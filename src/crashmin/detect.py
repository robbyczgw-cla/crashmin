"""Detect input format and parse a request."""

from __future__ import annotations

from crashmin.models import HttpRequest
from crashmin.parse_curl import CurlParseError, parse_curl
from crashmin.parse_har import HarParseError, parse_har
from crashmin.parse_http import HttpParseError, parse_raw_http


class DetectError(ValueError):
    pass


_HTTP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "TRACE",
    "CONNECT",
}


def sniff(text: str) -> str:
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped:
        raise DetectError("empty input")
    if stripped[0] in "{[":
        return "har"
    head = stripped.split(None, 1)[0]
    if head.lower() == "curl" or head.startswith("curl"):
        return "curl"
    if head.upper() in _HTTP_METHODS:
        return "http"
    if "curl " in stripped[:200].lower() or stripped.lstrip().startswith("curl"):
        return "curl"
    raise DetectError(
        "could not detect input format (expected a curl command, raw HTTP request, or HAR JSON)"
    )


def parse_input(text: str, fmt: str = "auto", har_index: int = 0) -> HttpRequest:
    if fmt == "auto":
        fmt = sniff(text)
    if fmt == "curl":
        try:
            return parse_curl(text)
        except CurlParseError as exc:
            raise DetectError(str(exc)) from exc
    if fmt == "http":
        try:
            return parse_raw_http(text)
        except HttpParseError as exc:
            raise DetectError(str(exc)) from exc
    if fmt == "har":
        try:
            return parse_har(text, index=har_index)
        except HarParseError as exc:
            raise DetectError(str(exc)) from exc
    raise DetectError(f"unknown format: {fmt}")
