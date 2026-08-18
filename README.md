# CrashMin

**Failure-preserving HTTP request reduction.**

Paste a grotesque `Copy as cURL`. Say what “still broken” means. Get back a tiny, readable request that still reproduces *your* failure.

```
15,615 bytes  →  117 bytes
964 pieces    →  6
99.25% smaller
same panic    →  YES (20/20)
```

```bash
# before: 15 KB of cookies, UTMs, and JSON noise
# after:
curl -H 'X-Crash-Token: letmein' \
  -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' \
  'http://127.0.0.1:18765/a'
```

This is **not** a formatter and **not** a “make the response look the same” minimizer.

| Other tools ask | CrashMin asks |
| --- | --- |
| Is the response still *identical*? | Is it still *broken the way I said*? |

A 500 page that changes wording when you drop `User-Agent` is still the crash. Equivalence tools keep the header. CrashMin deletes it.

License: **MIT**.

---

## Install

Python 3.10+, no runtime dependencies.

```bash
pip install git+https://github.com/robbyczgw-cla/crashmin.git
```

From a clone:

```bash
pip install .
crashmin --help
```

## 30-second demo (local only)

```bash
bash scripts/demo.sh
```

That starts a broken toy server on loopback, feeds it a 15 KB fake “Copy as cURL”, and prints the 117-byte repro. Nothing leaves `127.0.0.1`.

## Safety — read this

CrashMin **sends the request many times**. It will mutate whatever you point it at.

- **Default: loopback only.** Anything else is refused.
- Use a local or staging target. **Never production.**
- `--allow-remote` means you accept the blast radius.
- Use `--confirm N` on flaky or non-idempotent endpoints.
- A `Copy as cURL` is a session dump. Do not commit one, do not paste one into an issue.

Details: [docs/safety.md](docs/safety.md) · [docs/privacy.md](docs/privacy.md).

## Usage

```bash
crashmin request.curl --status 500 --body-regex 'panic: nil pointer'
crashmin request.http --status '>=500'
crashmin capture.har  --body-contains 'INTERNAL ERROR'
crashmin request.curl --oracle ./interesting.sh --confirm 5
```

Input is auto-detected: a `curl …` command, a raw HTTP request, or a HAR (first entry, or `--har-index N`).

Minimized request → **stdout**. Scoreboard → **stderr**.

```bash
crashmin req.curl --status 500 > min.curl
```

### Oracles (AND-combined; at least one required)

| Flag | Interesting when |
| --- | --- |
| `--status 500` / `'>=500'` / `5xx` | status matches |
| `--body-contains TEXT` | body contains the literal |
| `--body-regex REGEX` | body matches |
| `--header NAME=VALUE` | response header matches |
| `--timeout-is-failure` | the client timed out |
| `--oracle SCRIPT` | script exits 0 |

`--confirm N` — keep a candidate only if it fails **N/N** times.
`--final-confirm N` — re-send the answer N times and print `same failure: YES (N/N)`.

Full contract: [docs/oracles.md](docs/oracles.md).

### What it shrinks

HTTP structure, top-down — never raw bytes:

headers → cookies → query → form fields → nested JSON → primitives → path (carefully)

`Host` and `Content-Length` are rebuilt on the way out.

v0.1 does **not** shrink multipart or mystery content types. Opaque bodies stay readable rather than becoming junk.

## When this is worth it

Worth it when the crash lives in **JSON shape** (nested key, two fields only together, one array item) and the paste is huge.

Not worth it when the bug is “needs `Authorization`” — delete that header by hand, or use [curlmin](https://github.com/noperator/curlmin).

On our dialect corpus (Chrome / Firefox / Windows / HAR / raw HTTP), structured reduction beat header-only deletion on every JSON crash, and *tied* on the cookie+query crash — which is correct.

| Fixture A | Structured | Headers only |
| --- | ---: | ---: |
| 15,615 byte curl | **117** | 12,836 |

That leftover ~13 KB is the JSON. Header strippers cannot see it.

[corpus/REPORT.md](corpus/REPORT.md) · [docs/competition.md](docs/competition.md)

## Not this project

CrashMin is a reducer. It is not a Burp/Postman replacement, proxy, scanner, fuzzer, dashboard, or cloud service.

## Library

```python
from crashmin.detect import parse_input
from crashmin.executor import Executor
from crashmin.oracle import compile_oracle
from crashmin.reduce import reduce_request

req = parse_input(open("request.curl").read())
oracle = compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"])
result = reduce_request(req, Executor(oracle=oracle, confirm=5))
print("\n".join(result.summary_lines()))
```

## Develop

```bash
pip install -e '.[dev]'
pytest -q
python scripts/bench.py     # benchmarks/report.md
python scripts/corpus.py    # corpus/REPORT.md
```

Toy crash servers live on loopback only: `python3 -m crashmin.fixtures --port 18765` (`POST /a`–`/e`, `GET /f`).

## License

[MIT](LICENSE). Use it, fork it, vendor it. Keep the copyright notice.

Why MIT and not GPL or Apache: this is a small CLI people should paste into a debugging toolkit without a license argument. No patents, no copyleft. The risk is sending requests at the wrong host — that is a safety default, not a license problem.
