"""Hierarchical, HTTP-aware request reduction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlencode

from crashmin.ddmin import ddmin
from crashmin.emit import to_curl
from crashmin.executor import BudgetExceeded, Executor
from crashmin.json_reduce import reduce_json
from crashmin.models import HttpRequest

Listener = Callable[[str], None]


AUTO_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}


@dataclass
class ReductionResult:
    original: HttpRequest
    minimized: HttpRequest
    original_bytes: int
    minimized_bytes: int
    original_components: int
    minimized_components: int
    probes: int
    cache_hits: int
    phases: list[str] = field(default_factory=list)
    final_hits: int = 0
    final_trials: int = 0
    aborted: str | None = None

    @property
    def ratio(self) -> float:
        if self.original_bytes == 0:
            return 0.0
        return 1.0 - (self.minimized_bytes / self.original_bytes)

    @property
    def confirmed(self) -> bool:
        return self.final_trials > 0 and self.final_hits == self.final_trials

    def summary_lines(self) -> list[str]:
        pct = self.ratio * 100
        same = "YES" if self.confirmed else ("UNKNOWN" if self.final_trials == 0 else "NO")
        return [
            f"{self.original_bytes:,} bytes -> {self.minimized_bytes:,} bytes",
            f"{self.original_components} components -> {self.minimized_components}",
            f"{pct:.2f}% reduction",
            f"same failure: {same}"
            + (f" ({self.final_hits}/{self.final_trials})" if self.final_trials else ""),
        ]


def reduce_request(
    req: HttpRequest,
    executor: Executor,
    *,
    reduce_path: bool = True,
    final_confirm: int = 0,
    listener: Listener | None = None,
) -> ReductionResult:
    original = req.copy()
    original_bytes = original.compact_curl_size()
    original_components = original.component_count()
    log = listener or (lambda _msg: None)
    current = req.copy()
    current.refresh_body_from_structure()
    phases: list[str] = []

    if not executor.interesting(current):
        raise RuntimeError(
            "baseline request is not interesting "
            f"(oracle: {', '.join(executor.oracle.describe()) or 'none'}). "
            "Check the target is up and the oracle matches the failure."
        )
    log("baseline is interesting")

    def accept(candidate: HttpRequest) -> bool:
        candidate = candidate.copy()
        candidate.refresh_body_from_structure()
        try:
            return executor.interesting(candidate)
        except BudgetExceeded:
            raise

    try:
        current = _phase_drop_body(current, accept, phases, log)
        current = _phase_headers(current, accept, phases, log)
        current = _phase_cookies(current, accept, phases, log)
        current = _phase_query(current, accept, phases, log)
        current = _phase_form(current, accept, phases, log)
        current = _phase_json(current, accept, phases, log)
        if reduce_path:
            current = _phase_path(current, accept, phases, log)
        current = _phase_header_values(current, accept, phases, log)
        current = _phase_query_values(current, accept, phases, log)
        current = _phase_cookie_values(current, accept, phases, log)
        current = _cleanup_headers(current, accept, phases, log)
    except BudgetExceeded as exc:
        log(f"budget exhausted ({exc}); returning best so far")
        phases.append(f"aborted: {exc}")
        minimized = current.copy()
        minimized.refresh_body_from_structure()
        return ReductionResult(
            original=original,
            minimized=minimized,
            original_bytes=original_bytes,
            minimized_bytes=minimized.compact_curl_size(),
            original_components=original_components,
            minimized_components=minimized.component_count(),
            probes=executor.stats.sent,
            cache_hits=executor.stats.cache_hits,
            phases=phases,
            aborted=str(exc),
        )

    minimized = current.copy()
    minimized.refresh_body_from_structure()
    final_hits = 0
    final_trials = 0
    if final_confirm > 0:
        final_hits, final_trials = executor.confirm_only(minimized, final_confirm)
        log(f"final confirmation {final_hits}/{final_trials}")

    return ReductionResult(
        original=original,
        minimized=minimized,
        original_bytes=original_bytes,
        minimized_bytes=minimized.compact_curl_size(),
        original_components=original_components,
        minimized_components=minimized.component_count(),
        probes=executor.stats.sent,
        cache_hits=executor.stats.cache_hits,
        phases=phases,
        final_hits=final_hits,
        final_trials=final_trials,
    )


def _apply(base: HttpRequest, mutator) -> HttpRequest:
    cand = base.copy()
    mutator(cand)
    cand.refresh_body_from_structure()
    return cand


def _phase_drop_body(req: HttpRequest, accept, phases, log) -> HttpRequest:
    if not req.body:
        return req
    cand = req.copy()
    cand.body = None
    cand.json_body = None
    cand.form_body = None
    if accept(cand):
        phases.append("dropped body")
        log("dropped body")
        return cand
    return req


def _reducible_headers(req: HttpRequest) -> list[tuple[str, str]]:
    out = []
    for name, value in req.headers:
        if name.lower() in AUTO_HEADERS or name.lower() == "cookie":
            continue
        out.append((name, value))
    return out


def _phase_headers(req: HttpRequest, accept, phases, log) -> HttpRequest:
    headers = _reducible_headers(req)
    if not headers:
        return req
    before = len(headers)

    def test(subset: list[tuple[str, str]]) -> bool:
        cand = req.copy()
        cand.headers = list(subset)
        return accept(cand)

    kept = ddmin(headers, test, assume_original=True)
    if len(kept) != before:
        phases.append(f"headers {before} -> {len(kept)}")
        log(f"headers {before} -> {len(kept)}")
    req = req.copy()
    req.headers = list(kept)
    return req


def _phase_cookies(req: HttpRequest, accept, phases, log) -> HttpRequest:
    cookies = list(req.cookies)
    if not cookies:
        return req
    before = len(cookies)

    def test(subset: list[tuple[str, str]]) -> bool:
        cand = req.copy()
        cand.cookies = list(subset)
        return accept(cand)

    kept = ddmin(cookies, test, assume_original=True)
    if len(kept) != before:
        phases.append(f"cookies {before} -> {len(kept)}")
        log(f"cookies {before} -> {len(kept)}")
    req = req.copy()
    req.cookies = list(kept)
    return req


def _phase_query(req: HttpRequest, accept, phases, log) -> HttpRequest:
    params = list(req.query)
    if not params:
        return req
    before = len(params)

    def test(subset: list[tuple[str, str]]) -> bool:
        cand = req.copy()
        cand.query = list(subset)
        return accept(cand)

    kept = ddmin(params, test, assume_original=True)
    if len(kept) != before:
        phases.append(f"query {before} -> {len(kept)}")
        log(f"query {before} -> {len(kept)}")
    req = req.copy()
    req.query = list(kept)
    return req


def _phase_form(req: HttpRequest, accept, phases, log) -> HttpRequest:
    if req.form_body is None or req.json_body is not None:
        return req
    fields = list(req.form_body)
    if not fields:
        return req
    before = len(fields)

    def test(subset: list[tuple[str, str]]) -> bool:
        cand = req.copy()
        cand.form_body = list(subset)
        cand.body = urlencode(subset).encode("utf-8")
        return accept(cand)

    kept = ddmin(fields, test, assume_original=True)
    if len(kept) != before:
        phases.append(f"form {before} -> {len(kept)}")
        log(f"form {before} -> {len(kept)}")
    req = req.copy()
    req.form_body = list(kept)
    req.refresh_body_from_structure()
    return req


def _phase_json(req: HttpRequest, accept, phases, log) -> HttpRequest:
    if req.json_body is None:
        return req
    before = req.component_count()

    def test(value) -> bool:
        cand = req.copy()
        cand.json_body = value
        cand.refresh_body_from_structure()
        return accept(cand)

    shrunk = reduce_json(req.json_body, test)
    req = req.copy()
    req.json_body = shrunk
    req.refresh_body_from_structure()
    after = req.component_count()
    if after != before:
        phases.append(f"json components {before} -> {after}")
        log(f"json reduced ({before} -> {after} components)")
    return req


def _phase_path(req: HttpRequest, accept, phases, log) -> HttpRequest:
    path = req.path or "/"
    if path == "/":
        return req
    # Keep a leading slash. Try dropping trailing segments, never the root.
    parts = [p for p in path.split("/") if p]
    if len(parts) <= 1:
        return req
    current = list(parts)
    # Drop from the front first (e.g. /api/v1/a → /v1/a → /a), then trailing.
    changed = False
    for direction in ("head", "tail"):
        progressed = True
        while progressed and len(current) > 1:
            progressed = False
            trial = current[1:] if direction == "head" else current[:-1]
            cand = req.copy()
            cand.path = "/" + "/".join(trial)
            if accept(cand):
                current = trial
                progressed = True
                changed = True
    if changed:
        req = req.copy()
        req.path = "/" + "/".join(current)
        phases.append(f"path -> {req.path}")
        log(f"path -> {req.path}")
    return req


def _shorten_string(text: str, test: Callable[[str], bool]) -> str:
    if test(""):
        return ""
    lo, hi = 1, len(text)
    best = text
    while lo <= hi:
        mid = (lo + hi) // 2
        if test(text[:mid]):
            best = text[:mid]
            hi = mid - 1
        else:
            lo = mid + 1
    return best


def _phase_query_values(req: HttpRequest, accept, phases, log) -> HttpRequest:
    if not req.query:
        return req
    changed = False
    current = list(req.query)
    for i, (name, value) in enumerate(list(current)):
        if not value:
            continue

        def test(new_val: str, idx: int = i, key: str = name) -> bool:
            cand = req.copy()
            pairs = list(current)
            pairs[idx] = (key, new_val)
            cand.query = pairs
            return accept(cand)

        short = _shorten_string(value, test)
        if short != value:
            current[i] = (name, short)
            changed = True
    if changed:
        req = req.copy()
        req.query = current
        phases.append("shortened query values")
        log("shortened query values")
    return req


def _phase_cookie_values(req: HttpRequest, accept, phases, log) -> HttpRequest:
    if not req.cookies:
        return req
    changed = False
    current = list(req.cookies)
    for i, (name, value) in enumerate(list(current)):
        if not value:
            continue

        def test(new_val: str, idx: int = i, key: str = name) -> bool:
            cand = req.copy()
            pairs = list(current)
            pairs[idx] = (key, new_val)
            cand.cookies = pairs
            return accept(cand)

        short = _shorten_string(value, test)
        if short != value:
            current[i] = (name, short)
            changed = True
    if changed:
        req = req.copy()
        req.cookies = current
        phases.append("shortened cookie values")
        log("shortened cookie values")
    return req


def _phase_header_values(req: HttpRequest, accept, phases, log) -> HttpRequest:
    headers = _reducible_headers(req)
    if not headers:
        return req
    changed = False
    current = list(headers)
    for i, (name, value) in enumerate(list(current)):
        if name.lower() == "content-type":
            continue
        if not value:
            continue

        def test(new_val: str, idx: int = i, key: str = name) -> bool:
            cand = req.copy()
            pairs = list(current)
            pairs[idx] = (key, new_val)
            cand.headers = pairs
            return accept(cand)

        short = _shorten_string(value, test)
        if short != value:
            current[i] = (name, short)
            changed = True
    if changed:
        req = req.copy()
        req.headers = current
        phases.append("shortened header values")
        log("shortened header values")
    return req


def _cleanup_headers(req: HttpRequest, accept, phases, log) -> HttpRequest:
    """Drop Content-Type when the oracle still holds (many servers infer JSON)."""
    if req.header_value("Content-Type") is None:
        return req
    cand = req.copy()
    cand.drop_header("Content-Type")
    # Prevent refresh_body_from_structure from putting it back.
    if accept(cand):
        phases.append("dropped Content-Type")
        log("dropped Content-Type")
        return cand
    return req


def render_result(result: ReductionResult, fmt: str = "curl", pretty: bool = True) -> str:
    if fmt == "http":
        from crashmin.emit import to_raw_http

        return to_raw_http(result.minimized)
    return to_curl(result.minimized, pretty=pretty)
