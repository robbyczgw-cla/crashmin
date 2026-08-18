# Changelog

## 0.1.0 — 2026-08-18

First public release.

- CLI: curl / raw HTTP / HAR in, minimized curl or raw HTTP out
- Hierarchical reduction (headers, cookies, query, form, nested JSON)
- Built-in oracles (`--status`, `--body-contains`, `--body-regex`, `--header`, `--timeout-is-failure`) plus `--oracle SCRIPT`
- `--confirm` / `--final-confirm`
- Loopback-only default (`--allow-remote` to override)
- `--json` agent contract and `crashmin --schema`
- Exit codes 0–5
- Deterministic loopback fixtures and an anonymized Chrome Copy-as-cURL demo
