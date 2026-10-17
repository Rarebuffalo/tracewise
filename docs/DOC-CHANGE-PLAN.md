# Documentation Change Plan (2026-10-18)

This implements your decisions Q1–Q6 of 2026-10-18. It is written **before** any file is moved or replaced.

Sources:

- [REPOSITORY-AUDIT-2026-10-18.md](../research/REPOSITORY-AUDIT-2026-10-18.md);
- `research/final-evidence-review/IMPLEMENTATION-PLAN-CORRECTION-MATRIX.md` (CM-IDs).

## 0. Approach

The S1 plan set (2026-10-15) is large: `IMPLEMENTATION-PLAN.md` alone is ≈100 KB. It is built on the superseded attribution-only design. Patching it in place would leave mixed old and new instructions.

Instead, a **new canonical set** is written in `docs/`. Still-valid S1 content is carried over: data model, queue, tenancy, threat model, operations. The S1 files are archived unchanged.

| Canonical file (new) | Replaces (archived, not deleted) |
|---|---|
| `docs/SPEC.md` | `research/final-audit-public/VERIFIED-FEATURE-SPEC.md` (S3, stays in place as an audit record); S2 `research/VERIFIED-FEATURE-SPEC.md` |
| `docs/ARCHITECTURE.md` (ADRs v2) | `research/ARCHITECTURE-DECISIONS.md`, `research/DECISION-REGISTER.md` |
| `docs/BENCHMARK.md` | `research/04-failure-benchmark.md` §2, `research/TEST-AND-RELEASE-PLAN.md` §2, `research/final-evidence-review/BENCHMARK-AND-GROUND-TRUTH-REVIEW.md` §3–4 (record kept), S3 B-17 |
| `docs/ACCEPTANCE-TESTS.md` | S3 `TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` (record kept); S2 duplicate; `research/TEST-AND-RELEASE-PLAN.md` |
| `docs/IMPLEMENTATION-PLAN.md` | `research/IMPLEMENTATION-PLAN.md`, `research/RESOURCE-AND-SETUP-CHECKLIST.md` |
| `docs/TASKS.md` (backlog + estimate) | `research/IMPLEMENTATION-TASKS.md` |
| `docs/VALIDATION-PLAN.md` (G-0) | `research/07-validation-and-gtm.md` (interview script carried over) |
| `docs/DECISIONS.md` | `research/OPEN-QUESTIONS.md` (resolved items closed; open items kept) |
| `docs/README.md` | — (canonical index) |

## 1. The 15 blocking corrections

