"""In-memory HTTP request/response models."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit


PROTECTED_REQUEST_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
}


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def json_component_count(value: Any) -> int:
    """Count reducible JSON pieces (keys, array items, primitives)."""
    if isinstance(value, dict):
        return len(value) + sum(json_component_count(v) for v in value.values())
    if isinstance(value, list):
        return len(value) + sum(json_component_count(v) for v in value)
    return 1


def dumps_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def try_parse_json(raw: bytes | str | None) -> Any | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        if not raw:
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        text = raw
    text = text.strip()
    if not text:
        return None
    if text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_cookie_header(value: str) -> list[tuple[str, str]]:
    cookies: list[tuple[str, str]] = []
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, val = part.split("=", 1)
            cookies.append((name.strip(), val.strip()))
        else:
            cookies.append((part, ""))
    return cookies


def format_cookie_header(cookies: list[tuple[str, str]]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies)


def parse_urlencoded(raw: bytes | str) -> list[tuple[str, str]]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return []
    else:
        text = raw
    pairs: list[tuple[str, str]] = []
    if not text:
        return pairs
    from urllib.parse import parse_qsl

    return list(parse_qsl(text, keep_blank_values=True, strict_parsing=False))


@dataclass
class HttpResponse:
    status: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    elapsed_ms: float = 0.0
    timed_out: bool = False
    error: str | None = None

    @property
    def body_text(self) -> str:
        try:
            return self.body.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def header(self, name: str) -> str | None:
        needle = name.lower()
        for key, value in self.headers:
            if key.lower() == needle:
                return value
        return None


@dataclass
class HttpRequest:
    method: str = "GET"
    scheme: str = "http"
    host: str = "127.0.0.1"
    port: int | None = None
    path: str = "/"
    query: list[tuple[str, str]] = field(default_factory=list)
    headers: list[tuple[str, str]] = field(default_factory=list)
    cookies: list[tuple[str, str]] = field(default_factory=list)
    body: bytes | None = None
    json_body: Any = None
    form_body: list[tuple[str, str]] | None = None
    insecure: bool = False
    http_version: str = "HTTP/1.1"

    def copy(self) -> HttpRequest:
        return copy.deepcopy(self)

    def effective_port(self) -> int:
        return self.port if self.port is not None else _default_port(self.scheme)

    def netloc(self) -> str:
        port = self.port
        if port is None or port == _default_port(self.scheme):
            return self.host
        return f"{self.host}:{port}"

    def url(self) -> str:
        query = urlencode(self.query, doseq=True)
        return urlunsplit((self.scheme, self.netloc(), self.path or "/", query, ""))

    def set_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme:
            self.scheme = parsed.scheme
        if parsed.hostname:
            self.host = parsed.hostname
        if parsed.port is not None:
            self.port = parsed.port
        elif parsed.scheme:
            self.port = None
        self.path = parsed.path or "/"
        from urllib.parse import parse_qsl

        if parsed.query:
            self.query = list(parse_qsl(parsed.query, keep_blank_values=True))
        else:
            # Preserve explicit empty query vs missing. Missing → [].
            self.query = []

    def header_value(self, name: str) -> str | None:
        needle = name.lower()
        for key, value in self.headers:
            if key.lower() == needle:
                return value
        return None

    def set_header(self, name: str, value: str) -> None:
        needle = name.lower()
        for i, (key, _) in enumerate(self.headers):
            if key.lower() == needle:
                self.headers[i] = (key, value)
                return
        self.headers.append((name, value))

    def drop_header(self, name: str) -> None:
        needle = name.lower()
        self.headers = [(k, v) for k, v in self.headers if k.lower() != needle]

    def content_type(self) -> str | None:
        value = self.header_value("Content-Type")
        if value is None:
            return None
        return value.split(";", 1)[0].strip().lower()

    def refresh_body_from_structure(self) -> None:
        # Serialize only. Do not re-insert Content-Type; the reducer must be
        # able to drop it and have it stay gone.
        if self.json_body is not None:
            self.body = dumps_json(self.json_body)
        elif self.form_body is not None:
            self.body = urlencode(self.form_body).encode("utf-8")

    def adopt_body(self, raw: bytes | None) -> None:
        self.body = raw if raw else None
        self.json_body = None
        self.form_body = None
        if not raw:
            return
        ctype = self.content_type()
        parsed = try_parse_json(raw)
        if parsed is not None and (ctype in (None, "application/json") or ctype.endswith("+json")):
            self.json_body = parsed
            return
        if ctype == "application/x-www-form-urlencoded":
            form = parse_urlencoded(raw)
            if form or raw in (b"", b""):
                self.form_body = form

    def maybe_infer_structured_body(self) -> None:
        if self.body is None:
            return
        if self.json_body is None:
            parsed = try_parse_json(self.body)
            if parsed is not None:
                self.json_body = parsed
                return
        if self.form_body is None and self.content_type() == "application/x-www-form-urlencoded":
            self.form_body = parse_urlencoded(self.body)

    def wire_headers(self) -> list[tuple[str, str]]:
        """Headers to send, excluding hop-by-hop / auto Host/Content-Length."""
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for key, value in self.headers:
            low = key.lower()
            if low in PROTECTED_REQUEST_HEADERS:
                continue
            if low == "cookie":
                continue
            out.append((key, value))
            seen.add(low)
        if self.cookies:
            out.append(("Cookie", format_cookie_header(self.cookies)))
        return out

    def fingerprint(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.method.upper().encode())
        hasher.update(b"\0")
        hasher.update(self.url().encode())
        hasher.update(b"\0")
        for key, value in self.wire_headers():
            hasher.update(key.lower().encode())
            hasher.update(b":")
            hasher.update(value.encode())
            hasher.update(b"\n")
        hasher.update(b"\0")
        hasher.update(self.body or b"")
        return hasher.hexdigest()

    def component_count(self) -> int:
        count = len(self.headers) + len(self.cookies) + len(self.query)
        if self.json_body is not None:
            count += json_component_count(self.json_body)
        elif self.form_body is not None:
            count += len(self.form_body)
        elif self.body:
            count += 1
        return count

    def compact_curl_size(self) -> int:
        from crashmin.emit import to_curl

        return len(to_curl(self, pretty=False).encode("utf-8"))


def request_from_url(url: str) -> HttpRequest:
    req = HttpRequest()
    req.set_url(url)
    return req
