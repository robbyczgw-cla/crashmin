"""Send candidate requests and cache results."""

from __future__ import annotations

import http.client
import ssl
import time
from dataclasses import dataclass, field

from crashmin.models import HttpRequest, HttpResponse
from crashmin.oracle import Oracle


class BudgetExceeded(RuntimeError):
    def __init__(self, used: int, limit: int) -> None:
        super().__init__(f"request budget exceeded ({used}/{limit})")
        self.used = used
        self.limit = limit


@dataclass
class ProbeStats:
    sent: int = 0
    cache_hits: int = 0
    interesting: int = 0
    uninteresting: int = 0
    timeouts: int = 0
    errors: int = 0


@dataclass
class Executor:
    oracle: Oracle
    timeout: float = 5.0
    confirm: int = 1
    max_requests: int | None = None
    follow_redirects: bool = False
    stats: ProbeStats = field(default_factory=ProbeStats)
    _response_cache: dict[str, HttpResponse] = field(default_factory=dict)
    _interesting_cache: dict[str, bool] = field(default_factory=dict)

    def send(self, req: HttpRequest, *, use_cache: bool = True) -> HttpResponse:
        key = req.fingerprint()
        if use_cache and key in self._response_cache:
            self.stats.cache_hits += 1
            return self._response_cache[key]
        if self.max_requests is not None and self.stats.sent >= self.max_requests:
            raise BudgetExceeded(self.stats.sent, self.max_requests)
        response = _http_send(req, timeout=self.timeout)
        self.stats.sent += 1
        if response.timed_out:
            self.stats.timeouts += 1
        if response.error and not response.timed_out:
            self.stats.errors += 1
        if use_cache:
            self._response_cache[key] = response
        return response

    def interesting(self, req: HttpRequest) -> bool:
        key = req.fingerprint()
        if key in self._interesting_cache:
            self.stats.cache_hits += 1
            return self._interesting_cache[key]

        n = max(1, self.confirm)
        ok = True
        last: HttpResponse | None = None
        for trial in range(n):
            # Confirmation trials must not share a single cached response:
            # a one-off flake would otherwise become "always interesting".
            last = self.send(req, use_cache=(n == 1))
            if not self.oracle.matches(req, last):
                ok = False
                break
        if ok:
            self.stats.interesting += 1
        else:
            self.stats.uninteresting += 1
        self._interesting_cache[key] = ok
        return ok

    def confirm_only(self, req: HttpRequest, n: int) -> tuple[int, int]:
        """Send n fresh requests and count how many match the oracle."""
        hits = 0
        for _ in range(n):
            response = self.send(req, use_cache=False)
            if self.oracle.matches(req, response):
                hits += 1
        return hits, n


def _target_path(req: HttpRequest) -> str:
    from urllib.parse import urlencode

    path = req.path or "/"
    if req.query:
        return f"{path}?{urlencode(req.query, doseq=True)}"
    return path


def _http_send(req: HttpRequest, timeout: float) -> HttpResponse:
    started = time.perf_counter()
    conn: http.client.HTTPConnection | None = None
    try:
        if req.scheme == "https":
            ctx = ssl._create_unverified_context() if req.insecure else ssl.create_default_context()
            conn = http.client.HTTPSConnection(req.host, req.effective_port(), timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(req.host, req.effective_port(), timeout=timeout)
        headers = {name: value for name, value in req.wire_headers()}
        body = req.body if req.body else None
        conn.request(req.method.upper(), _target_path(req), body=body, headers=headers)
        resp = conn.getresponse()
        payload = resp.read()
        elapsed = (time.perf_counter() - started) * 1000
        return HttpResponse(
            status=resp.status,
            headers=list(resp.getheaders()),
            body=payload,
            elapsed_ms=elapsed,
        )
    except TimeoutError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpResponse(status=0, timed_out=True, error=str(exc) or "timeout", elapsed_ms=elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        name = type(exc).__name__
        if name in {"timeout", "TimeoutError"} or "timed out" in str(exc).lower():
            return HttpResponse(status=0, timed_out=True, error=str(exc), elapsed_ms=elapsed)
        return HttpResponse(status=0, error=f"{name}: {exc}", elapsed_ms=elapsed)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
