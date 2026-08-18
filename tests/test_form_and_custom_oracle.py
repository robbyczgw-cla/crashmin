from __future__ import annotations

import os
import stat
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs

import pytest

from crashmin.executor import Executor
from crashmin.models import HttpRequest
from crashmin.oracle import compile_oracle
from crashmin.reduce import reduce_request


class _FormHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A003
        return

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        form = parse_qs(raw, keep_blank_values=True)
        ok = form.get("user") == ["ada"] and form.get("op") == ["crash"]
        body = b"form-boom" if ok else b"ok"
        status = 500 if ok else 200
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def form_server():
    server = HTTPServer(("127.0.0.1", 0), _FormHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_reduces_form_urlencoded(form_server):
    req = HttpRequest(method="POST")
    req.set_url(form_server + "/form")
    req.set_header("Content-Type", "application/x-www-form-urlencoded")
    req.form_body = [
        ("utm", "x"),
        ("user", "ada"),
        ("pad", "zzzz"),
        ("op", "crash"),
        ("extra", "1"),
    ]
    req.refresh_body_from_structure()
    oracle = compile_oracle(statuses=["500"], body_contains=["form-boom"])
    result = reduce_request(req, Executor(oracle=oracle, timeout=2.0))
    assert set(result.minimized.form_body) == {("user", "ada"), ("op", "crash")}


def test_custom_oracle_script(form_server, tmp_path):
    script = tmp_path / "interesting.sh"
    script.write_text(
        "#!/bin/sh\n"
        "test \"$CRASHMIN_STATUS\" = 500 || exit 1\n"
        "grep -q form-boom \"$CRASHMIN_BODY_FILE\"\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    req = HttpRequest(method="POST")
    req.set_url(form_server + "/form")
    req.set_header("Content-Type", "application/x-www-form-urlencoded")
    req.form_body = [("user", "ada"), ("op", "crash"), ("noise", "1")]
    req.refresh_body_from_structure()
    oracle = compile_oracle(script=str(script))
    result = reduce_request(req, Executor(oracle=oracle, timeout=2.0))
    names = {n for n, _ in (result.minimized.form_body or [])}
    assert names == {"user", "op"}
    assert os.environ.get("CRASHMIN_STATUS") is None  # script env is isolated
