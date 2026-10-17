# Change Log

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
