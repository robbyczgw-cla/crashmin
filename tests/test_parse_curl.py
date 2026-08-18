from crashmin.parse_curl import parse_curl, split_argv


def test_split_quotes_and_continuations():
    text = r"""
    curl \
      -H 'Accept: application/json' \
      -H "X-Foo: bar baz" \
      'http://example.test/x?q=1'
    """
    argv = split_argv(text)
    assert argv[0] == "curl"
    assert "Accept: application/json" in argv
    assert "X-Foo: bar baz" in argv
    assert argv[-1] == "http://example.test/x?q=1"


def test_parse_chrome_style_copy():
    text = r"""
    curl 'http://localhost:8080/api?utm=1&keep=yes' \
      -H 'accept: application/json' \
      -H 'content-type: application/json' \
      -H 'cookie: a=1; session=abc; b=2' \
      --data-raw '{"foo":1,"bar":{"baz":true}}'
    """
    req = parse_curl(text)
    assert req.method == "POST"
    assert req.host == "localhost"
    assert req.port == 8080
    assert req.path == "/api"
    assert ("utm", "1") in req.query
    assert req.header_value("accept") == "application/json"
    assert ("session", "abc") in req.cookies
    assert req.json_body == {"foo": 1, "bar": {"baz": True}}


def test_parse_ansi_c_cookie():
    text = r"""curl $'http://127.0.0.1/x' -H $'Cookie: a=1; b=two'"""
    req = parse_curl(text)
    assert req.cookies == [("a", "1"), ("b", "two")]


def test_parse_minus_x_and_data():
    req = parse_curl("curl -X PUT -d hello http://127.0.0.1:9/z")
    assert req.method == "PUT"
    assert req.body == b"hello"
    assert req.path == "/z"


def test_parse_json_flag():
    req = parse_curl("""curl --json '{"a":1}' http://127.0.0.1/j""")
    assert req.method == "POST"
    assert req.json_body == {"a": 1}
    assert req.content_type() == "application/json"


def test_caret_windows_continuation():
    text = "curl ^\n  http://127.0.0.1/w"
    req = parse_curl(text)
    assert req.path == "/w"


def test_comments_ignored():
    text = "# captured from chrome\ncurl http://127.0.0.1/ok\n"
    req = parse_curl(text)
    assert req.path == "/ok"
