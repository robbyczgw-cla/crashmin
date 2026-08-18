"""Parse a raw HTTP/1.x request."""

from __future__ import annotations

from crashmin.models import HttpRequest, parse_cookie_header


class HttpParseError(ValueError):
    pass


def parse_raw_http(text: str | bytes, default_scheme: str = "http") -> HttpRequest:
    if isinstance(text, bytes):
        raw = text
        try:
            head_text_source = text.decode("utf-8")
        except UnicodeDecodeError:
            head_text_source = text.decode("latin-1")
    else:
        raw = text.encode("utf-8")
        head_text_source = text

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        head_text_source = head_text_source.lstrip("\ufeff")

    # Split headers/body on first blank line. Accept \r\n\r\n or \n\n.
    split_at = None
    sep_len = 0
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx != -1 and (split_at is None or idx < split_at):
            split_at = idx
            sep_len = len(sep)
    if split_at is None:
        header_bytes = raw
        body = b""
    else:
        header_bytes = raw[:split_at]
        body = raw[split_at + sep_len :]

    try:
        header_text = header_bytes.decode("utf-8")
    except UnicodeDecodeError:
        header_text = header_bytes.decode("latin-1")

    lines = header_text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].strip():
        raise HttpParseError("raw HTTP request is missing a request line")

    request_line = lines[0].strip()
    parts = request_line.split()
    if len(parts) < 2:
        raise HttpParseError(f"malformed request line: {request_line!r}")
    method, target = parts[0], parts[1]
    version = parts[2] if len(parts) > 2 else "HTTP/1.1"

    req = HttpRequest(method=method.upper(), http_version=version, scheme=default_scheme)

    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        if line[0] in " \t" and headers:
            prev_n, prev_v = headers[-1]
            headers[-1] = (prev_n, prev_v + " " + line.strip())
            continue
        if ":" not in line:
            raise HttpParseError(f"malformed header line: {line!r}")
        name, value = line.split(":", 1)
        headers.append((name.strip(), value.strip()))

    host = None
    port = None
    for name, value in headers:
        low = name.lower()
        if low == "host":
            host = value
            if value.startswith("["):
                # IPv6
                if "]" in value:
                    host = value[1 : value.index("]")]
                    rest = value[value.index("]") + 1 :]
                    if rest.startswith(":"):
                        try:
                            port = int(rest[1:])
                        except ValueError:
                            port = None
            elif ":" in value:
                host, _, port_s = value.rpartition(":")
                try:
                    port = int(port_s)
                except ValueError:
                    host = value
                    port = None
        elif low == "cookie":
            req.cookies.extend(parse_cookie_header(value))
        elif low == "content-length":
            continue
        else:
            req.headers.append((name, value))

    if target.startswith("http://") or target.startswith("https://"):
        req.set_url(target)
    else:
        if "?" in target:
            path, _, query = target.partition("?")
        else:
            path, query = target, ""
        req.path = path or "/"
        if query:
            from urllib.parse import parse_qsl

            req.query = list(parse_qsl(query, keep_blank_values=True))
        if host:
            req.host = host
            req.port = port
        req.scheme = default_scheme

    if body:
        # Trim a single trailing newline that editors often add after the body
        req.adopt_body(body)
        req.maybe_infer_structured_body()
    return req
