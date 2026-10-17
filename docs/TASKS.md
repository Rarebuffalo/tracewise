# Implementation Backlog and Estimate (canonical)

Version 2.0, 2026-10-18. Dependency-ordered. Each task lists the SPEC requirements it implements and the tests that accept it. The traceability is machine-checked by `scripts/check_docs.py`.

**Rules:**

- Offline work first.
- LIVE work (Phase 8) waits for your approval of a test org.
- The OpenAI evaluation (T-605) waits for a key you provision locally.
- Status values: `todo`, `in-progress`, `done` (done = tests exist and pass locally; see the change log).

## 1. Estimate assumptions

| # | Assumption |
|---|---|
| 1 | One developer, ≈5 productive dev-days (dd) per week |
| 2 | Estimates include writing and running each task's unit or replay tests |
| 3 | No re-architecture caused by G-PLAT outcomes. If one occurs, re-estimate. |
| 4 | ≤3 prompt/model iterations in T-605 |
| 5 | The G-0 commercial validation (≈4 dd: interviews + metadata study) is **separate** from these figures |
| 6 | Python + TypeScript customer-repo extractors (D-2) |
| 7 | **Uncertainty ±25%** on the totals. These are estimates, not commitments. |

## 2. Backlog

| ID | Task | Implements (FS) | Accepted by (AT) | Depends on | dd | Status |
|---|---|---|---|---|---|---|
| **Phase 0: repo and docs** | | | | | | |
| T-001 | `git init` (no remote), `.gitignore` (D-3), sensitive-file check, initial local commit | — | — | — | 0.25 | done |
| T-002 | Doc consistency checker (`scripts/check_docs.py`): links, traceability, banned instructions, B-case consolidation | — | — | — | 0.25 | done |
| **Phase 1: foundation (offline)** | | | | | | |
| T-101 | Project scaffold: `pyproject.toml` (uv), ruff, mypy, pytest, Makefile, package `tracewise` | FS-INS-1 | — | T-001 | 0.5 | done |
| T-102 | Settings (env, `SecretStr`), JSON logging, correlation IDs; secrets never logged | FS-SEC-5 | AT-SEC-05 | T-101 | 0.5 | done |
| T-103 | Contracts: webhook event, job payload, Diagnosis v2 (Pydantic) | FS-EVT-1, FS-DX-4, FS-DX-5 | AT-DX-12 | T-101 | 0.75 | done |
| T-104 | DB schema + Alembic + repositories (ARCHITECTURE §3), incl. `publication` | FS-EVT-4, FS-PUB-1, FS-PUB-2 | AT-EVT-06 | T-103 | 1.5 | todo |
| T-105 | Postgres job queue: tx enqueue, SKIP LOCKED claim, lease, backoff, dead letter, ≤2 per installation | FS-EVT-2, FS-EVT-4, FS-EVT-6 | AT-EVT-05, AT-REL-04 | T-104 | 1.5 | todo |
| T-106 | Webhook endpoint: raw-body HMAC (constant-time), 25 MB cap, event filter, delivery + run dedupe | FS-EVT-1, FS-EVT-3, FS-EVT-4 | AT-EVT-01, AT-EVT-02, AT-EVT-03, AT-SEC-02 | T-105 | 1.0 | todo |
| **Phase 2: deterministic pre-pass (offline)** | | | | | | |
| T-201 | GitHub log envelope parser; step slicing driven by jobs-API `steps[]`; job/step/command identification | FS-LOG-2, FS-SEC-2 | AT-LOG-02, AT-SEC-11 | T-103 | 1.0 | done |
| T-202 | Sanitiser (ANSI/OSC/C1/CR) + secret redaction | FS-LOG-5 | AT-LOG-06, AT-SEC-04 | T-101 | 0.75 | done |
| T-203 | Python extractors: pytest, traceback, ruff, mypy | FS-DX-9 | AT-LOG-05 | T-201 | 1.25 | done |
| T-204 | TypeScript extractors: tsc, jest/vitest, eslint | FS-DX-9 | AT-LOG-05 | T-201 | 1.25 | done |
| T-205 | Generic extractor; primary ranking; cascades; sibling grouping; fingerprint | FS-DX-1, FS-DX-2, FS-DX-9 | AT-DX-02, AT-DX-03, AT-DX-07, AT-DX-16, AT-SEC-15 | T-203, T-204 | 1.0 | done |
| T-206 | Streaming and truncation (≤2 MB per job; `log_truncated`) | FS-LOG-4 | AT-LOG-04 | T-201 | 0.5 | done |
| **Phase 3: GitHub client and code context (offline with REPLAY/fixtures)** | | | | | | |
| T-301 | App JWT; installation tokens scoped to repo + permissions; memory-only cache | FS-INS-2, FS-SEC-5 | AT-SEC-01, AT-SEC-05 | T-102 | 0.5 | todo |
| T-302 | REST client: pagination, primary/secondary rate limits, retries, log redirect, 404/410/403 handling | FS-LOG-1, FS-LOG-3, FS-ERR-2 | AT-LOG-01, AT-LOG-03, AT-REL-02 | T-301 | 1.25 | todo |
| T-303 | PR association (same-repo + fork-aware) | FS-PUB-7 | AT-PUB-09, AT-PUB-10 | T-302 | 0.5 | todo |
| T-304 | Code context: shallow single-commit fetch, hardening, size caps, contents-API fallback, `finally` cleanup + startup sweep | FS-CTX-1, FS-CTX-4 | AT-CTX-01, AT-CTX-02, AT-SEC-06 | T-302 | 1.5 | todo |
| T-305 | Read-only tools (`read_file`, `grep`, `list_dir`, `get_diff`) with realpath confinement, limits, tool log | FS-CTX-2, FS-CTX-5 | AT-CTX-03, AT-CTX-04, AT-SEC-09 | T-304 | 1.0 | todo |
| T-306 | Trigger diff + `touches_implicated` (code-computed) | FS-CTX-3, FS-ATR-1, FS-SEC-2 | AT-ATR-01, AT-ATR-02, AT-ATR-03, AT-ATR-09 | T-302, T-205 | 0.75 | todo |
| **Phase 4: investigation (offline with the fake provider)** | | | | | | |
| T-401 | Provider interface; deterministic fake provider; OpenAI adapter (not exercised offline) | FS-DX-3 | AT-SEC-10 | T-103 | 1.0 | todo |
| T-402 | Investigator loop: delimited untrusted data, ≤12 tool calls, ≤120 s, schema output, 1 repair, categories | FS-DX-3, FS-DX-5, FS-DX-6, FS-SEC-1 | AT-DX-01, AT-DX-04, AT-DX-08, AT-DX-09, AT-DX-10, AT-DX-11, AT-SEC-08 | T-401, T-305 | 1.5 | todo |
| T-403 | Validator rules 1–8; inconclusive fallback | FS-DX-4, FS-DX-5, FS-DX-8, FS-CTX-2, FS-SEC-1 | AT-DX-05, AT-DX-13, AT-DX-14 | T-402 | 1.25 | todo |
| T-404 | Confidence band + basis (deterministic corroboration) | FS-DX-7 | AT-DX-12 | T-403 | 0.25 | todo |
| **Phase 5: report and publishing (offline with REPLAY)** | | | | | | |
| T-501 | Renderer: all report sections, escaping, cap, code-built links, AI-agent block, PR merge caveat | FS-RPT-1, FS-RPT-2, FS-RPT-3, FS-RPT-4, FS-RPT-5, FS-RPT-6, FS-RPT-7, FS-RPT-8, FS-RPT-9, FS-RPT-10, FS-CTX-6, FS-SEC-1 | AT-RPT-01, AT-RPT-02, AT-RPT-03, AT-RPT-04, AT-RPT-05, AT-RPT-06, AT-RPT-07, AT-RPT-08, AT-RPT-09, AT-RPT-11, AT-SEC-07 | T-403 | 1.25 | todo |
| T-502 | Publishers: commit comment (write-once), PR comment (upsert by marker + author), Check Run (neutral, `external_id`, lookup by name); `publication` table idempotency | FS-PUB-1, FS-PUB-2, FS-PUB-3, FS-PUB-4, FS-PUB-5 | AT-PUB-01, AT-PUB-02, AT-PUB-03, AT-PUB-04, AT-PUB-05, AT-PUB-06 | T-501, T-303, T-104 | 1.5 | todo |
| T-503 | Failure and permission paths: could-not-complete, `logs_unavailable`, `permission_denied`, `unpublished_permission` | FS-ERR-1, FS-ERR-3, FS-LOG-3, FS-PUB-5 | AT-REL-01, AT-REL-05 | T-502 | 0.75 | todo |
| **Phase 6: offline benchmark** | | | | | | |
| T-601 | Synthetic harness: fixture-repo builder (C0/C1/C2), local tool runs, GitHub-like log envelope, jobs-API fixtures | — | AT-DX-15 | T-201 | 2.0 | todo |
| T-602 | Cases B-01…B-17, A-04…A-06, E-01…E-06 with committed `truth.yaml` | — | AT-DX-15 | T-601 | 2.0 | todo |
| T-603 | Scorer (BENCHMARK §4) + per-track report | — | AT-DX-15 | T-602 | 1.0 | todo |
| T-604 | META runner P-01…P-03 (anonymous REST, provenance recorded) | FS-ATR-2 | AT-ATR-05, AT-SEC-14 | T-603 | 0.5 | todo |
| T-605 | Measured evaluation with OpenAI (**needs a key you provide locally**); model choice (UD-3); cost and latency measured | FS-DX-3, FS-OPS-2 | AT-DX-15, AT-OPS-02 | T-603, T-402 | 1.5 | todo |
| **Phase 7: pilot hardening** | | | | | | |
| T-701 | Installation lifecycle (created, deleted, suspend, repos added/removed; in-flight cancel) | FS-INS-3, FS-INS-4 | AT-INS-03, AT-INS-04 | T-105 | 0.75 | todo |
| T-702 | Recovery: deliveries API redelivery + failed-run sweep | FS-EVT-5 | AT-REL-03 | T-302, T-105 | 1.0 | todo |
| T-703 | Quotas + over-quota notice | FS-QTA-1 | AT-QTA-01 | T-502 | 0.5 | todo |
| T-704 | Retention and purge jobs | FS-SEC-3 | AT-SEC-12 | T-104 | 0.75 | todo |
| T-705 | Postgres RLS (transaction-local context; non-owner role) | FS-SEC-6 | AT-SEC-03 | T-104 | 1.0 | todo |
| T-706 | Observability: stage timings, usage and cost records, alerts | FS-OPS-1, FS-OPS-2 | AT-OPS-01, AT-OPS-02 | T-105 | 0.75 | todo |
| **Phase 8: LIVE (gated: needs your approved test org + dev App)** | | | | | | |
| T-801 | Dev App registration checklist and execution **by you** (permissions per FS-INS-2) | FS-INS-1, FS-INS-2 | AT-INS-01, AT-INS-02 | Approval | 0.5 | todo |
| T-802 | Live gates G-PLAT-1…7 | FS-EVT-1, FS-PUB-1, FS-PUB-5, FS-RPT-10, FS-INS-3 | AT-EVT-04, AT-PUB-05, AT-PUB-06, AT-PUB-08, AT-PUB-10 | T-801, T-502 | 1.5 | todo |
| T-803 | LIVE versions of the publishing and context tests (Track F) | FS-PUB-1, FS-PUB-2, FS-PUB-3, FS-CTX-1 | AT-PUB-01, AT-PUB-02, AT-PUB-03, AT-CTX-01 | T-802 | 1.5 | todo |
| **Phase 9: pilot readiness** | | | | | | |
| T-1001 | Privacy notice (names the provider and model family) + pilot terms template | FS-SEC-4 | AT-SEC-13 | T-605 | 0.5 | todo |
| T-1002 | Staging and production deployment (ADR-09 decided then) | — | — | T-706 | 1.5 | todo |
| T-1003 | Runbooks + staging soak (effort only; calendar-bound) | — | — | T-1002 | 1.5 | todo |
| **P2 (after benchmark validation)** | | | | | | |
| T-901 | Lane history (last green / first red, `head_repo_id`) | FS-ATR-2 | AT-ATR-04, AT-ATR-05, AT-ATR-06 | T-603 | 2.0 | todo |
| T-902 | Flaky suspicion from attempts and history | FS-ATR-3 | AT-ATR-07 | T-901 | 0.75 | todo |
| T-903 | Dependency drift with structured corroboration | FS-ATR-4 | AT-ATR-08 | T-901 | 1.25 | todo |
| T-904 | Outcome tracking on editable surfaces | FS-PUB-6 | AT-PUB-07 | T-502, T-901 | 0.75 | todo |

