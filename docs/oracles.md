# Oracles

An **oracle** is the definition of *still broken*. CrashMin keeps a candidate only when the oracle says it is interesting.

This is the opposite of response-equivalence tools (curlmin, Burp Request Minimizer, Caido Squash), which keep a candidate when the response *stays the same as the original*.

All built-in checks are **AND**-combined. Repeat a flag to add another check.

## Built-in flags

| Flag | Interesting when |
| --- | --- |
| `--status 500` | status is exactly 500 |
| `--status '>=500'` | status ≥ 500 |
| `--status '>499'` | status > 499 |
| `--status 5xx` | status in 500–599 |
| `--body-contains TEXT` | response body contains the literal string |
| `--body-regex REGEX` | Python regular expression matches the body |
| `--header NAME` | response has this header |
| `--header NAME=VALUE` | response header equals VALUE |
| `--timeout-is-failure` | the client hit `--timeout` before a response |

Examples:

```bash
crashmin req.curl --status 500 --body-regex 'panic: nil pointer'
crashmin req.curl --status '>=500'
crashmin req.curl --body-contains 'INTERNAL ERROR: widget exploded'
crashmin req.curl --header X-Error-Code=WIDGET
crashmin req.curl --timeout-is-failure --timeout 0.2
```

`--header` inspects the **response**. Request headers come from the input file.

## Confirmation

```bash
crashmin req.curl --status 500 --confirm 5
```

A candidate is interesting only if **5 of 5** fresh sends match the oracle.

`--confirm` exists because HTTP is not a pure function:

- load balancers, warm-up, and one-shot 500s;
- servers that fail the first time they see a fingerprint;
- anything that is not idempotent.

Confirmation trials **do not share a cached response**. After all N trials, CrashMin caches the boolean decision so the search does not repeat the same N-pack.

`--final-confirm N` re-sends the minimized request N times at the end and prints `same failure: YES (N/N)`.

## Custom script

```bash
crashmin req.curl --oracle ./interesting.sh
```

The script is interesting when it exits **0**.

It is invoked as:

```text
interesting.sh $CRASHMIN_BODY_FILE
```

Environment:

| Variable | Meaning |
| --- | --- |
| `CRASHMIN_STATUS` | HTTP status, or `0` on timeout/error |
| `CRASHMIN_URL` | full URL that was sent |
| `CRASHMIN_METHOD` | method |
| `CRASHMIN_BODY_FILE` | path to the raw response body |
| `CRASHMIN_HEADERS_FILE` | path to a small dump (request line + response headers) |
| `CRASHMIN_TIMED_OUT` | `1` or `0` |
| `CRASHMIN_ERROR` | client error string, if any |

Example:

```sh
#!/bin/sh
test "$CRASHMIN_STATUS" = 500 || exit 1
grep -q 'panic: nil pointer' "$CRASHMIN_BODY_FILE"
```

You can combine a script with built-in flags; every check must pass.

## Programmatic interface

```python
from crashmin import HttpRequest, Oracle, reduce_request
from crashmin.detect import parse_input
from crashmin.executor import Executor
from crashmin.oracle import compile_oracle

req = parse_input(open("req.curl").read())
oracle = compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"])
# or:
oracle = Oracle(predicate=lambda req, resp: resp.status == 500 and b"panic" in resp.body)

result = reduce_request(req, Executor(oracle=oracle, confirm=3, timeout=2.0))
print(result.summary_lines())
print(result.minimized.url())
```

`Oracle.predicate` is a `Callable[[HttpRequest, HttpResponse], bool]`.

## What not to use as an oracle

- "Looks like the original response" — that is curlmin's job.
- "Any 5xx on production" — you will reduce a live system. See `docs/safety.md`.
- An oracle that is true for the empty request. Reduction will correctly collapse to almost nothing; that usually means the oracle is too wide (for example `--status 200` against a server that always 200s).
