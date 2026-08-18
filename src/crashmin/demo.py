"""Build the deliberately huge killer-demo request for fixture A."""

from __future__ import annotations

import json

from crashmin.models import HttpRequest


NOISE_HEADERS = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
    ("Accept-Language", "en-US,en;q=0.9,fr;q=0.8,de;q=0.7"),
    ("Accept-Encoding", "gzip, deflate, br"),
    ("Cache-Control", "max-age=0"),
    ("Pragma", "no-cache"),
    ("Upgrade-Insecure-Requests", "1"),
    ("Sec-Fetch-Dest", "document"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-CH-UA", '"Chromium";v="128", "Not;A=Brand";v="24"'),
    ("Sec-CH-UA-Mobile", "?0"),
    ("Sec-CH-UA-Platform", '"Linux"'),
    ("Referer", "https://intranet.example.invalid/app/dashboard?ref=copy-as-curl"),
    ("Origin", "https://intranet.example.invalid"),
    ("DNT", "1"),
    ("Connection", "keep-alive"),
    ("X-Requested-With", "XMLHttpRequest"),
    ("X-Forwarded-For", "203.0.113.88"),
    ("X-Request-ID", "req-7f3c2a91-e10b-4d44-9b0e-2c8f11aa0001"),
    ("X-CSRF-Token", "csrf-not-the-crash-token-aaaaaaaaaaaaaaaa"),
    ("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.notarealtoken"),
    ("Content-Type", "application/json"),
]


def _noise_cookies() -> list[tuple[str, str]]:
    cookies = [
        ("_ga", "GA1.2.1234567890.1623456789"),
        ("_gid", "GA1.2.9876543210.1623456789"),
        ("_fbp", "fb.1.1623456789.1234567890"),
        ("_gat", "1"),
        ("ajs_anonymous_id", "anon-1111-2222-3333"),
        ("hubspotutk", "hs-aaaaaaaaaaaaaaaa"),
        ("intercom-id", "ic-bbbbbbbbbbbbbbbb"),
        ("mp_mixpanel", "mp-cccccccccccccccc"),
        ("preference", "dark"),
        ("language", "en-US"),
        ("theme", "midnight"),
        ("sidebar", "collapsed"),
        ("consent", "advertising|analytics|functional"),
        ("campaign", "spring-sale-2026"),
        ("ab_bucket", "control-47"),
        ("session_hint", "not-the-real-session"),
        ("csrftoken", "not-required-for-this-crash"),
        ("uid", "424242"),
        ("locale", "en_US.UTF-8"),
        ("tz", "America/New_York"),
    ]
    for i in range(10):
        cookies.append((f"noise_ck_{i:02d}", f"val_{'x' * 12}_{i}"))
    return cookies


def _noise_query() -> list[tuple[str, str]]:
    params = [
        ("utm_source", "devtools"),
        ("utm_medium", "copy-as-curl"),
        ("utm_campaign", "crashmin-demo"),
        ("utm_content", "hero"),
        ("utm_term", "nil-pointer"),
        ("gclid", "CjwKCAjw" + "A" * 20),
        ("fbclid", "IwAR" + "B" * 20),
        ("mc_cid", "mailchimp-campaign"),
        ("mc_eid", "mailchimp-email"),
        ("ref", "sidebar"),
        ("src", "legacy"),
        ("ts", "1773878400"),
        ("cb", "cachebust-9911"),
        ("page", "1"),
        ("sort", "desc"),
        ("hl", "en"),
        ("debug", "0"),
        ("trace", "1"),
        ("feature_flags", "a,b,c,d,e"),
        ("experiment", "nested-json-crash"),
    ]
    for i in range(20):
        params.append((f"q{i:02d}", f"noise-{i}-{'y' * 8}"))
    return params


