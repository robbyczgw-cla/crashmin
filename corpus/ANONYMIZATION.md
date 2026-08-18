# How the “real” Chrome case was anonymized

File: `corpus/repros/anonymized-chrome-saas.curl`

This is a **Chrome 128 DevTools → Copy as cURL (bash)** of a workspace-settings
save. It is not a toy emitter dumping our own header order.

What was replaced before it entered git:

| Original | Replacement |
| --- | --- |
| Production / staging host | `http://127.0.0.1:18765/a` (loopback fixture) |
| `Origin` / `Referer` | `https://app.example.invalid/...` |
| Bearer token | `anonymized-session-token` |
| Session + vendor cookies | dummy values, real *names* kept (`_ga`, `__stripe_mid`, …) |
| Member emails | `memberN@example.invalid` |
| Org / request IDs | `org_anon_*`, `req_anon_*` |
| Client IP | `203.0.113.88` (documentation range) |

What was kept, because that is the point of the case:

- Chrome’s lowercase header names and typical order (`accept`, `priority`, `sec-ch-ua`, …)
- `--data-raw` body as Chrome emits it
- A fat JSON settings payload (members, flags, audit, UI chrome)
- One required custom header and one nested JSON field — those are the crash

The request is then replayed **only** against the loopback fixture, so the
failure (`HTTP 500` + `panic: nil pointer`) is deterministic. We do not ship
anyone’s real session.
