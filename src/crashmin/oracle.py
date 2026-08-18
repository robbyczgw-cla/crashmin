"""Failure oracles: user-defined 'still broken' predicates."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from crashmin.models import HttpRequest, HttpResponse


class OracleError(ValueError):
    pass


@dataclass
class StatusSpec:
    """A status matcher: exact, family (5xx), or comparison (>=500)."""

    raw: str
    kind: str
    value: int = 0

    def matches(self, status: int) -> bool:
        if self.kind == "exact":
            return status == self.value
        if self.kind == "family":
            return status // 100 == self.value
        if self.kind == "ge":
            return status >= self.value
        if self.kind == "le":
            return status <= self.value
        if self.kind == "gt":
            return status > self.value
        if self.kind == "lt":
            return status < self.value
        return False


def parse_status_spec(raw: str) -> StatusSpec:
    text = raw.strip()
    if not text:
        raise OracleError("empty --status spec")
    family = re.fullmatch(r"([1-5])xx", text, flags=re.IGNORECASE)
    if family:
        return StatusSpec(raw=text, kind="family", value=int(family.group(1)))
    cmp_m = re.fullmatch(r"(>=|<=|>|<)\s*(\d{3})", text)
    if cmp_m:
        op = {">>": "gt", ">=": "ge", "<=": "le", "<": "lt", ">": "gt"}[cmp_m.group(1)]
        return StatusSpec(raw=text, kind=op, value=int(cmp_m.group(2)))
    if re.fullmatch(r"\d{3}", text):
        return StatusSpec(raw=text, kind="exact", value=int(text))
    raise OracleError(
        f"invalid --status {raw!r} (use 500, >=500, >499, 5xx)"
    )


@dataclass
class HeaderSpec:
    name: str
    value: str | None
    regex: re.Pattern[str] | None = None

    def matches(self, response: HttpResponse) -> bool:
        got = response.header(self.name)
        if got is None:
            return False
        if self.regex is not None:
            return self.regex.search(got) is not None
        if self.value is None:
            return True
        return got == self.value


def parse_header_spec(raw: str) -> HeaderSpec:
    if "=" not in raw and ":" not in raw:
        return HeaderSpec(name=raw.strip(), value=None)
    sep = "=" if "=" in raw else ":"
    name, value = raw.split(sep, 1)
    name = name.strip()
    value = value.strip()
    if not name:
        raise OracleError(f"invalid --header spec {raw!r}")
    return HeaderSpec(name=name, value=value)


OracleFn = Callable[[HttpRequest, HttpResponse], bool]


@dataclass
class Oracle:
    """AND-combined failure oracle.

    A candidate is interesting only when every configured check holds.
    If no built-in check is configured, a custom script or callable is required.
    """

    statuses: list[StatusSpec] = field(default_factory=list)
    body_contains: list[str] = field(default_factory=list)
    body_regexes: list[re.Pattern[str]] = field(default_factory=list)
    response_headers: list[HeaderSpec] = field(default_factory=list)
    timeout_is_failure: bool = False
    script: str | None = None
    predicate: OracleFn | None = None

    def describe(self) -> list[str]:
        bits: list[str] = []
        for spec in self.statuses:
            bits.append(f"status {spec.raw}")
        for text in self.body_contains:
            bits.append(f"body contains {text!r}")
        for rx in self.body_regexes:
            bits.append(f"body ~ /{rx.pattern}/")
        for header in self.response_headers:
            if header.value is None:
                bits.append(f"header {header.name} present")
            else:
                bits.append(f"header {header.name}={header.value}")
        if self.timeout_is_failure:
            bits.append("timeout is failure")
        if self.script:
            bits.append(f"script {self.script}")
        if self.predicate is not None:
            bits.append("custom predicate")
        return bits

    def is_configured(self) -> bool:
        return bool(
            self.statuses
            or self.body_contains
            or self.body_regexes
            or self.response_headers
            or self.timeout_is_failure
            or self.script
            or self.predicate is not None
        )

    def matches(self, request: HttpRequest, response: HttpResponse) -> bool:
        if not self.is_configured():
            raise OracleError("no oracle configured; pass --status, --body-contains, --body-regex, or --oracle")

        if self.timeout_is_failure:
            if not response.timed_out and not _builtin_ok(self, request, response):
                # timeout-is-failure is OR'd with the other built-ins when those exist;
                # if only timeout is configured, timed_out must be true.
                if not (
                    self.statuses
                    or self.body_contains
                    or self.body_regexes
                    or self.response_headers
                    or self.script
                    or self.predicate
                ):
                    return False
            elif response.timed_out and not (
                self.statuses
                or self.body_contains
                or self.body_regexes
                or self.response_headers
                or self.script
                or self.predicate
            ):
                return True

        if response.timed_out:
            return bool(self.timeout_is_failure) and _rest_vacuously_ok(self)

        if self.statuses and not all(spec.matches(response.status) for spec in self.statuses):
            return False
        if self.body_contains:
            text = response.body_text
            if not all(needle in text for needle in self.body_contains):
                return False
        if self.body_regexes:
            text = response.body_text
            if not all(rx.search(text) for rx in self.body_regexes):
                return False
        if self.response_headers and not all(h.matches(response) for h in self.response_headers):
            return False
        if self.script is not None and not _run_script(self.script, request, response):
            return False
        if self.predicate is not None and not self.predicate(request, response):
            return False
        return True


def _builtin_ok(oracle: Oracle, request: HttpRequest, response: HttpResponse) -> bool:
    clone = Oracle(
        statuses=oracle.statuses,
        body_contains=oracle.body_contains,
        body_regexes=oracle.body_regexes,
        response_headers=oracle.response_headers,
        timeout_is_failure=False,
        script=oracle.script,
        predicate=oracle.predicate,
    )
    if not (
        clone.statuses
        or clone.body_contains
        or clone.body_regexes
        or clone.response_headers
        or clone.script
        or clone.predicate
    ):
        return False
    return clone.matches(request, response)


def _rest_vacuously_ok(oracle: Oracle) -> bool:
    """When the request timed out, other checks that need a body cannot hold
    unless they were not configured."""
    if oracle.statuses or oracle.body_contains or oracle.body_regexes or oracle.response_headers:
        return False
    return True


def _run_script(script: str, request: HttpRequest, response: HttpResponse) -> bool:
    with tempfile.TemporaryDirectory(prefix="crashmin-oracle-") as tmp:
        body_path = os.path.join(tmp, "body")
        with open(body_path, "wb") as handle:
            handle.write(response.body)
        headers_path = os.path.join(tmp, "headers")
        with open(headers_path, "w", encoding="utf-8") as handle:
            handle.write(f"{request.method.upper()} {request.url()}\n")
            handle.write(f"HTTP {response.status}\n")
            for name, value in response.headers:
                handle.write(f"{name}: {value}\n")
        env = os.environ.copy()
        env.update(
            {
                "CRASHMIN_STATUS": str(response.status),
                "CRASHMIN_URL": request.url(),
                "CRASHMIN_METHOD": request.method.upper(),
                "CRASHMIN_BODY_FILE": body_path,
                "CRASHMIN_HEADERS_FILE": headers_path,
                "CRASHMIN_TIMED_OUT": "1" if response.timed_out else "0",
                "CRASHMIN_ERROR": response.error or "",
            }
        )
        try:
            completed = subprocess.run(
                [script, body_path],
                env=env,
                cwd=os.getcwd(),
                timeout=30,
                check=False,
                capture_output=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0


def compile_oracle(
    *,
    statuses: list[str] | None = None,
    body_contains: list[str] | None = None,
    body_regexes: list[str] | None = None,
    response_headers: list[str] | None = None,
    timeout_is_failure: bool = False,
    script: str | None = None,
    predicate: OracleFn | None = None,
) -> Oracle:
    compiled_regexes: list[re.Pattern[str]] = []
    for raw in body_regexes or []:
        try:
            compiled_regexes.append(re.compile(raw))
        except re.error as exc:
            raise OracleError(f"invalid --body-regex {raw!r}: {exc}") from exc
    oracle = Oracle(
        statuses=[parse_status_spec(s) for s in (statuses or [])],
        body_contains=list(body_contains or []),
        body_regexes=compiled_regexes,
        response_headers=[parse_header_spec(h) for h in (response_headers or [])],
        timeout_is_failure=timeout_is_failure,
        script=script,
        predicate=predicate,
    )
    if script is not None and not os.path.exists(script):
        raise OracleError(f"oracle script not found: {script}")
    if not oracle.is_configured():
        raise OracleError(
            "no oracle configured; pass --status, --body-contains, --body-regex, or --oracle"
        )
    return oracle
