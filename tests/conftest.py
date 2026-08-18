from __future__ import annotations

import threading

import pytest

from crashmin.fixtures import make_server


@pytest.fixture(scope="session")
def fixture_server():
    server = make_server("127.0.0.1", 0, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
