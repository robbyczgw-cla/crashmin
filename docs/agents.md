# CrashMin for coding agents

CrashMin is a **Unix CLI**. There is no MCP server, no SDK, no daemon.
You invoke it, you parse stdout, you read the exit code.

## Contract

```text
crashmin INPUT --status SPEC [--body-regex RE] [--json] [-o min.curl]
```

| Stream | Contents |
| --- | --- |
| **stdout** | With `--json`: one JSON object, nothing else. Without: the minimized curl/HTTP. |
| **stderr** | Progress. Never the machine result. `--quiet` silences it. |
| **exit** | See below. Do not treat 4 or 5 as success. |

`--json` is the agent interface. `-o FILE` still writes the pasteable curl beside it.

```bash
crashmin req.curl \
  --status 500 \
  --body-regex 'panic: nil pointer' \
  --confirm 3 \
  --final-confirm 5 \
  --json \
  --quiet \
  -o min.curl
```

Then:

1. If exit is not `0`, stop. Read `.error` / `.error_code`.
2. Use `.minimized.curl` (or `min.curl`) as the reproduction.
3. Use `.minimized.url` + `.oracle` in the issue / regression test.
4. If `.reduction.percent` is tiny, the crash is probably one header — say so.

`crashmin --schema` prints the JSON Schema (`schema: 1`). Do not invent keys.

## Exit codes

| Code | Meaning | Agent action |
| ---: | --- | --- |
| 0 | Reduced (or `--parse-only` / `--schema` ok) | Use `.minimized` |
| 1 | Baseline is not interesting | Oracle or target is wrong |
| 2 | Usage / parse / missing oracle | Fix the invocation |
| 3 | Non-loopback target refused | Point at staging or pass `--allow-remote` *only if intended* |
| 4 | `--max-requests` hit; partial result | `.minimized` may still help; say it is incomplete |
| 5 | `--final-confirm` did not hold | Do not treat as a stable repro |

## Workflow

```
HTTP/API failure
    → write the captured curl/HAR to a temp file (never commit it)
    → crashmin that file --json --final-confirm 5
    → read JSON
    → diagnose / write a regression test / open a short issue
    → after a fix, replay .minimized.curl and expect the oracle to miss
```

`--parse-only --json` inspects a capture without sending anything.

## Safety (non-negotiable)

- Default: loopback only. Do not pass `--allow-remote` unless the human asked.
- A `Copy as cURL` is a session dump. Keep it in `/tmp`. Never commit it. Never paste it into an issue — paste `.minimized.curl` after reduction, and only if it no longer carries cookies/tokens you did not intend to keep.
- Prefer a local fixture or staging process as the target.

## What not to do

- Do not wrap CrashMin in an MCP server.
- Do not call an LLM from CrashMin.
- Do not parse stderr.
- Do not assume color codes or TTY layout.

## Minimal Python

```python
from crashmin.detect import parse_input
from crashmin.executor import Executor
from crashmin.oracle import compile_oracle
from crashmin.reduce import reduce_request
from crashmin.report import decide_exit, result_report

req = parse_input(open("req.curl").read())
oracle = compile_oracle(statuses=["500"], body_regexes=[r"panic"])
result = reduce_request(req, Executor(oracle=oracle, confirm=3), final_confirm=5)
print(result_report(result, oracle=oracle.describe(), confirm=3, exit_code=decide_exit(result)))
```
