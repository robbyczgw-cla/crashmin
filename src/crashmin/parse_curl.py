"""Parse a curl command into an HttpRequest."""

from __future__ import annotations

import os
import re
from typing import Iterable

from crashmin.models import HttpRequest, parse_cookie_header


_CONTINUATION = re.compile(r"[\\^]\r?\n")
_WS = set(" \t\r\n")


class CurlParseError(ValueError):
    pass


def _decode_ansi_c(text: str) -> str:
    """Decode a $'...' ANSI-C quoted string (subset)."""
    out: list[str] = []
    i = 0
    escapes = {
        "n": "\n",
        "t": "\t",
        "r": "\r",
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "v": "\v",
        "\\": "\\",
        "'": "'",
        '"': '"',
        "?": "?",
        "0": "\0",
        "e": "\x1b",
    }
    while i < len(text):
        ch = text[i]
        if ch != "\\" or i + 1 >= len(text):
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt in escapes:
            out.append(escapes[nxt])
            i += 2
            continue
        if nxt == "x" and i + 3 < len(text):
            hexpart = text[i + 2 : i + 4]
            if re.fullmatch(r"[0-9a-fA-F]{2}", hexpart):
                out.append(chr(int(hexpart, 16)))
                i += 4
                continue
        out.append(nxt)
        i += 2
    return "".join(out)


def split_argv(text: str) -> list[str]:
    """Split a shell-ish curl command into argv tokens.

    Handles backslash and caret line continuations, single/double quotes,
    and a subset of $'...' ANSI-C quotes produced by some browsers.
    """
    text = _CONTINUATION.sub(" ", text)
    text = text.strip()
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    tokens: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)

    def flush() -> None:
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    while i < n:
        ch = text[i]
        if ch in _WS:
            flush()
            i += 1
            continue
        if ch == "#" and not buf:
            # comment to end of line
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "$" and i + 1 < n and text[i + 1] == "'":
            i += 2
            inner: list[str] = []
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    inner.append(text[i : i + 2])
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                inner.append(text[i])
                i += 1
            buf.append(_decode_ansi_c("".join(inner)))
            continue
        if ch == "'":
            i += 1
            while i < n and text[i] != "'":
                buf.append(text[i])
                i += 1
            if i < n:
                i += 1
            continue
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    if nxt in '$`"\\\n':
                        if nxt != "\n":
                            buf.append(nxt)
                        i += 2
                        continue
                buf.append(text[i])
                i += 1
            if i < n:
                i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        buf.append(ch)
        i += 1
    flush()
    return tokens


def _is_url(token: str) -> bool:
    low = token.lower()
    return low.startswith("http://") or low.startswith("https://")


def _read_data_arg(value: str) -> bytes:
    if value.startswith("@") and len(value) > 1:
        path = value[1:]
        with open(path, "rb") as handle:
            return handle.read()
    return value.encode("utf-8")


