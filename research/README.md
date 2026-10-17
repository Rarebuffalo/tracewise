# Research Index (history and evidence)

**Not a source of truth for implementation.** The canonical documents are in [../docs/](../docs/README.md).

## Contents

| Path | What it is | Status |
|---|---|---|
| `final-evidence-review/` | S4 evidence and architecture review (2026-10-17): decision report, correction matrix, platform verification, evidence ledger, public CI metadata and GitHub docs snapshots | Dated record + evidence (unchanged) |
| `final-audit-public/` | S3 public-only competitor audit (2026-10-17) + public evidence + provenance | Dated record + evidence. Its spec and tests are superseded by `docs/`. |
| `final-audit/` | `PROVENANCE-QUARANTINE.md` + S2 evidence. **Contains quarantined authenticated artifacts; never use them as evidence.** Excluded from git (D-3). | Kept untouched |
| `REPOSITORY-AUDIT-2026-10-18.md` | Workspace audit that led to the 2026-10-18 cleanup | Dated record |
| `archive/2026-10-15-s1-research/` | Original market and competitor research, first MVP plan, executive summary, plan review, doc 04 (benchmark) and doc 07 (GTM) | Superseded; see its README |
| `archive/2026-10-15-s1-plan/` | S1 engineering plan set (attribution-only design) | Superseded by `docs/` |
| `archive/2026-10-17-s2-audit-quarantined/` | S2 audit, spec and tests built partly on quarantined evidence | Superseded; do not follow |

## Old → new path map

Dated records (S3, S4, the repository audit) were **not edited**. Their references to the files below resolve here.

| Original path | Moved to | Canonical replacement |
|---|---|---|
| research/01-product-teardown.md | `archive/2026-10-15-s1-research/` | `final-evidence-review/COMPETITOR-BEHAVIOR-VERIFICATION.md` |
| research/02-architecture-reconstruction.md | `archive/2026-10-15-s1-research/` | `docs/ARCHITECTURE.md` |
| research/03-competitor-matrix.md | `archive/2026-10-15-s1-research/` | (historical market data; no replacement) |
| research/04-failure-benchmark.md | `archive/2026-10-15-s1-research/` | `docs/BENCHMARK.md` (B-01…B-16 verified by `scripts/check_docs.py`) |
| research/05-opportunity-analysis.md | `archive/2026-10-15-s1-research/` | (historical rationale) |
| research/06-mvp-technical-plan.md | `archive/2026-10-15-s1-research/` | `docs/IMPLEMENTATION-PLAN.md` |
| research/07-validation-and-gtm.md | `archive/2026-10-15-s1-research/` | `docs/VALIDATION-PLAN.md` |
| research/08-sources-and-confidence.md | `archive/2026-10-15-s1-research/` | `final-evidence-review/EVIDENCE-LEDGER.md` |
| research/EXECUTIVE-SUMMARY.md | `archive/2026-10-15-s1-research/` | `final-evidence-review/FINAL-DECISION-REPORT.md` |
| research/PLAN-REVIEW.md | `archive/2026-10-15-s1-research/` | `docs/DOC-CHANGE-PLAN.md` |
| research/IMPLEMENTATION-PLAN.md | `archive/2026-10-15-s1-plan/` | `docs/IMPLEMENTATION-PLAN.md` |
| research/IMPLEMENTATION-TASKS.md | `archive/2026-10-15-s1-plan/` | `docs/TASKS.md` |
| research/ARCHITECTURE-DECISIONS.md | `archive/2026-10-15-s1-plan/` | `docs/ARCHITECTURE.md` |
| research/DECISION-REGISTER.md | `archive/2026-10-15-s1-plan/` | `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` |
| research/TEST-AND-RELEASE-PLAN.md | `archive/2026-10-15-s1-plan/` | `docs/ACCEPTANCE-TESTS.md`, `docs/BENCHMARK.md` |
| research/RESOURCE-AND-SETUP-CHECKLIST.md | `archive/2026-10-15-s1-plan/` | `docs/IMPLEMENTATION-PLAN.md` §4 |
| research/OPEN-QUESTIONS.md | `archive/2026-10-15-s1-plan/` | `docs/DECISIONS.md` |
| research/FINAL-REVERSE-ENGINEERING-AUDIT.md (S2) | `archive/2026-10-17-s2-audit-quarantined/` | `final-audit-public/FINAL-REVERSE-ENGINEERING-AUDIT.md` |
| research/VERIFIED-FEATURE-SPEC.md (S2) | `archive/2026-10-17-s2-audit-quarantined/` | `docs/SPEC.md` |
| research/TRACEWISE-PARITY-ACCEPTANCE-TESTS.md (S2) | `archive/2026-10-17-s2-audit-quarantined/` | `docs/ACCEPTANCE-TESTS.md` |
