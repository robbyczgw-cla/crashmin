"""Serialize an HttpRequest back to curl or raw HTTP."""

from __future__ import annotations

from crashmin.models import HttpRequest, format_cookie_header


def _sq(value: str) -> str:
    """Single-quote a string for POSIX shells."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def to_curl(req: HttpRequest, pretty: bool = True) -> str:
    parts: list[str] = ["curl"]
    method = req.method.upper()
    has_body = bool(req.body)
    if method == "HEAD":
        parts.append("-I")
    elif method not in ("GET", "POST") or (method == "GET" and has_body):
        parts.extend(["-X", method])
    elif method == "POST" and not has_body:
        parts.extend(["-X", "POST"])

    if req.insecure:
        parts.append("-k")

    for name, value in req.headers:
        if name.lower() in {"content-length", "host", "cookie"}:
            continue
        parts.extend(["-H", f"{name}: {value}"])

    if req.cookies:
        parts.extend(["-H", f"Cookie: {format_cookie_header(req.cookies)}"])

    if req.body is not None:
        try:
            text = req.body.decode("utf-8")
            if "\0" in text:
                raise UnicodeDecodeError("utf-8", req.body, 0, 1, "nul")
            parts.extend(["-d", text])
        except UnicodeDecodeError:
            # Best-effort: latin-1 round-trip so the command stays pasteable.
            parts.extend(["--data-binary", req.body.decode("latin-1")])

    parts.append(req.url())

    rendered = [_sq(p) if i > 0 and _needs_quote(p) else p for i, p in enumerate(parts)]
    if not pretty:
        return " ".join(rendered)

    if len(rendered) == 1:
        return "curl"
    # Keep flag+value on one line: `-H 'Name: v'`, `-d '{...}'`, `-X POST`.
    glued: list[str] = ["curl"]
    i = 1
    value_flags = {"-H", "-d", "-X", "-b", "-A", "-e", "-u", "--data-binary"}
    while i < len(rendered):
        if rendered[i] in value_flags and i + 1 < len(rendered):
            glued.append(f"{rendered[i]} {rendered[i + 1]}")
            i += 2
        else:
            glued.append(rendered[i])
            i += 1
    if len(glued) == 1:
        return glued[0]
    lines = [glued[0] + " \\"]
    for j, item in enumerate(glued[1:]):
        last = j == len(glued) - 2
        lines.append(f"  {item}" + ("" if last else " \\"))
    return "\n".join(lines)


def _needs_quote(token: str) -> bool:
    if token in {"curl", "-I", "-k", "-X", "-H", "-d", "--data-binary"}:
        return False
    if token.isalpha() and token.isupper() and len(token) <= 7:
        # HTTP methods used with -X
        return False
    return True


def to_raw_http(req: HttpRequest) -> str:
    target = req.path or "/"
    if req.query:
        from urllib.parse import urlencode

        target = f"{target}?{urlencode(req.query, doseq=True)}"
    lines = [f"{req.method.upper()} {target} {req.http_version or 'HTTP/1.1'}"]
    lines.append(f"Host: {req.netloc()}")
    for name, value in req.headers:
        if name.lower() in {"host", "content-length", "cookie"}:
            continue
        lines.append(f"{name}: {value}")
    if req.cookies:
        lines.append(f"Cookie: {format_cookie_header(req.cookies)}")
    body = req.body or b""
    if body:
        lines.append(f"Content-Length: {len(body)}")
    lines.append("")
    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = body.decode("latin-1")
    return "\r\n".join(lines) + (("\r\n" + body_text) if body else "\r\n")
