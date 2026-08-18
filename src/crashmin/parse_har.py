"""Parse one request out of a HAR file."""

from __future__ import annotations

import json
from typing import Any

from crashmin.models import HttpRequest, parse_cookie_header


class HarParseError(ValueError):
    pass


def _entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    log = doc.get("log")
    if not isinstance(log, dict):
        raise HarParseError("HAR is missing log object")
    entries = log.get("entries")
    if not isinstance(entries, list) or not entries:
        raise HarParseError("HAR has no entries")
    return entries


def parse_har(text: str | bytes, index: int = 0) -> HttpRequest:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarParseError(f"HAR is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise HarParseError("HAR root must be an object")
    entries = _entries(doc)
    if index < 0 or index >= len(entries):
        raise HarParseError(f"HAR index {index} out of range (0..{len(entries) - 1})")
    entry = entries[index]
    request = entry.get("request") if isinstance(entry, dict) else None
    if not isinstance(request, dict):
        raise HarParseError("HAR entry is missing request")

    url = request.get("url")
    if not isinstance(url, str) or not url:
        raise HarParseError("HAR request is missing url")
    method = str(request.get("method") or "GET").upper()
    req = HttpRequest(method=method)
    req.set_url(url)

    for header in request.get("headers") or []:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "")
        value = str(header.get("value") or "")
        if not name:
            continue
        low = name.lower()
        if low in {"host", "content-length", ":method", ":path", ":authority", ":scheme"}:
            continue
        if low == "cookie":
            req.cookies.extend(parse_cookie_header(value))
            continue
        req.headers.append((name, value))

    for cookie in request.get("cookies") or []:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if name and (name, value) not in req.cookies:
            req.cookies.append((name, value))

    # HAR queryString can supplement or replace the URL query. Prefer URL.
    if not req.query:
        for item in request.get("queryString") or []:
            if isinstance(item, dict) and item.get("name") is not None:
                req.query.append((str(item["name"]), str(item.get("value") or "")))

    post = request.get("postData")
    if isinstance(post, dict):
        mime = post.get("mimeType")
        if isinstance(mime, str) and mime and req.content_type() is None:
            req.set_header("Content-Type", mime)
        text_body = post.get("text")
        if isinstance(text_body, str):
            req.adopt_body(text_body.encode("utf-8"))
            req.maybe_infer_structured_body()
        elif post.get("params"):
            pairs = []
            for item in post["params"]:
                if isinstance(item, dict) and item.get("name") is not None:
                    pairs.append((str(item["name"]), str(item.get("value") or "")))
            req.form_body = pairs
            req.refresh_body_from_structure()
    return req
