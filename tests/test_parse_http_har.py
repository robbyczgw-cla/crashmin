import json

from crashmin.detect import parse_input, sniff
from crashmin.parse_har import parse_har
from crashmin.parse_http import parse_raw_http


def test_raw_http_post():
    raw = (
        "POST /v1/items?x=1 HTTP/1.1\r\n"
        "Host: 127.0.0.1:9999\r\n"
        "Content-Type: application/json\r\n"
        "Cookie: a=1; b=2\r\n"
        "Content-Length: 9\r\n"
        "\r\n"
        '{"k":1}'
    )
    req = parse_raw_http(raw)
    assert req.method == "POST"
    assert req.host == "127.0.0.1"
    assert req.port == 9999
    assert req.path == "/v1/items"
    assert req.query == [("x", "1")]
    assert req.cookies == [("a", "1"), ("b", "2")]
    assert req.json_body == {"k": 1}


def test_raw_http_absolute_form():
    raw = "GET http://example.test/abs HTTP/1.1\r\nHost: ignored\r\n\r\n"
    req = parse_raw_http(raw)
    assert req.host == "example.test"
    assert req.path == "/abs"


def test_sniff_formats():
    assert sniff("curl http://x") == "curl"
    assert sniff("POST / HTTP/1.1\nHost: x\n\n") == "http"
    assert sniff('{"log":{"entries":[]}}') == "har"


def test_parse_har_one_entry():
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "test", "version": "1"},
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": "http://127.0.0.1:8/har?q=1",
                        "headers": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "X-A", "value": "b"},
                            {"name": "Cookie", "value": "s=1"},
                        ],
                        "postData": {"mimeType": "application/json", "text": '{"z":2}'},
                    }
                }
            ],
        }
    }
    req = parse_har(json.dumps(har))
    assert req.method == "POST"
    assert req.path == "/har"
    assert req.query == [("q", "1")]
    assert req.json_body == {"z": 2}
    assert ("s", "1") in req.cookies
    assert req.header_value("X-A") == "b"


def test_parse_input_auto_curl():
    req = parse_input("curl -H 'X-A: 1' http://127.0.0.1/p")
    assert req.header_value("X-A") == "1"
