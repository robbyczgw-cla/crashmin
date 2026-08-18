"""Stable JSON report for agents and scripts.

Stdout is one JSON object. Field names and exit codes are the contract;
do not rename them in a patch release.
"""

from __future__ import annotations

import json
from typing import Any

from crashmin.version import __version__
from crashmin.emit import to_curl, to_raw_http
from crashmin.models import HttpRequest
from crashmin.reduce import ReductionResult

# Exit codes (also documented in --help and docs/agents.md).
EXIT_OK = 0
EXIT_NOT_INTERESTING = 1
EXIT_USAGE = 2
EXIT_SAFETY = 3
EXIT_ABORTED = 4
EXIT_CONFIRM_FAILED = 5

SCHEMA_VERSION = 1

RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/robbyczgw-cla/crashmin/docs/result.schema.json",
    "title": "CrashMin result",
    "type": "object",
    "required": ["ok", "version", "schema", "exit"],
    "properties": {
        "ok": {"type": "boolean"},
        "version": {"type": "string"},
        "schema": {"type": "integer", "const": SCHEMA_VERSION},
        "exit": {"type": "integer"},
        "error": {"type": ["string", "null"]},
        "error_code": {
            "type": ["string", "null"],
            "enum": [
                None,
                "usage",
                "parse",
                "not_interesting",
                "safety",
                "aborted",
                "confirm_failed",
            ],
        },
        "parse_only": {"type": "boolean"},
        "oracle": {"type": "array", "items": {"type": "string"}},
        "original": {"type": "object"},
        "minimized": {"type": "object"},
        "reduction": {"type": "object"},
        "confirmation": {"type": "object"},
        "search": {"type": "object"},
        "aborted": {"type": ["string", "null"]},
    },
}


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def error_report(*, exit_code: int, error: str, error_code: str) -> dict[str, Any]:
    return {
        "ok": False,
        "version": __version__,
        "schema": SCHEMA_VERSION,
        "exit": exit_code,
        "error": error,
        "error_code": error_code,
    }


def parse_report(req: HttpRequest) -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "schema": SCHEMA_VERSION,
        "exit": EXIT_OK,
        "parse_only": True,
        "error": None,
        "error_code": None,
        "method": req.method.upper(),
        "url": req.url(),
        "target": req.log_target(),
        "headers": len(req.headers),
        "cookies": len(req.cookies),
        "query": len(req.query),
        "body_bytes": len(req.body or b""),
        "bytes": req.compact_curl_size(),
        "components": req.component_count(),
        "curl": to_curl(req, pretty=False),
    }


def result_report(
    result: ReductionResult,
    *,
    oracle: list[str],
    confirm: int,
    exit_code: int,
) -> dict[str, Any]:
    same = result.confirmed if result.final_trials else None
    return {
        "ok": exit_code == EXIT_OK,
        "version": __version__,
        "schema": SCHEMA_VERSION,
        "exit": exit_code,
        "error": result.aborted,
        "error_code": "aborted" if result.aborted else (
            "confirm_failed" if exit_code == EXIT_CONFIRM_FAILED else None
        ),
        "oracle": list(oracle),
        "original": {
            "bytes": result.original_bytes,
            "components": result.original_components,
            "method": result.original.method.upper(),
            "target": result.original.log_target(),
            "curl": to_curl(result.original, pretty=False),
        },
        "minimized": {
            "bytes": result.minimized_bytes,
            "components": result.minimized_components,
            "method": result.minimized.method.upper(),
            "url": result.minimized.url(),
            "target": result.minimized.log_target(),
            "curl": to_curl(result.minimized, pretty=False),
            "http": to_raw_http(result.minimized),
        },
        "reduction": {
            "ratio": round(result.ratio, 6),
            "percent": round(result.ratio * 100, 2),
            "bytes_saved": result.original_bytes - result.minimized_bytes,
        },
        "confirmation": {
            "hits": result.final_hits,
            "trials": result.final_trials,
            "same_failure": same,
        },
        "search": {
            "probes": result.probes,
            "cache_hits": result.cache_hits,
            "confirm": confirm,
            "phases": list(result.phases),
        },
        "aborted": result.aborted,
    }


def decide_exit(result: ReductionResult) -> int:
    if result.aborted:
        return EXIT_ABORTED
    if result.final_trials > 0 and not result.confirmed:
        return EXIT_CONFIRM_FAILED
    return EXIT_OK
