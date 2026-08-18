# Repro corpus

Hand-shaped like Chrome / Firefox / Windows DevTools copies, plus raw HTTP and HAR.

They only ever hit the **loopback fixture server**. This is not a production crawl.

```bash
python3 scripts/corpus.py
```

Writes `corpus/repros/*` and `corpus/REPORT.md`.

**Surface** = delete headers, cookies, query (curlmin depth).
**Structured** = CrashMin, including nested JSON.

If structured does not beat surface on A/B/C/D, the wedge is dead.
