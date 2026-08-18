# CrashMin

**Failure-preserving HTTP request reduction.**

Paste a grotesque real-world request. Tell CrashMin what "still broken" means. Get back a tiny, human-readable curl that still reproduces *your* failure.

```
15,615 bytes -> 117 bytes
964 components -> 6
99.25% reduction
same failure: YES (20/20)
```

Measured against the bundled fixture on 17 August 2026. Re-run `python3 scripts/bench.py` to refresh [`benchmarks/report.md`](benchmarks/report.md).

This is **not** a request pretty-printer and **not** a response-equivalence minimizer.

```text
Input:   18 KB "Copy as cURL", 17 headers, a pile of cookies, 30+ JSON fields
Server:  HTTP 500, body contains "panic: nil pointer"

$ crashmin request.curl --status 500 --body-regex 'panic: nil pointer'

Output:  a ~100-byte curl
         one required header
         one required nested JSON field
         still the same panic
```

## Why this exists

[curlmin](https://github.com/noperator/curlmin), Burp Request Minimizer, and Caido Squash all shrink HTTP requests by asking:

> is the response still *the same*?

CrashMin asks:

> is it still *broken in the way I care about*?

That difference is the whole product. A 500 page that changes wording when you drop `User-Agent` is still the crash. An equivalence tool will keep the header. CrashMin will not.

Generic reducers (shrinkray, Picire, Lithium) can chew the *text* of a curl file given a shell script. They do not understand cookies vs JSON keys, and they happily emit unreadable garbage. CrashMin stays on the HTTP structure so the result is ready to paste.

See [`docs/competition.md`](docs/competition.md) for the August 2026 landscape and [`docs/verdict.md`](docs/verdict.md) for the BUILD scores.

## Safety (read this)

CrashMin **sends the request many times**. It will mutate whatever you point it at.

- **Default: loopback only.** Non-local hosts are refused.
- Use a local or staging target. Never production.
- `--allow-remote` is an explicit "I accept the blast radius" switch.
- Prefer `--confirm N` on anything flaky or non-idempotent.

Details: [`docs/safety.md`](docs/safety.md).

## Install

```bash
pip install .

# or, no install:
PYTHONPATH=src python3 -m crashmin --help
```

Python 3.10+. No runtime dependencies.

Dev:

```bash
pip install -e '.[dev]'
pytest
```

## Usage

```bash
crashmin request.curl --status 500 --body-regex 'panic: nil pointer'
crashmin request.http --status '>=500'
crashmin capture.har --body-contains 'INTERNAL ERROR'
crashmin request.curl --oracle ./interesting.sh --confirm 5
```

Input is auto-detected:

1. cURL command (`curl ...`)
2. Raw HTTP request (`POST /path HTTP/1.1 ...`)
3. HAR (first entry, or `--har-index N`)

The minimized request goes to **stdout**. Progress and the scoreboard go to **stderr**, so this is valid:

```bash
crashmin req.curl --status 500 > min.curl
```

### Oracles

All flags AND together. At least one is required.

| Flag | Meaning |
| --- | --- |
| `--status 500` / `'>=500'` / `5xx` | status check |
| `--body-contains TEXT` | literal needle in the body |
| `--body-regex REGEX` | body regular expression |
| `--header NAME=VALUE` | response header |
| `--timeout-is-failure` | client timeout counts as interesting |
| `--oracle SCRIPT` | exit 0 = still broken |

`--confirm N` — a candidate counts only if it fails **N/N** times.

`--final-confirm N` — extra N sends of the *answer*, printed as `same failure: YES (N/N)`.

Full contract: [`docs/oracles.md`](docs/oracles.md).

### What gets reduced

Hierarchically, not as raw bytes:

1. Whole body (if the crash does not need it)
2. Headers, then header values
3. Cookies, then cookie values
4. Query parameters, then values
5. `application/x-www-form-urlencoded` fields
6. JSON objects / arrays / nested values / primitives
7. Path segments, conservatively

`Host` and `Content-Length` are not toys. They are reconstructed on the way out.

v0.1 does **not** reduce multipart or every content type. Opaque bodies are left alone rather than shredded into junk.

## Killer demo

```bash
# terminal 1
python3 -m crashmin.fixtures --port 18765

# terminal 2
python3 -c 'from crashmin.demo import killer_curl; print(killer_curl("http://127.0.0.1:18765"))' \
  > examples/killer.curl

python3 -m crashmin examples/killer.curl \
  --status 500 \
  --body-regex 'panic: nil pointer' \
  --final-confirm 20 \
  --compact
```

Or: `bash scripts/demo.sh`.

The original is deliberately huge: tracking headers, a dozen cookies, UTM spam, a JSON blob with users/flags/events, and **one** real trigger:

- header `X-Crash-Token: letmein`
- JSON `payload.deeply.nested.trigger == "boom"`

Everything else is noise. CrashMin should throw it away and still get HTTP 500 + `panic: nil pointer` on 20/20 sends.

## Local fixtures

The bundled server is the test suite's universe. It never leaves `127.0.0.1`.

| Route | Failure | What must remain |
| --- | --- | --- |
| `POST /a` | 500 + `panic: nil pointer` | header + nested JSON field |
| `POST /b` | 500 only if **both** `alpha` and `beta` are set | the pair (A alone / B alone is fine) |
| `POST /c` | 500 if an array item has `kind=evil` | that one item |
| `POST /d` | **200** + `INTERNAL ERROR: widget exploded` | `widget.id` (body oracle, not status) |
| `POST /e` | 500 always with `X-Flaky-Key`; one-shot flake without it | confirmation logic |
| `GET  /f` | 500 + `session gate` | one cookie + one query param |

```bash
python3 -m crashmin.fixtures --port 18765
# or: python3 fixtures/server.py
```

## Algorithm

Classic **ddmin** over HTTP pieces, then another pass deeper:

```
request sections → fields → nested JSON → primitive simplification
```

No raw-byte pass. The output must stay a request a human can read and a colleague can paste.

## Non-goals

CrashMin is a reducer. It is not:

- a Burp/Postman replacement
- a proxy, dashboard, or traffic recorder
- a vulnerability scanner
- an AI analyst
- a fuzzing framework
- a cloud service

## Programmatic use

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

## License

MIT. See [LICENSE](LICENSE).
