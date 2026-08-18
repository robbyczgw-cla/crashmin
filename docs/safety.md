# Safety

CrashMin is a reducer. A reducer **sends the request over and over**, mutating whatever is on the other end.

Treat every target as if the request were a DELETE of production data, because during search it might as well be.

## Hard default

CrashMin **refuses non-loopback hosts** unless you pass `--allow-remote`.

Allowed without a flag:

- `127.0.0.1`
- `localhost`
- `::1`
- any name that resolves only to loopback

Everything else (RFC1918 included) requires `--allow-remote`. Staging on a private IP is still a real server with real side effects.

```bash
# refused
crashmin prod.curl --status 500

# you own this decision
crashmin staging.curl --status 500 --allow-remote
```

## What we recommend

1. Reproduce against a **local fixture** or a throwaway staging process.
2. Prefer **idempotent** reads when you can. If the crash is on `POST /orders`, point CrashMin at a fake that panics the same way.
3. Use `--confirm N` on anything even slightly flaky.
4. Set `--timeout` and `--max-requests` so a wedged server cannot become an accidental flood.
5. Never paste a session cookie for a production account into a reducer and aim it at production.

Privacy (what must not leave your machine) is in [privacy.md](privacy.md).

The README repeats this because people will not open this file.

## Why this is not optional

Reduction issues tens to hundreds of variants:

- with and without `Authorization`
- with half the JSON
- with empty bodies
- with shortened cookie values

On a real app that is:

- creating rows
- charging cards
- rotating credentials
- invalidating sessions
- hitting rate limits
- tripping WAF bans

`--confirm 5` makes this worse (more sends), not safer. Confirmation is for **reliability of the interestingness signal**, not for production hygiene.

## Caching

CrashMin caches:

- the last response for a request fingerprint when `--confirm 1`;
- the boolean interestingness decision after a full confirm pack.

It does **not** cache a single flaky 500 across a `--confirm N` pack. That is deliberate: fixture E exists to prove a one-shot 500 is a lie.

## TLS

`--insecure` disables certificate verification. Only for local HTTPS with a junk cert.

## Tests

The test suite binds fixture servers to `127.0.0.1` with an ephemeral port. It never speaks to the public internet. `test_cli.py` asserts that `example.com` is rejected.