def _split_header(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        return raw.strip(), ""
    name, value = raw.split(":", 1)
    return name.strip(), value.strip()


def parse_curl_argv(argv: Iterable[str]) -> HttpRequest:
    tokens = list(argv)
    if tokens and os.path.basename(tokens[0]).startswith("curl"):
        tokens = tokens[1:]

    req = HttpRequest()
    method_set = False
    url: str | None = None
    data_parts: list[bytes] = []
    data_is_urlencoded = False
    json_flag_body: bytes | None = None
    i = 0

    long_with_value = {
        "--url",
        "--header",
        "--cookie",
        "--data",
        "--data-raw",
        "--data-binary",
        "--data-ascii",
        "--data-urlencode",
        "--request",
        "--user-agent",
        "--referer",
        "--user",
        "--max-time",
        "--connect-timeout",
        "--output",
        "--dump-header",
        "--retry",
        "--unix-socket",
        "--resolve",
        "--proxy",
        "--json",
    }
    short_with_value = set("HXbAeuodDmFw")

    skip_flags = {
        "--compressed",
        "--silent",
        "--show-error",
        "--fail",
        "--location",
        "--location-trusted",
        "--http1.0",
        "--http1.1",
        "--http2",
        "--http2-prior-knowledge",
        "--globoff",
        "--raw",
        "--include",
        "--head",
        "--verbose",
        "--no-progress-meter",
        "--progress-bar",
        "--insecure",
        "--ssl-no-revoke",
        "--tlsv1",
        "--tlsv1.0",
        "--tlsv1.1",
        "--tlsv1.2",
        "--tlsv1.3",
        "--ipv4",
        "--ipv6",
        "--get",
        "--next",
    }

    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-k", "--insecure"):
            req.insecure = True
            i += 1
            continue
        if tok in ("-s", "-S", "-f", "-L", "-v", "-i", "-I", "-g", "-4", "-6", "-#", "-N"):
            i += 1
            continue
        if tok == "--":
            i += 1
            if i < len(tokens) and url is None:
                url = tokens[i]
                i += 1
            continue
        if tok in skip_flags:
            if tok == "--get" and data_parts:
                # curl --get with --data moves data to query string; handle later
                pass
            i += 1
            continue

        name: str | None = None
        value: str | None = None
        if tok.startswith("--") and "=" in tok:
            name, value = tok.split("=", 1)
        elif tok.startswith("--"):
            name = tok
            if name in long_with_value:
                i += 1
                if i >= len(tokens):
                    raise CurlParseError(f"flag {name} requires a value")
                value = tokens[i]
        elif tok.startswith("-") and len(tok) == 2:
            name = tok
            if tok[1] in short_with_value:
                i += 1
                if i >= len(tokens):
                    raise CurlParseError(f"flag {name} requires a value")
                value = tokens[i]
        elif tok.startswith("-") and len(tok) > 2 and not tok.startswith("--"):
            # clustered shorts like -sS or -Hvalue
            flag = tok[1]
            rest = tok[2:]
            name = f"-{flag}"
            if flag in short_with_value:
                value = rest
            else:
                # treat remaining as extra flags without values
                i += 1
                continue

        if name in ("-H", "--header") and value is not None:
            hname, hval = _split_header(value)
            if hname.lower() == "cookie":
                req.cookies.extend(parse_cookie_header(hval))
            elif hname.lower() == "host":
                # Host is derived from the URL; remember the hostname if URL missing.
                host = hval
                port = None
                if ":" in hval and not hval.startswith("["):
                    host, _, port_s = hval.rpartition(":")
                    try:
                        port = int(port_s)
                    except ValueError:
                        host = hval
                        port = None
                if not req.host or req.host == "127.0.0.1":
                    req.host = host
                    if port is not None:
                        req.port = port
            elif hname.lower() != "content-length":
                req.headers.append((hname, hval))
            i += 1
            continue

        if name in ("-b", "--cookie") and value is not None:
            if "=" in value or ";" in value:
                req.cookies.extend(parse_cookie_header(value))
            else:
                # cookie file — ignore contents if missing, try to read
                if os.path.isfile(value):
                    with open(value, encoding="utf-8", errors="replace") as handle:
                        req.cookies.extend(parse_cookie_header(handle.read()))
            i += 1
            continue

        if name in ("-A", "--user-agent") and value is not None:
            req.set_header("User-Agent", value)
            i += 1
            continue

        if name in ("-e", "--referer") and value is not None:
            req.set_header("Referer", value)
            i += 1
            continue

        if name in ("-u", "--user") and value is not None:
            req.set_header("Authorization", f"Basic {value}")
            i += 1
            continue

        if name in ("-X", "--request") and value is not None:
            req.method = value.upper()
            method_set = True
            i += 1
            continue

        if name == "--url" and value is not None:
            url = value
            i += 1
            continue

        if name == "--json" and value is not None:
            json_flag_body = _read_data_arg(value)
            req.set_header("Content-Type", "application/json")
            req.set_header("Accept", "application/json")
            if not method_set:
                req.method = "POST"
            i += 1
            continue

        if name in ("-d", "--data", "--data-raw", "--data-ascii", "--data-binary") and value is not None:
            data_parts.append(_read_data_arg(value))
            if not method_set:
                req.method = "POST"
            i += 1
            continue

        if name == "--data-urlencode" and value is not None:
            from urllib.parse import quote

            if value.startswith("@"):
                raw = _read_data_arg(value)
                data_parts.append(quote(raw.decode("utf-8", errors="replace")).encode("ascii"))
            elif "=" in value:
                key, val = value.split("=", 1)
                if val.startswith("@"):
                    raw = _read_data_arg(val)
                    val = raw.decode("utf-8", errors="replace")
                data_parts.append(f"{quote(key)}={quote(val)}".encode("ascii"))
            else:
                data_parts.append(quote(value).encode("ascii"))
            data_is_urlencoded = True
            if not method_set:
                req.method = "POST"
            i += 1
            continue

        if name in (
            "-o",
            "--output",
            "-D",
            "--dump-header",
            "-m",
            "--max-time",
            "--connect-timeout",
            "-w",
            "--retry",
            "--unix-socket",
            "--resolve",
            "-x",
            "--proxy",
            "-F",  # multipart: skip value, do not treat as JSON
        ):
            i += 1
            continue

        if name is not None:
            # Unknown flag: skip value-less, ignore
            i += 1
            continue

        if _is_url(tok) or url is None:
            url = tok
            i += 1
            continue

        i += 1

    if url is None:
        raise CurlParseError("curl command has no URL")
    req.set_url(url)

    body: bytes | None = None
    if json_flag_body is not None:
        body = json_flag_body
    elif data_parts:
        if data_is_urlencoded:
            body = b"&".join(data_parts)
            if req.content_type() is None:
                req.set_header("Content-Type", "application/x-www-form-urlencoded")
        elif len(data_parts) == 1:
            body = data_parts[0]
        else:
            body = b"&".join(data_parts)
            if req.content_type() is None:
                req.set_header("Content-Type", "application/x-www-form-urlencoded")
    if body is not None:
        req.adopt_body(body)
        req.maybe_infer_structured_body()
    return req


def parse_curl(text: str) -> HttpRequest:
    argv = split_argv(text)
    if not argv:
        raise CurlParseError("empty curl command")
    # Allow a file that is just the command plus comments
    if not (os.path.basename(argv[0]).startswith("curl") or _is_url(argv[0]) or argv[0].startswith("-")):
        raise CurlParseError("input does not look like a curl command")
    return parse_curl_argv(argv)
