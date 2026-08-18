"""CrashMin command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crashmin import __version__
from crashmin.detect import DetectError, parse_input
from crashmin.executor import Executor
from crashmin.oracle import OracleError, compile_oracle
from crashmin.reduce import reduce_request, render_result
from crashmin.safety import SafetyError, check_target, warn_mutating


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crashmin",
        description=(
            "Reduce an HTTP request to the smallest ready-to-paste reproducer "
            "that still satisfies a failure oracle."
        ),
        epilog=(
            "SAFETY: CrashMin sends many real requests. Use a local or staging "
            "target. See docs/safety.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="curl command, raw HTTP request, or HAR file (or - for stdin)")
    p.add_argument("--version", action="version", version=f"crashmin {__version__}")

    src = p.add_argument_group("input")
    src.add_argument("--format", choices=["auto", "curl", "http", "har"], default="auto")
    src.add_argument("--har-index", type=int, default=0, help="which HAR entry to reduce (default 0)")

    ora = p.add_argument_group("oracle (AND-combined; at least one required)")
    ora.add_argument(
        "--status",
        action="append",
        default=[],
        metavar="SPEC",
        help="interesting status: 500, >=500, >499, 5xx (repeatable)",
    )
    ora.add_argument(
        "--body-contains",
        action="append",
        default=[],
        metavar="TEXT",
        help="response body must contain TEXT (repeatable)",
    )
    ora.add_argument(
        "--body-regex",
        action="append",
        default=[],
        metavar="REGEX",
        help="response body must match REGEX (repeatable)",
    )
    ora.add_argument(
        "--header",
        action="append",
        default=[],
        dest="response_headers",
        metavar="NAME=VALUE",
        help="response header must match (NAME or NAME=VALUE)",
    )
    ora.add_argument(
        "--timeout-is-failure",
        action="store_true",
        help="treat a client-side timeout as interesting",
    )
    ora.add_argument(
        "--oracle",
        metavar="SCRIPT",
        help="custom interestingness script (exit 0 = still broken)",
    )

    run = p.add_argument_group("execution")
    run.add_argument("--confirm", type=int, default=1, metavar="N", help="require N/N reproductions (default 1)")
    run.add_argument(
        "--final-confirm",
        type=int,
        default=0,
        metavar="N",
        help="re-send the minimized request N times at the end (0 = skip)",
    )
    run.add_argument("--timeout", type=float, default=5.0, help="per-request timeout in seconds")
    run.add_argument("--max-requests", type=int, default=None, help="stop after this many HTTP calls")
    run.add_argument("--allow-remote", action="store_true", help="permit non-loopback targets (dangerous)")
    run.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    run.add_argument("--no-path", action="store_true", help="do not reduce URL path segments")

    out = p.add_argument_group("output")
    out.add_argument("--output-format", choices=["curl", "http"], default="curl")
    out.add_argument("-o", "--output", help="write minimized request to FILE")
    out.add_argument("--compact", action="store_true", help="emit a single-line curl command")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--quiet", action="store_true", help="only print the minimized request")
    out.add_argument(
        "--parse-only",
        action="store_true",
        help="parse and print a summary; do not send anything",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = _read_input(args.input)
        req = parse_input(text, fmt=args.format, har_index=args.har_index)
    except (OSError, DetectError) as exc:
        print(f"crashmin: {exc}", file=sys.stderr)
        return 2

    if args.insecure:
        req.insecure = True

    if args.parse_only:
        _print_parse_summary(req)
        from crashmin.emit import to_curl

        print(to_curl(req, pretty=not args.compact))
        return 0

    try:
        oracle = compile_oracle(
            statuses=args.status,
            body_contains=args.body_contains,
            body_regexes=args.body_regex,
            response_headers=args.response_headers,
            timeout_is_failure=args.timeout_is_failure,
            script=args.oracle,
        )
    except OracleError as exc:
        print(f"crashmin: {exc}", file=sys.stderr)
        return 2

    try:
        check_target(req, allow_remote=args.allow_remote)
    except SafetyError as exc:
        print(f"crashmin: {exc}", file=sys.stderr)
        return 3

    if not args.quiet:
        warn = warn_mutating(req)
        if warn:
            print(f"crashmin: warning: {warn}", file=sys.stderr)
        print(
            f"crashmin: parsed {req.compact_curl_size():,} byte request "
            f"({req.component_count()} components) -> {req.method} {req.url()}",
            file=sys.stderr,
        )
        print(f"crashmin: oracle: {', '.join(oracle.describe())}", file=sys.stderr)

    executor = Executor(
        oracle=oracle,
        timeout=args.timeout,
        confirm=max(1, args.confirm),
        max_requests=args.max_requests,
    )

    def log(msg: str) -> None:
        if args.verbose and not args.quiet:
            print(f"crashmin: {msg}", file=sys.stderr)

    try:
        result = reduce_request(
            req,
            executor,
            reduce_path=not args.no_path,
            final_confirm=args.final_confirm,
            listener=log,
        )
    except RuntimeError as exc:
        print(f"crashmin: {exc}", file=sys.stderr)
        return 1

    rendered = render_result(result, fmt=args.output_format, pretty=not args.compact)
    if not args.quiet:
        print("crashmin: " + " | ".join(result.summary_lines()), file=sys.stderr)
        print(
            f"crashmin: probes={result.probes} cache_hits={result.cache_hits} "
            f"confirm={args.confirm}",
            file=sys.stderr,
        )
        if result.aborted:
            print(f"crashmin: {result.aborted}", file=sys.stderr)
        for line in result.summary_lines():
            print(line, file=sys.stderr)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not result.aborted else 4


def _print_parse_summary(req) -> None:
    print(
        f"crashmin: {req.method} {req.url()} "
        f"headers={len(req.headers)} cookies={len(req.cookies)} "
        f"query={len(req.query)} body={len(req.body or b'')} "
        f"components={req.component_count()} bytes={req.compact_curl_size()}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
