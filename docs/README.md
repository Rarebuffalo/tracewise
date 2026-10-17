# Tracewise Documentation Index (canonical)

**This directory is the single source of truth** (since 2026-10-18). Everything under `research/` is history or evidence; see [research/README.md](../research/README.md).

| Document | Purpose |
|---|---|
| [SPEC.md](SPEC.md) | MVP requirements (FS-…), data contracts, validator rules |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and decisions (ADR-01…18), data model, security boundaries |
| [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) | Gates A–E, package layout, analysis flow, configuration, controls |
| [TASKS.md](TASKS.md) | Dependency-ordered backlog with traceability and a bottom-up estimate |
| [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md) | Acceptance tests (AT-…) and the MVP gate |
| [BENCHMARK.md](BENCHMARK.md) | Synthetic cases B-01…B-17, Tracks A–F, public-metadata cases, grading |
| [VALIDATION-PLAN.md](VALIDATION-PLAN.md) | Commercial gate G-0 (interviews, metadata-only G-2) |
| [DECISIONS.md](DECISIONS.md) | Closed decisions (Q1–Q6), applied defaults (D-1…D-3), open items |
| [DOC-CHANGE-PLAN.md](DOC-CHANGE-PLAN.md) | The 15 blocking corrections and the cleanup plan (change record) |
| [CHANGELOG.md](CHANGELOG.md) | What changed, with validation results |

**Rules that apply everywhere:**

- No personal, global or CLI GitHub credentials. Benchmarks use synthetic data and anonymous public metadata only.
- No accuracy, latency or cost claims until measured (T-605).
- LIVE GitHub tests need your approval of a dedicated test org.

**Consistency check:** `python3 -I scripts/check_docs.py`
