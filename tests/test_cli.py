from __future__ import annotations

import json
from pathlib import Path

import pytest

from crashmin.cli import main
from crashmin.demo import build_killer_request
from crashmin.emit import to_curl
from crashmin.safety import SafetyError, check_target
from crashmin.models import HttpRequest


def test_cli_parse_only(tmp_path, capsys):
    path = tmp_path / "req.curl"
    path.write_text("curl -H 'X-A: 1' 'http://127.0.0.1:1/x?q=1'\n", encoding="utf-8")
    rc = main([str(path), "--parse-only"])
    assert rc == 0
    out = capsys.readouterr()
    assert "127.0.0.1" in out.out
    assert "X-A" in out.out


def test_cli_requires_oracle(tmp_path, capsys):
    path = tmp_path / "req.curl"
    path.write_text("curl http://127.0.0.1/x\n", encoding="utf-8")
    rc = main([str(path)])
    assert rc == 2
    assert "oracle" in capsys.readouterr().err.lower()


def test_cli_blocks_remote(tmp_path, capsys):
    path = tmp_path / "req.curl"
    path.write_text("curl http://example.com/x\n", encoding="utf-8")
    rc = main([str(path), "--status", "500"])
    assert rc == 3
    assert "refusing" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_reduces_fixture_a(tmp_path, fixture_server, capsys):
    req = build_killer_request(fixture_server)
    path = tmp_path / "killer.curl"
    path.write_text(to_curl(req, pretty=True), encoding="utf-8")
    rc = main(
        [
            str(path),
            "--status",
            "500",
            "--body-regex",
            "panic: nil pointer",
            "--final-confirm",
            "3",
            "--compact",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "X-Crash-Token: letmein" in captured.out
    assert "trigger" in captured.out
    assert "same failure: YES" in captured.err


@pytest.mark.integration
def test_cli_json_contract(tmp_path, fixture_server, capsys):
    req = build_killer_request(fixture_server)
    path = tmp_path / "killer.curl"
    out = tmp_path / "min.curl"
    path.write_text(to_curl(req, pretty=True), encoding="utf-8")
    rc = main(
        [
            str(path),
            "--status",
            "500",
            "--body-regex",
            "panic: nil pointer",
            "--final-confirm",
            "3",
            "--json",
            "--quiet",
            "-o",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["schema"] == 1
    assert payload["exit"] == 0
    assert payload["confirmation"]["same_failure"] is True
    assert payload["confirmation"]["hits"] == 3
    assert "trigger" in payload["minimized"]["curl"]
    assert "x-crash-token" in payload["minimized"]["curl"].lower()
    assert payload["reduction"]["percent"] > 90
    assert "letmein" in out.read_text(encoding="utf-8")
    # stdout is only JSON — no second copy of the curl hanging off it
    assert captured.out.strip().startswith("{")


def test_cli_raw_http_and_har_roundtrip(tmp_path, capsys):
    raw = tmp_path / "req.http"
    raw.write_text(
        "GET /f HTTP/1.1\nHost: 127.0.0.1:1\nCookie: session=s3cret\n\n",
        encoding="utf-8",
    )
    assert main([str(raw), "--format", "http", "--parse-only"]) == 0
    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "http://127.0.0.1:1/f?need=1",
                        "headers": [],
                    }
                }
            ]
        }
    }
    hpath = tmp_path / "one.har"
    hpath.write_text(json.dumps(har), encoding="utf-8")
    assert main([str(hpath), "--format", "har", "--parse-only"]) == 0


def test_check_target_loopback_ok():
    req = HttpRequest(host="127.0.0.1", path="/")
    check_target(req)
    with pytest.raises(SafetyError):
        check_target(HttpRequest(host="93.184.216.34", path="/"))
