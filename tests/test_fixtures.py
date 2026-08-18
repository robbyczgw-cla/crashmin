from __future__ import annotations

import pytest

from crashmin.fixtures import reset_flake_state
from crashmin.demo import (
    build_killer_request,
    fixture_b_request,
    fixture_c_request,
    fixture_d_request,
    fixture_e_request,
    fixture_f_request,
)
from crashmin.executor import Executor
from crashmin.oracle import compile_oracle
from crashmin.reduce import reduce_request


def _run(req, oracle, confirm=1, final_confirm=0):
    ex = Executor(oracle=oracle, timeout=2.0, confirm=confirm)
    return reduce_request(req, ex, final_confirm=final_confirm)


@pytest.mark.integration
def test_fixture_a_nested_json_and_header(fixture_server):
    req = build_killer_request(fixture_server)
    assert req.compact_curl_size() >= 15_000
    assert req.component_count() >= 50
    oracle = compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"])
    result = _run(req, oracle, final_confirm=5)
    names = {n.lower() for n, _ in result.minimized.headers}
    assert "x-crash-token" in names
    assert result.minimized.header_value("X-Crash-Token") == "letmein"
    assert result.minimized.json_body == {
        "payload": {"deeply": {"nested": {"trigger": "boom"}}}
    }
    assert result.minimized.cookies == []
    assert result.minimized.query == []
    assert result.minimized_bytes < 200
    assert result.ratio > 0.98
    assert result.final_hits == 5


@pytest.mark.integration
def test_fixture_b_pair_fields(fixture_server):
    req = fixture_b_request(fixture_server)
    oracle = compile_oracle(statuses=["500"], body_contains=["pair collision"])
    result = _run(req, oracle)
    assert result.minimized.json_body == {"alpha": "one", "beta": "two"}


@pytest.mark.integration
def test_fixture_c_array(fixture_server):
    req = fixture_c_request(fixture_server)
    oracle = compile_oracle(statuses=["500"], body_contains=["kind=evil"])
    result = _run(req, oracle)
    assert result.minimized.json_body == {"items": [{"kind": "evil"}]}


@pytest.mark.integration
def test_fixture_d_body_oracle(fixture_server):
    req = fixture_d_request(fixture_server)
    oracle = compile_oracle(body_contains=["INTERNAL ERROR: widget exploded"])
    result = _run(req, oracle)
    body = result.minimized.json_body
    assert isinstance(body, dict)
    assert "widget" in body
    assert "id" in body["widget"]
    assert "note" not in body


@pytest.mark.integration
def test_fixture_e_confirmation_keeps_real_key(fixture_server):
    req = fixture_e_request(fixture_server)
    oracle = compile_oracle(statuses=["500"], body_contains=["flaky-boom"])
    result = _run(req, oracle, confirm=3)
    assert result.minimized.header_value("X-Flaky-Key") == "yes"
    # The one-shot flake header is not sufficient under --confirm 3.
    assert result.minimized.header_value("X-Sometimes") in (None, "1")


@pytest.mark.integration
def test_fixture_e_without_confirm_can_keep_flake_only(fixture_server):
    """Document why --confirm exists: a single 500 is not enough."""
    reset_flake_state()
    req = fixture_e_request(fixture_server)
    req.drop_header("X-Flaky-Key")
    oracle = compile_oracle(statuses=["500"], body_contains=["flaky-boom"])
    ex = Executor(oracle=oracle, timeout=2.0, confirm=1)
    # First send flakes to 500.
    assert ex.interesting(req) is True
    # Second send of the same fingerprint is cached as interesting — this is
    # why confirm>1 bypasses the response cache.
    ex2 = Executor(oracle=oracle, timeout=2.0, confirm=3)
    assert ex2.interesting(req) is False


@pytest.mark.integration
def test_fixture_f_cookies_and_query(fixture_server):
    req = fixture_f_request(fixture_server)
    oracle = compile_oracle(statuses=["500"], body_contains=["session gate"])
    result = _run(req, oracle)
    assert result.minimized.cookies == [("session", "s3cret")]
    assert result.minimized.query == [("need", "1")]