| # | CM | Affected (old) files | Conflict | Change in the canonical set | Rationale | Product decision? |
|---|---|---|---|---|---|---|
| 1 | CM-02 | `IMPLEMENTATION-PLAN.md` L171 (FR-018), L329, §8; `ARCHITECTURE-DECISIONS.md` ADR-08; `DECISION-REGISTER.md` DR-27, DR-28 | LLM off in the MVP; only adjudicates among candidates | Investigation **on by default**, after a deterministic pre-pass. Bounded and read-only. Provider interface, **OpenAI first** (Q4). Model chosen by measured eval. No key needed for offline tests (fake provider). | Parity requires a line-level cause and fix (EV-C07/C08) | Decided (Q1, Q4) |
| 2 | CM-03 | PLAN §4.4.3 L370; ADR-06; DR-09, DR-15 | `pull_requests:write` dropped; Check-Run-only output | Permissions: Actions r, Contents r, Metadata r, Pull requests w, Checks w. Three publishers. | EV-C04/C06; EV-P09; Q2 | Decided (Q2) |
| 3 | CM-04 | PLAN §4.4.7, §7.8 L5 | No general code-context component | Code-context component: shallow single-commit fetch into a confined workspace, plus a contents-API fallback | Parity needs code reading (EV-C08) | No |
| 4 | CM-05 | PLAN §4.6.2 `Diagnosis`; LLM schema v1 | No root cause, why, location, fix, files examined, step/command fields | Diagnosis v2 + validator rules 1–8 (SPEC §3) | EV-C07, EV-C12 | No |
| 5 | CM-06 | PLAN L439, L643, L853 (`pr_numbers` from the payload) | `workflow_run.pull_requests` is unreliable | PR association by API, fork-aware (SPEC FS-PUB-7) | EV-P23, EV-P24, EV-P10 | No |
| 6 | CM-09 | `TEST-AND-RELEASE-PLAN.md` §6; `IMPLEMENTATION-TASKS.md` L26, L631 | G-INT depends on Phase 6 and on log-labelled real data | G-INT = synthetic Tracks A–E + public-metadata Track D, reported separately. No real-log accuracy gate. | EV-P13; your benchmark decision | No |
| 7 | CM-15 | `IMPLEMENTATION-TASKS.md` T5.02, T5.03 | No per-surface idempotency (commit comments are not editable) | Commit comment write-once; PR comment upsert; Check Run `external_id` update | EV-P09, EV-P02 | No |
| 8 | CM-18 | PLAN, TASKS, TEST plan (no mention) | No log-spoofing defence | Steps from the jobs API; structured corroboration for dependency and runner claims; Track E cases | Repo output is attacker-controlled | No |
| 9 | CM-19 | TASKS L643 (T4B.05, optional phase) | Injection tests optional | Injection and spoofing tests are **MVP P0** | The LLM is on by default | No |
| 10 | CM-21 | TASKS T0.01–T0.03, T3.09; `RESOURCE-AND-SETUP-CHECKLIST.md` R3, L109 | `gh auth login`, personal lab PAT, authenticated log downloads | **Removed.** Phase 0 uses anonymous public metadata only. Parser goldens come from synthetic offline logs. | Your no-credentials rule; EV-P13 | Decided |
| 11 | CM-24 | TASKS Phases 1–5 | No tasks for the parity components | New backlog with SPEC ↔ TASK ↔ TEST traceability | Spec and tasks must agree before coding | No |
| 12 | CM-25 | PLAN L58, L1563, L1574 | The estimate predates the scope change | New bottom-up estimate in `docs/TASKS.md` | — | No |
| 13 | CM-26 | TEST plan §2–§6; doc 04 §2 | Benchmark written for attribution-only categories; spread over 4 files | A single `docs/BENCHMARK.md`. B-01…B-16 consolidated and mapped to parity categories plus trigger-diff expectations. B-17 and Tracks A–F added. | Q6 condition for archiving doc 04 | No |
| 14 | CM-27 | PLAN §16 G-2; doc 07 §3 | G-2 needs log labels | G-2 = a **metadata-only lower bound**: the share of red runs where the same job/step already failed before the push, or the same SHA passed on another attempt | No-credentials rule | **Yes: D-1 (threshold)** |
| 15 | CM-28 | Checklist R3; TASKS T0.01; EXECUTIVE-SUMMARY L105; doc 04 L97; OQ-02 | Personal credentials and CLI login | Only project-scoped App credentials, provisioned by you when live tests are approved. No CLI login in tooling. | Your rule; S3 provenance incident | Decided |

### Non-blocking items carried into the canonical set

| CM / finding | Fix |
|---|---|
| CM-01 | Commit comments need Contents read |
| CM-07 | `head_repo_id` added to the lane key |
| CM-08 | No T2.06; delivery endpoint paths recorded |
| CM-10 / CM-12 / CM-13 | Cost, quota and latency figures withdrawn until measured; "60 seconds" copy removed |
| CM-14 | Quota task |
| CM-16 / CM-17 | Uninstall and publish-403 paths |
| CM-20 | `startup_failure` gated |
| CM-22 | Failed-run sweep |
| CM-23 | Single provisional output cap |
| CM-29 / CM-30 | Fork gate; merge-commit caveat |
| Audit F-03 | REAL-SET / project-token options removed |

## 2. Conflicts with your requirements, and how each is resolved

