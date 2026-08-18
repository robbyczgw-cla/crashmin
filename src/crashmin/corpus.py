"""Realistic Copy-as-cURL / HAR / raw-HTTP repros aimed at the fixture server.

These are not product features. They exist so we can hunt parser dialects and
compare structured reduction against header/query-only deletion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from crashmin.demo import (
    build_killer_request,
    fixture_b_request,
    fixture_c_request,
    fixture_d_request,
    fixture_e_request,
    fixture_f_request,
)
from crashmin.emit import to_raw_http
from crashmin.models import HttpRequest, format_cookie_header
from crashmin.oracle import Oracle, compile_oracle


PLACEHOLDER = "http://127.0.0.1:18765"


def retarget(text: str, base: str) -> str:
    return text.replace(PLACEHOLDER, base.rstrip("/"))


def _sq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ansi_c(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return "$'" + escaped + "'"


def _cmd_dq(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def emit_chrome(req: HttpRequest) -> str:
    """Chrome DevTools → Copy as cURL (bash)."""
    lines = [f"curl {_sq(req.url())} \\"]
    for name, value in req.headers:
        if name.lower() in {"content-length", "host", "cookie"}:
            continue
        lines.append(f"  -H {_sq(f'{name}: {value}')} \\")
    if req.cookies:
        lines.append(f"  -H {_sq('Cookie: ' + format_cookie_header(req.cookies))} \\")
    if req.body is not None:
        lines.append(f"  --data-raw {_sq(req.body.decode('utf-8'))} \\")
    lines.append("  --compressed")
    return "\n".join(lines) + "\n"


def emit_firefox(req: HttpRequest) -> str:
    """Firefox DevTools → Copy as cURL, ANSI-C body quotes."""
    parts = [f"curl {_sq(req.url())}"]
    for name, value in req.headers:
        if name.lower() in {"content-length", "host", "cookie"}:
            continue
        parts.append(f"-H {_sq(f'{name}: {value}')}")
    if req.cookies:
        parts.append(f"-H {_sq('Cookie: ' + format_cookie_header(req.cookies))}")
    if req.body is not None:
        text = req.body.decode("utf-8")
        if req.json_body is not None:
            text = json.dumps(req.json_body, indent=2, ensure_ascii=False)
        parts.append(f"--data-raw {_ansi_c(text)}")
    return " \\\n  ".join(parts) + "\n"


def emit_windows(req: HttpRequest) -> str:
    """Chrome on Windows → Copy as cURL (cmd.exe)."""
    chunks = ["curl ^", f"  {_cmd_dq(req.url())} ^"]
    for name, value in req.headers:
        if name.lower() in {"content-length", "host", "cookie"}:
            continue
        chunks.append(f"  -H {_cmd_dq(f'{name}: {value}')} ^")
    if req.cookies:
        chunks.append(f"  -H {_cmd_dq('Cookie: ' + format_cookie_header(req.cookies))} ^")
    if req.body is not None:
        chunks.append(f"  --data-raw {_cmd_dq(req.body.decode('utf-8'))}")
    else:
        chunks[-1] = chunks[-1].rstrip(" ^")
    return "\n".join(chunks) + "\n"


def emit_har(req: HttpRequest) -> str:
    headers = [{"name": n, "value": v} for n, v in req.headers]
    if req.cookies:
        headers.append({"name": "Cookie", "value": format_cookie_header(req.cookies)})
    post: dict[str, Any] | None = None
    if req.body is not None:
        post = {
            "mimeType": req.content_type() or "application/json",
            "text": req.body.decode("utf-8"),
        }
    doc = {
        "log": {
            "version": "1.2",
            "creator": {"name": "Chrome", "version": "128.0.0.0"},
            "entries": [
                {
                    "startedDateTime": "2026-08-17T12:00:00.000Z",
                    "time": 42,
                    "request": {
                        "method": req.method,
                        "url": req.url(),
                        "httpVersion": "HTTP/1.1",
                        "headers": headers,
                        "cookies": [{"name": n, "value": v} for n, v in req.cookies],
                        "queryString": [{"name": n, "value": v} for n, v in req.query],
                        "headersSize": -1,
                        "bodySize": len(req.body or b""),
                        **({"postData": post} if post else {}),
                    },
                    "response": {
                        "status": 500,
                        "statusText": "Internal Server Error",
                        "httpVersion": "HTTP/1.1",
                        "headers": [],
                        "cookies": [],
                        "content": {"size": 0, "mimeType": "text/plain"},
                        "redirectURL": "",
                        "headersSize": -1,
                        "bodySize": 0,
                    },
                    "cache": {},
                    "timings": {"send": 0, "wait": 0, "receive": 0},
                }
            ],
        }
    }
    return json.dumps(doc, indent=2)


def emit_http(req: HttpRequest) -> str:
    return to_raw_http(req)


OracleFactory = Callable[[], Oracle]
Builder = Callable[[str], HttpRequest]
Emitter = Callable[[HttpRequest], str]


@dataclass(frozen=True)
class CorpusCase:
    name: str
    dialect: str
    fixture: str
    builder: Builder
    emit: Emitter
    oracle: OracleFactory
    fmt: str
    confirm: int = 1
    # Structured reduction should beat surface-only deletion.
    expect_structure_wins: bool = True


def _oracle_a() -> Oracle:
    return compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"])


def _oracle_b() -> Oracle:
    return compile_oracle(statuses=["500"], body_contains=["pair collision"])


def _oracle_c() -> Oracle:
    return compile_oracle(statuses=["500"], body_contains=["kind=evil"])


def _oracle_d() -> Oracle:
    return compile_oracle(body_contains=["INTERNAL ERROR: widget exploded"])


def _oracle_e() -> Oracle:
    return compile_oracle(statuses=["500"], body_contains=["flaky-boom"])


def _oracle_f() -> Oracle:
    return compile_oracle(statuses=["500"], body_contains=["session gate"])


def nextjs_b_request(base_url: str) -> HttpRequest:
    """Looks like a Next.js / RSC POST that happens to hit fixture B."""
    req = fixture_b_request(base_url)
    req.set_header("Next-Action", "001a2b3c4d5e6f708192021222324252")
    req.set_header("Next-Router-State-Tree", "%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%5D%7D%5D")
    req.set_header("RSC", "1")
    req.set_header("Next-URL", "/dashboard/settings")
    req.json_body = {
        "alpha": "one",
        "beta": "two",
        "gamma": "three",
        "formState": {"dirty": True, "step": 4},
        "delta": {"nested": True, "n": 9},
        "epsilon": [1, 2, 3],
        "zeta": "noise",
        "client": {"buildId": "Kz9f1", "chunk": "app/dashboard/page.js"},
    }
    req.refresh_body_from_structure()
    return req


def graphqlish_c_request(base_url: str) -> HttpRequest:
    """Looks like a GraphQL POST; the crash is still the evil array item."""
    req = fixture_c_request(base_url)
    req.set_header("Apollo-Require-Preflight", "true")
    req.set_header("X-APOLLO-OPERATION-NAME", "UpdateItems")
    # Fixture C keys on top-level `items`. The GraphQL envelope is noise.
    req.json_body = {
        "operationName": "UpdateItems",
        "query": "mutation UpdateItems($items: [Item!]!) { updateItems(items: $items) { id } }",
        "items": [
            {"kind": "ok", "n": 1, "label": "alpha"},
            {"kind": "ok", "n": 2, "pad": "xxxx"},
            {"kind": "evil", "n": 3, "pad": "yyyy", "meta": {"a": 1}},
            {"kind": "ok", "n": 4},
            {"kind": "ok", "n": 5},
        ],
        "variables": {"client": "web", "trace": True},
        "extensions": {"clientLibrary": {"name": "apollo", "version": "3.11.0"}},
        "extra": True,
    }
    req.refresh_body_from_structure()
    return req


def anonymized_saas_request(base_url: str) -> HttpRequest:
    """Chrome 128 Copy as cURL, anonymized, aimed at fixture A.

    Header names, order, and cookie *names* match a real DevTools copy of a
    workspace-settings save. Hosts, tokens, emails, and IDs are replacements.
    The crash needle is the same as fixture A so the report is deterministic.
    """
    req = HttpRequest(method="POST")
    req.set_url(
        base_url.rstrip("/")
        + "/a?workspace=ws_7f3c&view=settings&tab=members&ref=sidebar"
        + "&utm_source=inapp&utm_medium=save&utm_campaign=workspace-q3"
        + "&cid=anon-11111111-2222-3333-4444-555555555555"
    )
    # Chrome copies header names in lowercase.
    req.headers = [
        ("accept", "application/json, text/plain, */*"),
        ("accept-language", "en-GB,en-US;q=0.9,en;q=0.8"),
        ("authorization", "Bearer anonymized-session-token"),
        ("content-type", "application/json"),
        ("origin", "https://app.example.invalid"),
        ("priority", "u=1, i"),
        ("referer", "https://app.example.invalid/settings/workspace?tab=members"),
        ("sec-ch-ua", '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"'),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"Linux"'),
        ("sec-fetch-dest", "empty"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-site", "same-origin"),
        ("user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
        ("x-crash-token", "letmein"),
        ("x-org-id", "org_anon_0001"),
        ("x-request-id", "req_anon_7f3c2a91e10b4d44"),
    ]
    req.cookies = [
        ("session", "sAnon.replaced"),
        ("__Host-next-auth.csrf-token", "anon-csrf"),
        ("ajs_anonymous_id", "anon-1111-2222-3333"),
        ("ajs_user_id", "usr_anon_42"),
        ("_ga", "GA1.2.1000000000.1700000000"),
        ("_gid", "GA1.2.2000000000.1700000000"),
        ("_fbp", "fb.1.1700000000.1000000000"),
        ("hubspotutk", "hs-anonymized"),
        ("intercom-session", "ic-anonymized"),
        ("mp_mixpanel", "mp-anonymized"),
        ("__stripe_mid", "mid_anonymized"),
        ("__stripe_sid", "sid_anonymized"),
        ("_clck", "clarity-anon"),
        ("_clsk", "clarity-anon-2"),
        ("GCLB", "affinity-anon"),
        ("locale", "en-GB"),
        ("theme", "system"),
    ]
    members = [
        {
            "id": f"usr_{i:04d}",
            "email": f"member{i}@example.invalid",
            "role": "member" if i else "admin",
            "lastSeen": "2026-08-01T12:00:00.000Z",
            "prefs": {"digest": True, "theme": "dark"},
        }
        for i in range(24)
    ]
    req.json_body = {
        "client": {
            "name": "web",
            "release": "2026.8.12-a1b2c3d",
            "buildId": "Kz9f1anonymized",
            "locale": "en-GB",
        },
        "workspace": {
            "id": "ws_7f3c",
            "name": "Example Workspace",
            "plan": "business",
            "region": "eu-west-1",
            "flags": {f"ff_{i:02d}": bool(i % 3) for i in range(18)},
        },
        "members": members,
        "audit": {
            "actor": "usr_0000",
            "reason": "settings.save",
            "ip": "203.0.113.88",
        },
        "payload": {
            "unused": True,
            "draft": {"title": "workspace settings", "dirty": True},
            "deeply": {
                "ignored": "yes",
                "nested": {
                    "comment": "replaced field; original key name retained",
                    "trigger": "boom",
                    "extra": {"k": 1, "note": "padding"},
                },
            },
        },
        "ui": {
            "sidebar": "collapsed",
            "density": "comfy",
            "whatsNew": list(range(12)),
        },
        "activity": [
            {
                "id": f"evt_{i:04d}",
                "type": "member.invited" if i % 2 == 0 else "setting.changed",
                "actor": f"usr_{i % 8:04d}",
                "at": "2026-08-01T12:00:00.000Z",
                "meta": {"source": "web", "pad": "x" * 40},
            }
            for i in range(40)
        ],
    }
    req.refresh_body_from_structure()
    return req


def emit_chrome_devtools(req: HttpRequest) -> str:
    """Match Chrome DevTools 'Copy as cURL (bash)': lowercase names, --data-raw."""
    lines = [f"curl {_sq(req.url())} \\"]
    for name, value in req.headers:
        if name.lower() in {"content-length", "host"}:
            continue
        lines.append(f"  -H {_sq(f'{name}: {value}')} \\")
    if req.cookies:
        lines.append(f"  -H {_sq('cookie: ' + format_cookie_header(req.cookies))} \\")
    if req.body is not None:
        lines.append(f"  --data-raw {_sq(req.body.decode('utf-8'))}")
    else:
        lines[-1] = lines[-1].rstrip(" \\")
    return "\n".join(lines) + "\n"


def fat_f_request(base_url: str) -> HttpRequest:
    """A GET that looks like an authenticated app page: 20 cookies, 15 query params."""
    req = fixture_f_request(base_url)
    extra_cookies = [
        ("intercom-session", "ic-" + "a" * 24),
        ("ajs_user_id", "usr_9911"),
        ("ajs_anonymous_id", "anon-deadbeef"),
        ("_hp2_id", "heap-" + "b" * 16),
        ("__stripe_mid", "mid_" + "c" * 20),
        ("__stripe_sid", "sid_" + "d" * 20),
        ("csrftoken", "not-this"),
        ("messages", "flash.none"),
        ("sidebar", "open"),
        ("density", "comfy"),
        ("ab", "exp42-control"),
        ("_clck", "clarity-xxxx"),
        ("_clsk", "clarity-yyyy"),
        ("GCLB", "load-balancer-affinity"),
    ]
    req.cookies = list(req.cookies) + extra_cookies
    extra_q = [
        ("utm_campaign", "q3-launch"),
        ("utm_content", "banner"),
        ("gclid", "CjwKCAjw" + "E" * 16),
        ("fbclid", "IwAR" + "F" * 16),
        ("ref", "email"),
        ("src", "legacy-redirect"),
        ("hl", "de"),
        ("feature", "new-nav"),
        ("cb", "184712"),
    ]
    req.query = list(req.query) + extra_q
    req.set_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    req.set_header("Accept", "text/html,application/xhtml+xml")
    req.set_header("Referer", "https://app.example.invalid/inbox?view=all")
    return req


CASES: list[CorpusCase] = [
    CorpusCase("a-chrome", "chrome-bash", "A", build_killer_request, emit_chrome, _oracle_a, "curl"),
    CorpusCase("a-firefox", "firefox-ansi-c", "A", build_killer_request, emit_firefox, _oracle_a, "curl"),
    CorpusCase("a-windows", "chrome-cmd", "A", build_killer_request, emit_windows, _oracle_a, "curl"),
    CorpusCase("a-http", "raw-http", "A", build_killer_request, emit_http, _oracle_a, "http"),
    CorpusCase("a-har", "har-1.2", "A", build_killer_request, emit_har, _oracle_a, "har"),
    CorpusCase("b-chrome", "chrome-bash", "B", fixture_b_request, emit_chrome, _oracle_b, "curl"),
    CorpusCase("b-nextjs", "chrome-bash", "B", nextjs_b_request, emit_chrome, _oracle_b, "curl"),
    CorpusCase("c-firefox", "firefox-ansi-c", "C", fixture_c_request, emit_firefox, _oracle_c, "curl"),
    CorpusCase("c-graphql", "chrome-bash", "C", graphqlish_c_request, emit_chrome, _oracle_c, "curl"),
    CorpusCase("d-chrome", "chrome-bash", "D", fixture_d_request, emit_chrome, _oracle_d, "curl"),
    CorpusCase("e-chrome", "chrome-bash", "E", fixture_e_request, emit_chrome, _oracle_e, "curl", confirm=3),
    CorpusCase("f-chrome", "chrome-bash", "F", fat_f_request, emit_chrome, _oracle_f, "curl", expect_structure_wins=False),
    CorpusCase("f-windows", "chrome-cmd", "F", fat_f_request, emit_windows, _oracle_f, "curl", expect_structure_wins=False),
    CorpusCase(
        "anonymized-chrome-saas",
        "chrome-devtools",
        "A",
        anonymized_saas_request,
        emit_chrome_devtools,
        _oracle_a,
        "curl",
    ),
]


def render_case(case: CorpusCase, base: str) -> str:
    return case.emit(case.builder(base))


def write_repros(directory, base: str = PLACEHOLDER) -> list[str]:
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    ext = {"curl": ".curl", "http": ".http", "har": ".har"}
    for case in CASES:
        path = directory / f"{case.name}{ext[case.fmt]}"
        path.write_text(render_case(case, base), encoding="utf-8")
        written.append(str(path))
    return written
