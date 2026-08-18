# Corpus hunt

Realistic Copy-as-cURL / HAR / raw-HTTP repros, replayed only against
the loopback fixture server. **Surface** is header + cookie + query
deletion (curlmin depth). **Structured** is CrashMin, including JSON.

Cases: 14. Structured strictly smaller: 12/14.
Cases where we *claimed* structure must win: 12/12.

| Case | Dialect | In | Structured | Surface | Saved vs surface | Confirm |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `a-chrome` | chrome-bash | 15,578 | 117 | 12,835 | 12,718 | 5/5 |
| `a-firefox` | firefox-ansi-c | 20,940 | 117 | 12,835 | 12,718 | 5/5 |
| `a-windows` | chrome-cmd | 15,578 | 117 | 12,835 | 12,718 | 5/5 |
| `a-http` | raw-http | 15,578 | 117 | 12,835 | 12,718 | 5/5 |
| `a-har` | har-1.2 | 15,578 | 117 | 12,835 | 12,718 | 5/5 |
| `b-chrome` | chrome-bash | 180 | 65 | 144 | 79 | 5/5 |
| `b-nextjs` | chrome-bash | 464 | 65 | 241 | 176 | 5/5 |
| `c-firefox` | firefox-ansi-c | 423 | 64 | 204 | 140 | 5/5 |
| `c-graphql` | chrome-bash | 561 | 64 | 447 | 383 | 5/5 |
| `d-chrome` | chrome-bash | 158 | 59 | 122 | 63 | 5/5 |
| `e-chrome` | chrome-bash | 147 | 61 | 68 | 7 | 5/5 |
| `f-chrome` | chrome-bash | 898 | 66 | 66 | 0 | 5/5 |
| `f-windows` | chrome-cmd | 898 | 66 | 66 | 0 | 5/5 |
| `anonymized-chrome-saas` | chrome-devtools | 12,441 | 117 | 11,069 | 10,952 | 5/5 |

## Minimized curls

### a-chrome

```bash
curl -H 'X-Crash-Token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

### a-firefox

```bash
curl -H 'X-Crash-Token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

### a-windows

```bash
curl -H 'X-Crash-Token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

### a-http

```bash
curl -H 'X-Crash-Token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

### a-har

```bash
curl -H 'X-Crash-Token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

### b-chrome

```bash
curl -d '{"alpha":"one","beta":"two"}' 'http://127.0.0.1:40755/b'
```

### b-nextjs

```bash
curl -d '{"alpha":"one","beta":"two"}' 'http://127.0.0.1:40755/b'
```

### c-firefox

```bash
curl -d '{"items":[{"kind":"evil"}]}' 'http://127.0.0.1:40755/c'
```

### c-graphql

```bash
curl -d '{"items":[{"kind":"evil"}]}' 'http://127.0.0.1:40755/c'
```

### d-chrome

```bash
curl -d '{"widget":{"id":null}}' 'http://127.0.0.1:40755/d'
```

### e-chrome

```bash
curl -X POST -H 'X-Flaky-Key: yes' 'http://127.0.0.1:40755/e'
```

### f-chrome

```bash
curl -H 'Cookie: session=s3cret' 'http://127.0.0.1:40755/f?need=1'
```

### f-windows

```bash
curl -H 'Cookie: session=s3cret' 'http://127.0.0.1:40755/f?need=1'
```

### anonymized-chrome-saas

```bash
curl -H 'x-crash-token: letmein' -d '{"payload":{"deeply":{"nested":{"trigger":"boom"}}}}' 'http://127.0.0.1:40755/a'
```

## Reading

- Fixture A/B/C/D: the crash lives in the JSON. Surface deletion leaves
  the body almost intact. That is the wedge.
- Fixture F: the crash is a cookie + a query param. Surface deletion is
  enough; structured should tie, not invent work.
- Fixture E: `--confirm 3` keeps `X-Flaky-Key` and drops the one-shot flake.
- Dialects: Chrome bash, Firefox `$''`, Windows `^` + `""`, raw HTTP, HAR.