| Item | Conflict | Resolution |
|---|---|---|
| S3 tests §0 option (a) and S3 audit §7.2 option 1 | Project-token re-download of public logs | Not carried over. Benchmark = synthetic + anonymous metadata (job/step level). |
| S3 spec FS-SEC-5 | "Benchmark uses a project-scoped token" | Rewritten: benchmark tooling uses **no** GitHub credentials |
| S3 tests AT-DX-15 / ATR-09 real-accuracy gates (≥70%) | Unmeasurable, and implies a performance claim | Removed. Only synthetic targets (labelled *targets*, not results) and metadata-track checks remain. |
| S1 cost and latency figures, "60 seconds" copy | Unsupported claims | Removed from the canonical set. Measured later. |
| Q3 "Python + TypeScript" | Ambiguous: product implementation language vs **supported customer-repo languages** | Implementation stays **Python only**. Nothing in the GitHub integration requires TypeScript, and the MVP has no UI. Analysis supports **Python and TypeScript customer repos** (pytest/ruff/mypy and tsc/jest/vitest/eslint). See D-2. |
| Q5 git staging | `research/final-audit/evidence/` holds the quarantined third-party logs | Files stay untouched on disk. Proposed `.gitignore` entry so they never enter history (D-3). |
| "R-04" naming | In S1 docs "R-04" means *research doc 04*; in S2 "R-01…R-15" are quarantined real cases | The canonical docs say "doc 04"; the R-case IDs are not reused |

## 3. Decisions flagged (defaults applied unless you say otherwise)

| ID | Decision | Default applied |
|---|---|---|
| **D-1** | G-2 threshold on the metadata-only lower bound | Report the lower bound with its CI. **≥15% supports BUILD.** Below 15% does **not** alone trigger ABANDON, because dependency and environment causes are uncountable without logs. Interviews (G-1) and commitments (G-3) decide. |
| **D-2** | Q3 interpretation | Python-only implementation; Python + TypeScript customer-repo support |
| **D-3** | Git history excludes `research/final-audit/evidence/` (quarantined) | Excluded via `.gitignore`; files untouched |

## 4. Exact file-operation plan

There are no deletions. Moves use `mv` within `~/tracewise`.

```text
CREATE  docs/{README,SPEC,ARCHITECTURE,BENCHMARK,ACCEPTANCE-TESTS,IMPLEMENTATION-PLAN,TASKS,VALIDATION-PLAN,DECISIONS,DOC-CHANGE-PLAN}.md
CREATE  research/README.md                                   (research index + old→new path map)
MKDIR   research/archive/2026-10-15-s1-research/
MKDIR   research/archive/2026-10-15-s1-plan/
MKDIR   research/archive/2026-10-17-s2-audit-quarantined/
MOVE    research/{01-product-teardown,02-architecture-reconstruction,03-competitor-matrix,05-opportunity-analysis,06-mvp-technical-plan,08-sources-and-confidence,EXECUTIVE-SUMMARY,PLAN-REVIEW}.md
        → research/archive/2026-10-15-s1-research/
MOVE    research/07-validation-and-gtm.md → research/archive/2026-10-15-s1-research/   (after VALIDATION-PLAN carries the script)
MOVE    research/04-failure-benchmark.md  → research/archive/2026-10-15-s1-research/   (ONLY after the B-01…B-16 verification check passes)
MOVE    research/{IMPLEMENTATION-PLAN,IMPLEMENTATION-TASKS,ARCHITECTURE-DECISIONS,DECISION-REGISTER,TEST-AND-RELEASE-PLAN,RESOURCE-AND-SETUP-CHECKLIST,OPEN-QUESTIONS}.md
        → research/archive/2026-10-15-s1-plan/
MOVE    research/{FINAL-REVERSE-ENGINEERING-AUDIT,VERIFIED-FEATURE-SPEC,TRACEWISE-PARITY-ACCEPTANCE-TESTS}.md   (S2 root copies)
        → research/archive/2026-10-17-s2-audit-quarantined/
CREATE  research/archive/*/README.md                          (what superseded each)
UNCHANGED research/final-audit/** (incl. quarantined evidence), research/final-audit-public/**,
          research/final-evidence-review/**, research/REPOSITORY-AUDIT-2026-10-18.md
```

**Reference policy:**

- Active documents (`docs/`, `research/README.md`) are fixed to the new paths.
- Dated audit records (S3, S4, the repository audit) are **not edited**. Their references to moved files resolve through the old→new path map in `research/README.md`.
- A checker (`scripts/check_docs.py`) verifies active-document links and traceability.
