#!/usr/bin/env python3
"""Hunt the dialect corpus: parse, reduce, compare against header-only."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crashmin.corpus import CASES, PLACEHOLDER, render_case, write_repros  # noqa: E402
from crashmin.detect import parse_input  # noqa: E402
from crashmin.emit import to_curl  # noqa: E402
from crashmin.executor import Executor  # noqa: E402
from crashmin.fixtures import make_server, reset_flake_state  # noqa: E402
from crashmin.reduce import (  # noqa: E402
    _phase_cookies,
    _phase_headers,
    _phase_query,
    reduce_request,
)


def reduce_surface(req, executor):
    """Header / cookie / query deletion only — curlmin's depth."""
    current = req.copy()
    current.refresh_body_from_structure()
    if not executor.interesting(current):
        raise RuntimeError("surface baseline is not interesting")

    def accept(candidate):
        candidate = candidate.copy()
        candidate.refresh_body_from_structure()
        return executor.interesting(candidate)

    log = lambda _m: None
    phases: list[str] = []
    current = _phase_headers(current, accept, phases, log)
    current = _phase_cookies(current, accept, phases, log)
    current = _phase_query(current, accept, phases, log)
    current.refresh_body_from_structure()
    return current, executor.stats.sent


def hunt(base: str) -> list[dict]:
    rows = []
    reset_flake_state()
    for case in CASES:
        text = render_case(case, base)
        parsed = parse_input(text, fmt=case.fmt)
        full_ex = Executor(oracle=case.oracle(), timeout=2.0, confirm=case.confirm)
        full = reduce_request(parsed, full_ex, final_confirm=5)
        surf_ex = Executor(oracle=case.oracle(), timeout=2.0, confirm=case.confirm)
        surface, surf_probes = reduce_surface(parsed, surf_ex)
        structured_smaller = full.minimized_bytes < surface.compact_curl_size()
        rows.append(
            {
                "name": case.name,
                "dialect": case.dialect,
                "fixture": case.fixture,
                "in_bytes": full.original_bytes,
                "structured_out": full.minimized_bytes,
                "surface_out": surface.compact_curl_size(),
                "in_comp": full.original_components,
                "structured_comp": full.minimized_components,
                "surface_comp": surface.component_count(),
                "delta": surface.compact_curl_size() - full.minimized_bytes,
                "structured_wins": structured_smaller,
                "expect_structure_wins": case.expect_structure_wins,
                "confirm": f"{full.final_hits}/{full.final_trials}",
                "ok": full.confirmed,
                "probes": full.probes,
                "surface_probes": surf_probes,
                "minimized": to_curl(full.minimized, pretty=False),
            }
        )
        mark = "WIN" if structured_smaller else "tie/surface"
        print(
            f"{case.name:12} {case.dialect:16} "
            f"{full.original_bytes:6,} → {full.minimized_bytes:4} vs surface {surface.compact_curl_size():6,} "
            f"({mark}) {full.final_hits}/{full.final_trials}",
            flush=True,
        )
    return rows


def write_report(rows: list[dict], path: Path) -> None:
    wins = sum(1 for r in rows if r["structured_wins"])
    expected = [r for r in rows if r["expect_structure_wins"]]
    expected_hits = sum(1 for r in expected if r["structured_wins"])
    lines = [
        "# Corpus hunt",
        "",
        "Realistic Copy-as-cURL / HAR / raw-HTTP repros, replayed only against",
        "the loopback fixture server. **Surface** is header + cookie + query",
        "deletion (curlmin depth). **Structured** is CrashMin, including JSON.",
        "",
        f"Cases: {len(rows)}. Structured strictly smaller: {wins}/{len(rows)}.",
        f"Cases where we *claimed* structure must win: {expected_hits}/{len(expected)}.",
        "",
        "| Case | Dialect | In | Structured | Surface | Saved vs surface | Confirm |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        saved = r["delta"]
        lines.append(
            f"| `{r['name']}` | {r['dialect']} | {r['in_bytes']:,} | "
            f"{r['structured_out']:,} | {r['surface_out']:,} | "
            f"{saved:,} | {r['confirm']} |"
        )
    lines += [
        "",
        "## Minimized curls",
        "",
    ]
    for r in rows:
        lines += [
            f"### {r['name']}",
            "",
            "```bash",
            r["minimized"],
            "```",
            "",
        ]
    lines += [
        "## Reading",
        "",
        "- Fixture A/B/C/D: the crash lives in the JSON. Surface deletion leaves",
        "  the body almost intact. That is the wedge.",
        "- Fixture F: the crash is a cookie + a query param. Surface deletion is",
        "  enough; structured should tie, not invent work.",
        "- Fixture E: `--confirm 3` keeps `X-Flaky-Key` and drops the one-shot flake.",
        "- Dialects: Chrome bash, Firefox `$''`, Windows `^` + `\"\"`, raw HTTP, HAR.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    server = make_server("127.0.0.1", 0, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    out_dir = ROOT / "corpus"
    out_dir.mkdir(exist_ok=True)
    write_repros(out_dir / "repros", PLACEHOLDER)
    try:
        rows = hunt(base)
    finally:
        server.shutdown()
        server.server_close()
    write_report(rows, out_dir / "REPORT.md")
    (out_dir / "_last.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("wrote", out_dir / "REPORT.md")
    claimed = [r for r in rows if r["expect_structure_wins"]]
    if not all(r["ok"] for r in rows):
        return 1
    if not all(r["structured_wins"] for r in claimed):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
