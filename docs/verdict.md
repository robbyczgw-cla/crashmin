# Verdict

**BUILD.**

Date: 17 August 2026.

CrashMin is a real, tested, loopback-only CLI that takes a grotesque HTTP request and a user-defined failure oracle and returns a pasteable curl that still fails that way.

## Kill-criteria

| Criterion | Result |
| --- | --- |
| shrinkray or another current tool already does this workflow with equivalent UX | **No.** See `docs/competition.md`. Closest: curlmin (equivalence, no body), Squash (Caido plugin, equivalence), shrinkray (generic file shrinker). |
| Structured reduction rarely beats simple header/query deletion | **False.** Fixtures B (pair fields), C (array item), D (nested body oracle) cannot be solved by deleting headers. Bench: B 180→65, C 240→64, A 15,615→117 with the trigger still nested. |
| Stateful / non-idempotent HTTP makes reproduction fundamentally unreliable | **A risk, not a kill.** `--confirm N`, decision caching (not one-shot response caching), `--timeout`, `--max-requests`, and a hard loopback default. Fixture E exists to prove confirmation. |
| Results frequently become unreadable garbage | **No.** No raw-byte pass. Output is curl or raw HTTP. The killer demo is one header + one JSON path. |

## Scores (1–5)

| Axis | Score | Notes |
| --- | --- | --- |
| Usefulness | 4 | Every backend engineer has a 18 KB Copy-as-cURL and a panic. This is the last mile to a bug report. |
| Differentiation | 5 | Failure oracle + structured HTTP + pasteable output is not a product anyone else ships. |
| Reduction quality | 5 | 99.25% on the killer demo; pair/array/nested JSON all 1-minimal and readable. |
| Reliability | 4 | Confirm + cache + fixtures E. Real-world non-idempotent APIs will still hurt; safety rails are the answer, not a different product. |
| UX | 4 | One command, scoreboard on stderr, curl on stdout. No daemon, no account. |
| Fun / technical interest | 5 | Hierarchical ddmin over HTTP is a satisfying, teachable algorithm with a demo that slaps. |
| Maintenance burden | 4 | Stdlib only, ~2k lines, no services. Curl dialects will rot at the edges; that is the main tax. |
| OSS potential | 4 | Small enough to finish, sharp enough to tweet, useful enough to depend on. Stay a reducer. |

## What would flip this to PARK or KILL

- A curlmin release that adds `--status` / `--body-regex` **and** JSON/form reduction with confirmation. Then this is a fork conversation, not a new tool.
- Evidence that most "real" crashes collapse after deleting three headers and never need JSON structure. Our fixtures show the opposite for the bugs we claim to own; a corpus of production curls would be the honest follow-up.
- If users cannot keep a staging target and keep pointing this at production despite the default deny.

Corpus hunt (13 dialect repros, 17 August 2026): structured reduction beat
header/query-only deletion on every JSON crash (A–D, including Next.js- and
GraphQL-shaped envelopes). On the cookie+query crash (F) both strategies tied,
which is what should happen. See `corpus/REPORT.md`.

Until then: **ship it, keep it small, do not grow a proxy.**
