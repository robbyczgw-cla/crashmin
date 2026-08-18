# Competition check (August 2026)

CrashMin's claimed wedge is:

> curl / raw HTTP / HAR
> \+ a built-in **arbitrary failure oracle**
> \+ HTTP-aware **structured** reduction
> → a ready-to-paste **minimal reproduction** of a *chosen failure*

That is **failure-preserving request reduction**, not response-equivalence minimization and not generic file shrinking.

This document classifies the current landscape. Classes:

| Class | Meaning |
| --- | --- |
| **EXACT** | Same workflow and UX: paste a request, define "still broken", get a small pasteable HTTP repro |
| **ADJACENT** | Overlaps (HTTP-aware minimization, or a request CLI) but a different oracle, host, or depth |
| **PRIMITIVE** | Generic delta-debugging / test-case reduction you could *wrap*, with no HTTP request UX |

**Finding:** nothing is EXACT. The wedge survives.

---

## Closest tools

### curlmin — ADJACENT

- Repo: [noperator/curlmin](https://github.com/noperator/curlmin)
- CLI that parses a curl command and drops headers, cookies, and query parameters.
- Oracle is **response equivalence**: replay the original, then keep an edit only if the response (body / status / counts) stays the same.
- Does **not** reduce JSON / form bodies.
- Does **not** take `--status 500`, `--body-regex`, or a custom "still broken" script.
- This is the nearest CLI. It solves "strip tracking junk from Copy as cURL while the page still loads the same", not "keep the panic and delete everything else".

Why it is not EXACT: a 500 with a huge HTML error page plus one `panic: nil pointer` line would be treated as a *different* response as soon as headers or cookies change the surrounding HTML. Equivalence oracles fight crash reduction.

### Burp Request Minimizer — ADJACENT

- [PortSwigger BApp](https://portswigger.net/bappstore/cc16f37549ff416b990d4312490f5fd1), source [portswigger/request-minimizer](https://github.com/portswigger/request-minimizer)
- Repeater context-menu action. Deletes parameters that do not change the response.
- Oracle is again **response match**, not a user-defined failure.
- Lives inside Burp. Not a paste-curl CLI. Not a JSON hierarchical reducer.

### Caido Squash — ADJACENT

- [evanconnelly/squash](https://github.com/evanconnelly/squash) (active 2025–2026 plugin)
- Right-click minimizer: query, form fields, **JSON**, headers, cookies.
- Still compares responses for *invariant* behavior, then opens Replay.
- Plugin-only. No curl/HAR CLI, no `--status` / `--body-regex` / `--oracle` failure language.

Squash is the strongest evidence that structured HTTP reduction is useful — and that the market still frames it as "make the request look like the original response", not "preserve this crash".

### Other Burp-family helpers — ADJACENT / irrelevant

- Paste curl → Repeater, copy request/response, etc. They move bytes between UIs. They do not reduce against a failure oracle.

---

## Generic reducers

### shrinkray (DRMacIver) — PRIMITIVE

- [DRMacIver/shrinkray](https://github.com/DRMacIver/shrinkray), still actively released (calver through 2025).
- Excellent multi-format *file* reducer. You hand it a file and an interestingness script.
- Tuned for languages / JSON / binary blobs, not for "parse this curl, send HTTP, keep it a valid request".
- You *could* wrap CrashMin's problem as `shrinkray interesting.sh request.curl`. The script would exec curl and grep the panic. Shrinkray would then chew the **text of the curl command**.
- That frequently yields broken quoting, invalid HTTP, or unreadable garbage — the opposite of a paste-ready repro.
- No built-in HTTP client, no status/body/header oracle DSL, no cookie/query/JSON hierarchy.

**Kill-criterion check:** shrinkray does **not** already provide this workflow with equivalent UX.

### Picire — PRIMITIVE

- [renatahodovan/picire](https://github.com/renatahodovan/picire)
- Parallel delta debugging on lines or characters. Library + CLI. Custom tester script.
- No HTTP model.

### Lithium (Mozilla) — PRIMITIVE

- [MozillaSecurity/lithium](https://github.com/MozillaSecurity/lithium)
- Line-based reducer. Famous for shrinking HTML/JS crashers for Firefox.
- No HTTP request object, no curl parser.

### C-Reduce / C-Vise / `ddmin` libraries — PRIMITIVE

- Domain-specific (C/C++) or textbook delta debugging.
- [Alamvic/ddmin](https://github.com/Alamvic/ddmin) and similar are algorithm ports.
- Useful as an engine, not as a product.

### Hypothesis shrinking — PRIMITIVE

- Shrinks generated examples inside a property test. Not a standalone HTTP repro tool.

---

## HAR / capture tools — ADJACENT (wrong axis)

| Tool | What it actually does |
| --- | --- |
| [markSmurphy/shrink-har](https://github.com/markSmurphy/shrink-har) | Strips **response bodies** from a HAR to shrink the file on disk |
| [thameera/harcleaner](https://github.com/thameera/harcleaner) | Drops noisy *requests* from a capture |
| [sen-ltd/har-analyze](https://github.com/sen-ltd/har-analyze) (2026) | Summarizes a HAR; not a reducer |
| [0xpanadol/har-viewer](https://github.com/0xpanadol/har-viewer) | Viewer |
| [paulirish/request-capture-har](https://github.com/paulirish/request-capture-har) | Recorder |

None of these minimize a single request against a live failure oracle.

---

## Security / fuzzing reducers — ADJACENT

Fuzzers (AFL, libFuzzer, ClusterFuzz, web fuzzers, API fuzzers) reduce **inputs that crash a binary** or sometimes HTTP payloads inside a harness. They:

- assume you already have a harness, corpus, and crash artifact;
- usually shrink bytes / tokens, not a Copy-as-cURL session;
- do not emit a human-readable curl with one required header and two JSON keys.

No 2025–2026 GitHub project was found that packages "paste this 18 KB curl, here is the panic regex, give me 94 bytes" as a polished CLI.

---

## Why structured HTTP reduction is not "just delete headers"

curlmin-style one-at-a-time header/query deletion is enough when the failure is "missing `Authorization`" or "needs `session=`".

It is **not** enough when:

- two JSON fields must appear **together** (A alone and B alone are fine; A+B panics);
- the trigger is a **nested** key under 40 siblings and 3 wrapper objects;
- the trigger is **one array element** with `kind=evil` and the rest is padding;
- the interesting signal is a **body string on HTTP 200**, not a status change;
- the server is **slightly flaky** and a single 500 is a lie.

Those are CrashMin fixtures B–E. They are the difference between a header stripper and a reducer.

---

## Kill-criteria review

| Criterion | Verdict |
| --- | --- |
| shrinkray or another current tool already does the exact workflow with equivalent UX | **No.** Closest are curlmin (wrong oracle, no body) and Squash (plugin, equivalence). |
| Structured reduction rarely beats simple header/query deletion | **False for the intended bugs.** Nested JSON / pair fields / array items are the point. Header-only deletion cannot reach them. |
| Stateful / non-idempotent HTTP makes reproduction fundamentally unreliable | **A real risk, not a kill.** Mitigation: `--confirm N`, caching of *oracle decisions* (not one-shot flakes), timeout limits, and a hard default of loopback-only. Documented in `docs/safety.md`. |
| Results frequently become unreadable garbage | **Avoided by refusing raw-byte reduction.** Output stays a curl/HTTP request. |

**Decision: BUILD.** Scores and the four kill-criteria are written up in [`docs/verdict.md`](verdict.md).

CrashMin should stay a reducer. It should not grow a proxy UI, scanner, or SaaS. The product is the last mile from a grotesque real-world request to a sentence-sized repro.
