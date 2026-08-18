from __future__ import annotations

import pytest

from crashmin.corpus import CASES, render_case
from crashmin.detect import parse_input
from crashmin.executor import Executor
from crashmin.parse_curl import parse_curl
from crashmin.reduce import reduce_request


def test_windows_cmd_doubled_quotes():
    text = (
        'curl ^\n'
        '  "http://127.0.0.1:9/b" ^\n'
        '  -H "Content-Type: application/json" ^\n'
        '  --data-raw "{""alpha"":""one"",""beta"":""two""}"\n'
    )
    req = parse_curl(text)
    assert req.path == "/b"
    assert req.json_body == {"alpha": "one", "beta": "two"}


def test_firefox_ansi_c_pretty_json():
    text = (
        "curl 'http://127.0.0.1:9/a' \\\n"
        "  -H $'X-Crash-Token: letmein' \\\n"
        "  --data-raw $'{\\n  \"payload\": {\\n    \"deeply\": {\\n"
        '      "nested": {\\n        "trigger": "boom"\\n      }\\n    }\\n  }\\n}\'\n'
    )
    req = parse_curl(text)
    assert req.header_value("X-Crash-Token") == "letmein"
    assert req.json_body["payload"]["deeply"]["nested"]["trigger"] == "boom"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_every_dialect_parses(case, fixture_server):
    text = render_case(case, fixture_server)
    req = parse_input(text, fmt=case.fmt)
    assert req.host in {"127.0.0.1", "localhost"}
    assert case.fixture.lower() in req.path.lower() or req.path.endswith(f"/{case.fixture.lower()}")


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    ["a-chrome", "a-firefox", "a-windows", "a-http", "a-har", "b-nextjs", "c-graphql", "f-windows"],
)
def test_corpus_reduces_to_needle(name, fixture_server):
    case = next(c for c in CASES if c.name == name)
    req = parse_input(render_case(case, fixture_server), fmt=case.fmt)
    result = reduce_request(
        req,
        Executor(oracle=case.oracle(), timeout=2.0, confirm=case.confirm),
        final_confirm=3,
    )
    assert result.confirmed
    mini = result.minimized
    if case.fixture == "A":
        assert mini.header_value("X-Crash-Token") == "letmein"
        assert mini.json_body == {"payload": {"deeply": {"nested": {"trigger": "boom"}}}}
        assert result.minimized_bytes < 200
    elif case.fixture == "B":
        assert mini.json_body["alpha"] == "one"
        assert mini.json_body["beta"] == "two"
        assert "gamma" not in mini.json_body
    elif case.fixture == "C":
        items = mini.json_body.get("items")
        assert items == [{"kind": "evil"}]
    elif case.fixture == "F":
        assert mini.cookies == [("session", "s3cret")]
        assert mini.query == [("need", "1")]
