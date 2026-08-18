# Reduction report

Measured against the in-repo fixture server on loopback.
Bytes are compact-curl encodings of the parsed request.

| Case | In | Out | Components | Reduction | Probes | Confirm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A nested JSON + header (killer demo) | 15,615 | 117 | 964 → 6 | 99.25% | 68 | 20/20 |
| B pair fields | 180 | 65 | 21 → 4 | 63.89% | 31 | 5/5 |
| C array item | 240 | 64 | 36 → 4 | 73.33% | 33 | 5/5 |
| D body-text oracle (HTTP 200) | 158 | 59 | 12 → 3 | 62.66% | 24 | 5/5 |
| E flaky / confirmation | 147 | 61 | 6 → 1 | 58.50% | 23 | 5/5 |
| F cookies + query | 183 | 66 | 12 → 2 | 63.93% | 24 | 5/5 |

## Killer demo

```
15,615 bytes -> 117 bytes
964 components -> 6
99.25% reduction
same failure: YES (20/20)
```

Structured JSON reduction is what takes fixture A from dozens of
object keys down to `payload.deeply.nested.trigger`. Header/query
deletion alone cannot do that.
