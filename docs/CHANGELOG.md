# Change Log

## 2026-10-18 (b): offline implementation, Phases 0–2

**Tasks done:** T-001, T-002, T-101…T-103, T-201…T-206 (12.0 of 30.0 offline-core dd, as estimated). No network calls, no credentials, no LLM.

### Code

| Area | Files | Notes |
|---|---|---|
| Scaffold (T-101) | `pyproject.toml`, `uv.lock`, `Makefile`, `.env.example` | uv, ruff, mypy `--strict`, pytest. `.env.example` holds placeholders only. Runtime deps: pydantic, pydantic-settings. |
| Settings, logging (T-102) | `src/tracewise/config.py`, `logging.py` | `SecretStr` everywhere. `LLM_PROVIDER=fake` by default; `openai` refuses to start without a local key. JSON logs with a correlation ID. A filter scrubs registered secrets, token shapes and URL credentials from messages, extras and tracebacks. |
| Contracts (T-103) | `src/tracewise/contracts.py` | Webhook subset, `AnalysisJob` (IDs only), Diagnosis v2 with schema-level rules. |
| Pre-pass (T-201…T-206) | `src/tracewise/prepass/` | Steps come from the jobs API; runner timestamps slice the log. Sanitise, then redact. pytest, traceback, ruff, mypy, tsc, jest, vitest and eslint extractors, plus a generic fallback. Ranking, cascades, siblings and fingerprints. Streaming retention ≤2 MB. |

### Spec change (contract)

- Diagnosis v2 `primary_error` + top-level `siblings` became **`primary_errors[]` (1–3)**, each with its own `siblings`.
- **Reason:** FS-DX-2 and AT-DX-16 require ≤3 independent primaries, which the single-object contract could not express. Validator rule 1 already said "each".
- SPEC §3.1 and §3.2 were updated.

### Fixtures

| Kind | Files |
|---|---|
| **Real tool output** | `pytest_b02.out` (B-02 replica, defect at `pricing.py:41`), `ruff_b10.out`, `ruff_full_b10.out`, `mypy_b10.out`, `traceback.out`. All regenerable offline with `scripts/gen_python_fixtures.py`; host paths are rewritten to runner paths. |
| **Hand-written** (`*.handwritten.out`) | tsc, jest, vitest, eslint, from the documented formats. Real TypeScript tool runs need npm downloads; they belong to the benchmark harness (T-601). |

### Bugs found by the tests and fixed

- The tsc regex missed the colon in `file(3,10): error`.
- The error-window detector missed exception names such as `AssertionError`. A 200 MB log dropped its only error.
- The generic extractor took 3.3 s per 50 MB; a prefilter brought it to 1.4 s.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `ruff format --check` | pass |
| `uv run mypy` (strict, 21 files) | pass |
| `uv run pytest -m "not slow"` | **45 passed** |
| `uv run pytest -m slow` | **10 passed**. AT-LOG-04: 200 MB log in ≈50 s, peak RSS < 300 MB. AT-SEC-15: 50 MB per extractor in ≤2 s. |
| `python3 -I scripts/check_docs.py` | PASS |

### Coverage of the acceptance tests touched (honest scope)

| Test | Covered now | Still needs |
|---|---|---|
| AT-LOG-02, AT-LOG-04, AT-LOG-05, AT-LOG-06, AT-SEC-15 | Full | — |
| AT-DX-02, AT-DX-03, AT-DX-07, AT-DX-16 | Pre-pass level | The end-to-end BENCH runs (T-601+) |
| AT-SEC-04 | Redaction | The storage, fake-provider-capture and report assertions (T-104, T-401, T-501) |
| AT-SEC-05 | Logging | Per-installation token scope (T-301) |
| AT-SEC-11 | Step attribution | The "no drift claim above `low`" part (T-306) |
| AT-DX-12 | Schema (band + ≥1 basis) | The corroboration rule (T-404) |

## 2026-10-18: canonical documentation set, archive cleanup, git initialisation

**Decisions applied:** Q1–Q6 (user, 2026-10-18), plus defaults D-1…D-3 ([DECISIONS.md](DECISIONS.md)). The plan of changes was written first: [DOC-CHANGE-PLAN.md](DOC-CHANGE-PLAN.md).

