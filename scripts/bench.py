#!/usr/bin/env python3
"""Run the six fixtures and write benchmarks/report.md."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crashmin.demo import (  # noqa: E402
    build_killer_request,
    fixture_b_request,
    fixture_c_request,
    fixture_d_request,
    fixture_e_request,
    fixture_f_request,
)
from crashmin.executor import Executor  # noqa: E402
from crashmin.fixtures import make_server  # noqa: E402
from crashmin.oracle import compile_oracle  # noqa: E402
from crashmin.reduce import reduce_request  # noqa: E402


def main() -> int:
    server = make_server("127.0.0.1", 0, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"

    cases = [
        (
            "A nested JSON + header (killer demo)",
            build_killer_request(base),
            compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"]),
            1,
            20,
        ),
        (
            "B pair fields",
            fixture_b_request(base),
            compile_oracle(statuses=["500"], body_contains=["pair collision"]),
            1,
            5,
        ),
        (
            "C array item",
            fixture_c_request(base),
            compile_oracle(statuses=["500"], body_contains=["kind=evil"]),
            1,
            5,
        ),
        (
            "D body-text oracle (HTTP 200)",
            fixture_d_request(base),
            compile_oracle(body_contains=["INTERNAL ERROR: widget exploded"]),
            1,
            5,
        ),
        (
            "E flaky / confirmation",
            fixture_e_request(base),
            compile_oracle(statuses=["500"], body_contains=["flaky-boom"]),
            3,
            5,
        ),
        (
            "F cookies + query",
            fixture_f_request(base),
            compile_oracle(statuses=["500"], body_contains=["session gate"]),
            1,
            5,
        ),
    ]

    rows = []
    for name, req, oracle, confirm, final in cases:
        ex = Executor(oracle=oracle, timeout=2.0, confirm=confirm)
        result = reduce_request(req, ex, final_confirm=final)
        rows.append(
            {
                "name": name,
                "in_bytes": result.original_bytes,
                "out_bytes": result.minimized_bytes,
                "in_comp": result.original_components,
                "out_comp": result.minimized_components,
                "ratio": result.ratio,
                "probes": result.probes,
                "confirm": f"{result.final_hits}/{result.final_trials}",
                "ok": result.confirmed,
            }
        )
        print(name, *result.summary_lines(), f"probes={result.probes}", sep=" | ")

    server.shutdown()
    server.server_close()

    out_dir = ROOT / "benchmarks"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "_last.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    lines = [
        "# Reduction report",
        "",
        "Measured against the in-repo fixture server on loopback.",
        "Bytes are compact-curl encodings of the parsed request.",
        "",
        "| Case | In | Out | Components | Reduction | Probes | Confirm |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['in_bytes']:,} | {row['out_bytes']:,} | "
            f"{row['in_comp']} → {row['out_comp']} | {row['ratio']*100:.2f}% | "
            f"{row['probes']} | {row['confirm']} |"
        )
    killer = rows[0]
    lines += [
        "",
        "## Killer demo",
        "",
        "```",
        f"{killer['in_bytes']:,} bytes -> {killer['out_bytes']:,} bytes",
        f"{killer['in_comp']} components -> {killer['out_comp']}",
        f"{killer['ratio']*100:.2f}% reduction",
        f"same failure: {'YES' if killer['ok'] else 'NO'} ({killer['confirm']})",
        "```",
        "",
        "Structured JSON reduction is what takes fixture A from dozens of",
        "object keys down to `payload.deeply.nested.trigger`. Header/query",
        "deletion alone cannot do that.",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", out_dir / "report.md")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
