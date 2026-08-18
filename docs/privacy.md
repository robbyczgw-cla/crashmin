# Privacy

CrashMin's job is to chew on HTTP requests. Those requests are usually full of
session cookies, bearer tokens, and personal data. Treat every input as
**secret**.

## This repository

Everything in this repo is synthetic:

- hosts are `127.0.0.1` or `*.example.invalid`
- IPs are documentation ranges (`203.0.113.0/24`)
- cookies, JWTs, Stripe/Intercom IDs are dummy strings
- no real `Copy as cURL` was ever imported

Do **not** add a real capture to `corpus/`, `examples/`, an issue, or a PR.
Redact or throw it away. Git history keeps it forever.

`--parse-only` prints the reconstructed request, secrets included. That output
is for your terminal, not for GitHub.

Progress logs print host + path + *counts* (`3 cookies`, `12 query`). They do
not print cookie values, query values, or `Authorization`.

## What CrashMin sends

It replays your request, including cookies and bodies, at the target. There is
no CrashMin cloud, no telemetry, no phone-home. Stdlib HTTP client only.

If the target is not yours, you are leaking the session to that host — and
to every hop on the way. Default is loopback. See [safety.md](safety.md).

## Git

Do not `git push --mirror` or push `refs/t3/**`. Those are local tool
checkpoints and must stay on the machine that created them.

Commits are attributed to the GitHub account that owns the repo, using
GitHub's `noreply` address so a private inbox is not in the history.

## License vs privacy

MIT does not make a leaked session cookie okay. The license is for the code.
The request you paste is yours, and it stays yours.