### Created (canonical, `docs/`)

| File | Content |
|---|---|
| `SPEC.md` | 63 requirements, 44 of them P0. New since S3: FS-PUB-7 (API PR association, fork-aware), FS-EVT-5(b) (failed-run sweep), FS-CTX-5/6, FS-DX-9, FS-SEC-5 rewritten (no credentials in benchmark tooling), provider interface with OpenAI first |
| `ACCEPTANCE-TESTS.md` | 90 tests. REAL-SET and project-token options removed. Real-accuracy gates removed. Synthetic **targets** labelled as targets. |
| `BENCHMARK.md` | B-01…B-17 consolidated from doc 04, the TEST-AND-RELEASE amendments, the S4 review and S3's B-17. Tracks A–F; public-metadata cases P-01…P-03; grading. |
| `ARCHITECTURE.md` | ADR-01…18. ADR-06 (three surfaces) and ADR-08 (AI on by default, OpenAI first) supersede the S1 ADRs. Python-only implementation (D-2). |
| `IMPLEMENTATION-PLAN.md` | Gates A–E, layout, flow, configuration (no personal tokens) |
| `TASKS.md` | 48 tasks with traceability and a bottom-up estimate |
| `VALIDATION-PLAN.md` | G-0 without credentials; G-2 as a metadata-only lower bound |
| `DECISIONS.md`, `README.md`, `CHANGELOG.md` | — |
| `scripts/check_docs.py` | Consistency checker (T-002) |

### Moved (archived, content unchanged: SHA-256 verified before and after)

| Destination | Files |
|---|---|
| `research/archive/2026-10-15-s1-research/` | 01, 02, 03, 04, 05, 06, 07, 08, EXECUTIVE-SUMMARY, PLAN-REVIEW |
| `research/archive/2026-10-15-s1-plan/` | IMPLEMENTATION-PLAN, IMPLEMENTATION-TASKS, ARCHITECTURE-DECISIONS, DECISION-REGISTER, TEST-AND-RELEASE-PLAN, RESOURCE-AND-SETUP-CHECKLIST, OPEN-QUESTIONS |
| `research/archive/2026-10-17-s2-audit-quarantined/` | S2 FINAL-REVERSE-ENGINEERING-AUDIT, VERIFIED-FEATURE-SPEC, TRACEWISE-PARITY-ACCEPTANCE-TESTS |

Doc 04 was moved only **after** the checker verified all 16 cases and their ground-truth phrases in `docs/BENCHMARK.md`.

### Unchanged

- `research/final-evidence-review/**`
- `research/final-audit-public/**`
- `research/final-audit/**`, including the quarantined evidence, untouched
- `research/REPOSITORY-AUDIT-2026-10-18.md`

**Deleted:** nothing.

### References

- **Active documents** were fixed to the new paths.
- **Dated records** were not edited. Their references resolve through the path map in `research/README.md`.

### Git

- `git init` on branch `main`, **no remote**.
- `.gitignore` excludes virtualenvs and caches, `.env*` (except `.env.example`), `*.pem`, `*.key`, and `research/final-audit/evidence/` (D-3).

**Pre-staging scan:**

- No secret patterns found. Matches of `sk-…` were inside "flask-…" file names: false positives.
- No credential-like file names.
- The name of the unintended `gh` account appears, as text only, in dated provenance records. It is not a secret; review it before ever adding a remote.

### Validation (actually run)

Command: `python3 -I scripts/check_docs.py`

| Check | Result |
|---|---|
| Links and paths in active docs | **0 missing** |
| Traceability: 63 requirements, 48 tasks, 90 tests | Every FS has ≥1 task and ≥1 test; every referenced task or test exists; every test is referenced |
| Banned instructions in active docs | **0 hits** (`gh auth login`, `gh run list`, personal tokens, the unintended account, REAL-SET, unmeasured latency claims) |
| Doc 04 B-01…B-16 consolidation | **16/16 verified** |
| Overall | **PASS** |

**No product tests exist or were run** as part of this documentation change.
