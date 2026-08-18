# Agent notes

CrashMin is a Unix CLI for **failure-preserving HTTP request reduction**.

## Invoke

```bash
crashmin REQ.curl --status 500 --body-regex 'panic: nil pointer' --json --quiet -o min.curl
```

- **stdout** with `--json` = one JSON object (`schema: 1`). `crashmin --schema` prints the schema.
- **stderr** = progress. Ignore it. Use `--quiet`.
- Full contract: [docs/agents.md](docs/agents.md)

## Exit codes

| 0 | ok |
| 1 | baseline not interesting |
| 2 | usage / parse |
| 3 | safety (non-loopback) |
| 4 | budget abort (partial) |
| 5 | `--final-confirm` failed |

Exit `!= 0` → do not treat the result as a stable repro (except 4, which is a *best so far*).

## Safety

Do **not** pass `--allow-remote` unless the user explicitly asked. Do **not** commit raw `Copy as cURL` files. The minimized curl is what goes in issues and tests.

## Out of scope

No MCP, no LLM, no plugins, no daemon. If you need those, you are in the wrong repo.
