# Benchmark rerun: Phase 28 final offline gate

**Protocol validation, not model accuracy.** The provider is the scripted oracle.

| Item | Value |
|---|---|
| Code | `2a9167e` (includes the P-1 snippet and replacement redaction) |
| Command | `uv run python -m tracewise.bench run --provider oracle --reps 3 --include-slow --out .bench-results/2026-10-19-phase28-oracle-full-slow` |
| Wall time | 1 min 48 s |
| `verify` | `OK: 26 cases, truth lock matches` (`931fe20a4c2004f8…`) |
| Truth files | No case file changed since d4745aa |
| Result | Run id `04e8c1a72a5291fc`; 115 required, 111 executed, 4 not applicable, 0 errors, complete. All 115 outcomes are identical to Phase 0. The redaction did not change any scored snippet, because the truth snippets contain no secrets. |

Unchanged review items: A-05 fails only `first_error`, and B-04/C1 is the one safety failure (`high_confidence_wrong`).
