from __future__ import annotations

import json

from crashmin.cli import main
from crashmin.models import HttpRequest
from crashmin.reduce import ReductionResult
from crashmin.report import (
    EXIT_ABORTED,
    EXIT_CONFIRM_FAILED,
    EXIT_OK,
    RESULT_SCHEMA,
    decide_exit,
    parse_report,
)


def test_schema_flag(capsys):
    assert main(["--schema"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == RESULT_SCHEMA["title"]
    assert payload["properties"]["schema"]["const"] == 1


def test_missing_input_is_usage(capsys):
    assert main([]) == 2
    assert "required" in capsys.readouterr().err.lower()


def test_json_usage_error_is_object(capsys):
    assert main(["--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == "usage"
    assert payload["exit"] == 2
    assert payload["schema"] == 1


def test_json_safety(tmp_path, capsys):
    path = tmp_path / "r.curl"
    path.write_text("curl http://example.com/x\n", encoding="utf-8")
    assert main([str(path), "--status", "500", "--json"]) == 3
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["error_code"] == "safety"
    assert "example.com" not in captured.err or "query" not in captured.err


def test_parse_only_json(tmp_path, capsys):
    path = tmp_path / "r.curl"
    path.write_text("curl -H 'X-A: 1' 'http://127.0.0.1:1/x?secret=nope'\n", encoding="utf-8")
    assert main([str(path), "--parse-only", "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["parse_only"] is True
    assert payload["method"] == "GET"
    assert "secret=nope" not in captured.err
    assert payload["query"] == 1


def test_decide_exit():
    base = dict(
        original=HttpRequest(),
        minimized=HttpRequest(),
        original_bytes=10,
        minimized_bytes=3,
        original_components=4,
        minimized_components=1,
        probes=1,
        cache_hits=0,
    )
    ok = ReductionResult(**base, final_hits=5, final_trials=5)
    assert decide_exit(ok) == EXIT_OK
    bad = ReductionResult(**base, final_hits=3, final_trials=5)
    assert decide_exit(bad) == EXIT_CONFIRM_FAILED
    dead = ReductionResult(**base, aborted="budget")
    assert decide_exit(dead) == EXIT_ABORTED


def test_parse_report_shape():
    req = HttpRequest(method="POST", path="/a", host="127.0.0.1")
    payload = parse_report(req)
    assert payload["ok"] is True
    assert "curl" in payload
    assert payload["schema"] == 1
