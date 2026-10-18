# Benchmark rerun: final acceptance audit (Phase 10)

**Protocol validation, not model accuracy.** The provider is the scripted oracle.

## Command

```
uv run python -m tracewise.bench verify
uv run python -m tracewise.bench run --provider oracle --reps 3 --include-slow --out .bench-results/2026-10-19-phase10-oracle-full-slow
```

| Item | Value |
|---|---|
| Code | `9e85a02`. It includes T-706 instrumentation in the analysis path, migrations 0006–0008 and the logging changes. |
| Wall time | 1 min 59 s |
| `verify` | `OK: 26 cases, truth lock matches` |
| Truth lock | `931fe20a4c2004f8…` |
| Truth files | `git diff d4745aa -- src/tracewise/bench/cases` is empty |

## Result

Run id `04e8c1a72a5291fc`. The outcome of every one of the 115 required runs is identical to the Phase 0 and Phase 4 runs.

| Required | Executed | Errored | Missing | Not executed | Not applicable (P2) | Complete |
|---|---|---|---|---|---|---|
| 115 | 111 | 0 | 0 | 0 | 4 | yes |

Unchanged review items (`docs/BENCHMARK-REVIEW-QUEUE.md`):

- A-05 fails only `first_error`.
- B-04/C1 is the one safety failure (`high_confidence_wrong`).