## 3. Totals (bottom-up)

| Scope | Tasks | dd |
|---|---|---|
| Phase 0 | T-001, T-002 | 0.5 |
| Offline MVP core (Phases 1–6, excluding T-605) | T-101 … T-604 | **30.0** |
| Measured OpenAI evaluation | T-605 | 1.5 |
| Pilot hardening | Phase 7 | 4.75 |
| LIVE gates and tests | Phase 8 | 3.5 |
| Pilot readiness | Phase 9 | 3.5 |
| **Total to the first external pilot** | | **≈43.75 dd (≈9 weeks at 5 dd/week; ±25%)** |
| P2 differentiation | T-901…T-904 | 4.75 |

**Comparison:** the S1 estimate was ≈31.5 dd for an **attribution-only** pilot. The increase comes from the parity components: code context, investigator, validator v2, renderer and the three publishers. Calendar-bound items (interviews, soak, your approvals) are not included.

## 4. Critical path

T-001 → T-101 → T-103 → T-201 → T-203/T-204 → T-205 → (T-301 → T-302 → T-304 → T-305) → T-401 → T-402 → T-403 → T-501 → T-502 → T-601 → T-602 → T-603 → T-605 → [approval] T-801 → T-802 → T-803 → T-1002.

**Can proceed in parallel with offline work:** G-0 validation, T-202, T-206, T-306, T-104/T-105/T-106.