def _noise_json() -> dict:
    users = [{"id": i, "email": f"user{i}@example.invalid", "role": "viewer", "meta": {"n": i}} for i in range(40)]
    flags = {f"flag_{i:02d}": bool(i % 2) for i in range(30)}
    blob = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 120
    return {
        "meta": {
            "client": "web",
            "version": "2026.8.17",
            "build": "deadbeef",
            "session": "sess-" + "0" * 32,
            "noise": blob,
        },
        "user": {
            "id": 999,
            "name": "Ada Lovelace",
            "email": "ada@example.invalid",
            "prefs": {"theme": "dark", "digest": True, "locale": "en"},
        },
        "users": users,
        "flags": flags,
        "analytics": {
            "events": [{"t": i, "name": "page_view", "props": {"n": i, "p": "dash"}} for i in range(25)],
            "context": {"ip": "203.0.113.88", "ua": "chrome"},
        },
        "payload": {
            "unused": True,
            "padding": {"a": 1, "b": 2, "c": {"d": [1, 2, 3, 4, 5], "e": "nope"}},
            "deeply": {
                "ignored": "yes",
                "nested": {
                    "comment": "the next field is the only one that matters",
                    "trigger": "boom",
                    "extra": {"k": 1, "m": 2, "n": [0, 0, 0]},
                },
                "siblings": {"x": 1, "y": 2, "z": 3},
            },
        },
        "attachments": [{"name": f"file{i}.png", "size": 1000 + i} for i in range(15)],
    }


def build_killer_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="POST")
    req.set_url(base_url.rstrip("/") + "/a")
    req.headers = list(NOISE_HEADERS)
    req.headers.append(("X-Crash-Token", "letmein"))
    req.cookies = _noise_cookies()
    req.query = _noise_query()
    req.json_body = _noise_json()
    req.refresh_body_from_structure()
    return req


def killer_curl(base_url: str) -> str:
    from crashmin.emit import to_curl

    return to_curl(build_killer_request(base_url), pretty=True)


def fixture_b_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="POST")
    req.set_url(base_url.rstrip("/") + "/b")
    req.set_header("Content-Type", "application/json")
    req.json_body = {
        "alpha": "one",
        "beta": "two",
        "gamma": "three",
        "delta": {"nested": True, "n": 9},
        "epsilon": [1, 2, 3],
        "zeta": "noise",
    }
    req.refresh_body_from_structure()
    return req


def fixture_c_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="POST")
    req.set_url(base_url.rstrip("/") + "/c")
    req.set_header("Content-Type", "application/json")
    req.json_body = {
        "items": [
            {"kind": "ok", "n": 1},
            {"kind": "ok", "n": 2, "pad": "xxxx"},
            {"kind": "evil", "n": 3, "pad": "yyyy", "meta": {"a": 1}},
            {"kind": "ok", "n": 4},
            {"kind": "ok", "n": 5},
        ],
        "extra": True,
    }
    req.refresh_body_from_structure()
    return req


def fixture_d_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="POST")
    req.set_url(base_url.rstrip("/") + "/d")
    req.set_header("Content-Type", "application/json")
    req.json_body = {
        "widget": {"id": "w-99", "color": "red", "unused": True},
        "note": "please ignore",
        "count": 4,
    }
    req.refresh_body_from_structure()
    return req


def fixture_e_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="POST")
    req.set_url(base_url.rstrip("/") + "/e")
    req.set_header("X-Flaky-Key", "yes")
    req.set_header("X-Sometimes", "1")
    req.set_header("X-Noise", "aaaaaaaa")
    req.set_header("Content-Type", "application/json")
    req.json_body = {"pad": 1}
    req.refresh_body_from_structure()
    return req


def fixture_f_request(base_url: str) -> HttpRequest:
    req = HttpRequest(method="GET")
    req.set_url(base_url.rstrip("/") + "/f")
    req.cookies = [
        ("session", "s3cret"),
        ("_ga", "GA1.2.1"),
        ("_gid", "GA1.2.2"),
        ("theme", "light"),
        ("locale", "en"),
        ("sid_extra", "nope"),
    ]
    req.query = [
        ("need", "1"),
        ("utm_source", "x"),
        ("utm_medium", "y"),
        ("page", "3"),
        ("q", "search"),
        ("debug", "1"),
    ]
    return req
