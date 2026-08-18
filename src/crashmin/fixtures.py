"""Deliberately broken local HTTP services used as reduction targets.

Fixture A  POST /a   header + nested JSON field
Fixture B  POST /b   two fields together
Fixture C  POST /c   array item
Fixture D  POST /d   body-text oracle, HTTP 200
Fixture E  POST /e   confirmation / flake
Fixture F  GET  /f   cookie + query
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


def _read_json(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _deep_get(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _cookies(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    raw = handler.headers.get("Cookie") or ""
    out: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            out[name.strip()] = value.strip()
    return out


def _query(handler: BaseHTTPRequestHandler) -> dict[str, list[str]]:
    return parse_qs(urlparse(handler.path).query, keep_blank_values=True)


def _send(handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str = "text/plain") -> None:
    payload = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("X-Fixture", "crashmin")
    handler.end_headers()
    handler.wfile.write(payload)


# First-seen fingerprints that returned a flaky 500 without the real key.
_FLAKE_SEEN: set[str] = set()


def reset_flake_state() -> None:
    _FLAKE_SEEN.clear()


def _fixture_a(handler: BaseHTTPRequestHandler) -> None:
    token = handler.headers.get("X-Crash-Token")
    body = _read_json(handler)
    trigger = _deep_get(body, "payload", "deeply", "nested", "trigger")
    if token == "letmein" and trigger == "boom":
        _send(handler, 500, "panic: nil pointer dereference in handler")
        return
    _send(handler, 200, json.dumps({"ok": True, "fixture": "a"}), "application/json")


def _fixture_b(handler: BaseHTTPRequestHandler) -> None:
    body = _read_json(handler) or {}
    if not isinstance(body, dict):
        _send(handler, 200, '{"ok":true}', "application/json")
        return
    left = body.get("alpha") == "one"
    right = body.get("beta") == "two"
    if left and right:
        _send(handler, 500, "pair collision: alpha+beta")
        return
    _send(handler, 200, json.dumps({"ok": True, "left": left, "right": right}), "application/json")


def _fixture_c(handler: BaseHTTPRequestHandler) -> None:
    body = _read_json(handler) or {}
    items = body.get("items") if isinstance(body, dict) else None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("kind") == "evil":
                _send(handler, 500, "array item kind=evil detonated")
                return
    _send(handler, 200, '{"ok":true}', "application/json")


def _fixture_d(handler: BaseHTTPRequestHandler) -> None:
    body = _read_json(handler) or {}
    widget = body.get("widget") if isinstance(body, dict) else None
    if isinstance(widget, dict) and "id" in widget:
        _send(
            handler,
            200,
            "ok=1\nINTERNAL ERROR: widget exploded\ntrace=stable\n",
            "text/plain",
        )
        return
    _send(handler, 200, '{"ok":true}', "application/json")


def _fixture_e(handler: BaseHTTPRequestHandler) -> None:
    # Drain the body so keep-alive connections stay aligned.
    length = int(handler.headers.get("Content-Length") or 0)
    if length:
        handler.rfile.read(length)
    key = handler.headers.get("X-Flaky-Key")
    sometimes = handler.headers.get("X-Sometimes")
    if key == "yes":
        _send(handler, 500, "flaky-boom")
        return
    if sometimes == "1":
        # Deterministic one-shot flake: first time we see this exact request
        # without the real key, pretend to crash. Confirmation catches it.
        length = int(handler.headers.get("Content-Length") or 0)
        # Body was already consumed by the caller only in JSON fixtures;
        # here we include headers so each distinct candidate flakes once.
        fp = f"{handler.command}|{handler.path}|{sorted(handler.headers.items())}|{length}"
        if fp not in _FLAKE_SEEN:
            _FLAKE_SEEN.add(fp)
            _send(handler, 500, "flaky-boom")
            return
    _send(handler, 200, '{"ok":true}', "application/json")


def _fixture_f(handler: BaseHTTPRequestHandler) -> None:
    cookies = _cookies(handler)
    query = _query(handler)
    if cookies.get("session") == "s3cret" and query.get("need") == ["1"]:
        _send(handler, 500, "session gate")
        return
    _send(handler, 200, '{"ok":true}', "application/json")


ROUTES = {
    "/a": _fixture_a,
    "/b": _fixture_b,
    "/c": _fixture_c,
    "/d": _fixture_d,
    "/e": _fixture_e,
    "/f": _fixture_f,
}


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if getattr(self.server, "quiet", True):
            return
        super().log_message(fmt, *args)

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/health":
            _send(self, 200, "ok")
            return
        handler = ROUTES.get(route)
        if handler is None:
            _send(self, 404, f"unknown fixture {route}")
            return
        handler(self)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()


def make_server(host: str = "127.0.0.1", port: int = 0, quiet: bool = True) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), FixtureHandler)
    server.quiet = quiet  # type: ignore[attr-defined]
    return server


def serve_forever(host: str = "127.0.0.1", port: int = 18765, quiet: bool = False) -> None:
    server = make_server(host, port, quiet=quiet)
    actual = server.server_address[1]
    print(f"crashmin fixtures on http://{host}:{actual}", file=sys.stderr)
    print("routes: /a /b /c /d /e /f /health", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CrashMin local fixture servers")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    serve_forever(args.host, args.port, quiet=not args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
