from crashmin.emit import to_curl, to_raw_http
from crashmin.models import HttpRequest, HttpResponse
from crashmin.oracle import compile_oracle, parse_status_spec
from crashmin.safety import SafetyError, check_target, is_loopback_host


def test_status_specs():
    assert parse_status_spec("500").matches(500)
    assert not parse_status_spec("500").matches(501)
    assert parse_status_spec(">=500").matches(503)
    assert not parse_status_spec(">=500").matches(499)
    assert parse_status_spec("5xx").matches(580)
    assert not parse_status_spec("5xx").matches(404)


def test_oracle_and_combination():
    oracle = compile_oracle(statuses=["500"], body_contains=["panic"], body_regexes=["nil pointer"])
    req = HttpRequest()
    ok = HttpResponse(status=500, body=b"panic: nil pointer")
    bad_status = HttpResponse(status=200, body=b"panic: nil pointer")
    bad_body = HttpResponse(status=500, body=b"ok")
    assert oracle.matches(req, ok)
    assert not oracle.matches(req, bad_status)
    assert not oracle.matches(req, bad_body)


def test_oracle_header_and_timeout():
    oracle = compile_oracle(response_headers=["X-Err=boom"])
    req = HttpRequest()
    resp = HttpResponse(status=200, headers=[("X-Err", "boom")], body=b"x")
    assert oracle.matches(req, resp)
    timeout_only = compile_oracle(timeout_is_failure=True)
    timed = HttpResponse(status=0, timed_out=True)
    assert timeout_only.matches(req, timed)
    assert not timeout_only.matches(req, HttpResponse(status=200, body=b"ok"))


def test_emit_curl_and_http():
    req = HttpRequest(method="POST", host="127.0.0.1", port=9, path="/a")
    req.set_header("X-Crash-Token", "letmein")
    req.json_body = {"payload": {"deeply": {"nested": {"trigger": "boom"}}}}
    req.refresh_body_from_structure()
    curl = to_curl(req, pretty=False)
    assert "X-Crash-Token: letmein" in curl
    assert "trigger" in curl
    pretty = to_curl(req, pretty=True)
    assert "-H 'X-Crash-Token: letmein'" in pretty
    assert pretty.count("\\\n") >= 1
    raw = to_raw_http(req)
    assert raw.startswith("POST /a HTTP/1.1")
    assert "Host: 127.0.0.1:9" in raw


def test_safety_blocks_remote():
    req = HttpRequest(host="example.com", path="/")
    try:
        check_target(req, allow_remote=False)
        assert False, "expected SafetyError"
    except SafetyError as exc:
        assert "refusing" in str(exc)
    check_target(req, allow_remote=True)
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
