# Implementation Plan (canonical)

Version 2.0, 2026-10-18.

| Topic | Document |
|---|---|
| Requirements | [SPEC.md](SPEC.md) |
| Decisions | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Tasks and estimate | [TASKS.md](TASKS.md) |
| Tests | [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md) |
| Benchmark | [BENCHMARK.md](BENCHMARK.md) |
| Commercial gate | [VALIDATION-PLAN.md](VALIDATION-PLAN.md) |

This replaces `research/archive/2026-10-15-s1-plan/IMPLEMENTATION-PLAN.md` (attribution-only, LLM off). The S1 plan's still-valid detail on tenancy, threat model and operations is summarised in §5–§6; the archived file remains available for history.

## 1. Gates

| Gate | Condition | Blocks |
|---|---|---|
| **A: spec/tasks agree** | `scripts/check_docs.py` passes (traceability, no banned instructions) | Any feature implementation |
| **B: commercial (G-0)** | [VALIDATION-PLAN.md](VALIDATION-PLAN.md) §4 | Committing to the full build and the pilot (not offline work) |
| **C: live platform** | Your approval of a dedicated test org + dev App; then G-PLAT-1…7 (T-802) | Accepting the publishing and integration code as complete; any external install |
| **D: comparative claims** | AT-CMP-01, with your approval | Any "better than X" statement |
| **E: measured evaluation** | T-605 with a locally provisioned OpenAI key | Model choice; any accuracy, cost or latency figure |

## 2. Package layout (Python)

```text
tracewise/                       repo root (~/tracewise)
├─ pyproject.toml  uv.lock  Makefile  .gitignore  .env.example
├─ src/tracewise/
│  ├─ config.py   logging.py   contracts.py
│  ├─ web/        app.py  webhooks.py  health.py                 (T-106)
│  ├─ jobs/       queue.py  worker.py  handlers/                 (T-105, T-701…T-704)
│  ├─ db/         repositories.py  session.py  migrate.py  migrations/   (T-104, T-705)
│  ├─ github/     endpoints.py  errors.py  auth.py  client.py  pulls.py  publish.py   (T-301…T-303, T-502)
│  ├─ prepass/    envelope.py  sanitize.py  extractors/{python,typescript,generic}.py  primary.py  (T-201…T-206)
│  ├─ context/    workspace.py  tools.py  trigger.py             (T-304…T-306)
│  ├─ investigate/ provider.py  fake.py  openai_provider.py  loop.py  validate.py  confidence.py  (T-401…T-404)
│  ├─ report/     render.py                                      (T-501)
│  └─ bench/      harness.py  cases/  score.py  meta.py          (T-601…T-604)
├─ tests/ unit/ replay/ bench/ fixtures/
├─ scripts/check_docs.py
├─ docs/   (canonical)
└─ research/ (history + evidence; not imported by code)
```

**No TypeScript code** (D-2). TypeScript appears only as *fixture repos* for the extractors.

## 3. Analysis flow (one job)

1. **Load and filter.** Load the job, then the installation token (scoped). On 401 or 404 from token mint → `cancelled_uninstalled`.
2. **Jobs.** List jobs for the attempt. Failed jobs and steps come from the jobs API.
3. **Logs.** Download the failed logs: stream, slice, sanitise and redact, and set the truncation flag. 404/410 → `logs_unavailable`.
4. **Pre-pass.** Run the extractors, then primary error, siblings and fingerprint.
5. **Trigger diff.** Compare the trigger diff with the implicated paths → `touches_implicated`.
6. **Code context.** Shallow fetch at `head_sha` into a confined workspace (contents-API fallback).
7. **Investigation.** The provider interface runs ≤12 read-only tool calls and returns a structured Diagnosis.
8. **Validation.** Rules 1–8 decide `diagnosed` or `inconclusive`.
9. **Render.** Build the report.
10. **Publish.** Resolve the PR via the API. Then:
    - PR comment (upsert) if a PR is found, otherwise a commit comment (write-once);
    - Check Run (create or update by `external_id`).
11. **Persist and clean up.** Persist the analysis, publications and usage. Delete the workspace in `finally`.

## 4. Configuration (`.env.example`; placeholders only, never real values)

| Variable | Purpose | Required |
|---|---|---|
| `TW_ENV` | local, test, staging or prod | yes |
| `DATABASE_URL` | Postgres (runtime role) | yes, for DB tasks |
| `DATABASE_URL_MIGRATIONS` | Postgres (owner role) | yes, for migrations |
| `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `GITHUB_WEBHOOK_SECRET` | **Project-scoped dev App** (LIVE only) | LIVE only |
| `LLM_PROVIDER` | `fake` (default offline) or `openai` | yes |
| `OPENAI_API_KEY` | Only when `LLM_PROVIDER=openai` (T-605 onward); local env only | no (offline) |
| `LLM_MODEL` | Chosen by T-605 | no (offline) |
| `INVESTIGATION_MAX_TOOL_CALLS` (12), `INVESTIGATION_TIMEOUT_S` (120), `LOG_MAX_BYTES_PER_JOB` (2 MB), `REPORT_MAX_CHARS` (60000) | Limits | no |

**Removed vs S1:** `GITHUB_TOKEN_LAB` (personal PAT) and all `gh` CLI usage.

## 5. Security controls (carried and extended)

| Area | Control | Tests |
|---|---|---|
| Ingress | HMAC; size caps; delivery + run dedupe | AT-SEC-02, AT-EVT-06 |
| Untrusted content | Sanitise, redact, delimit; jobs-API steps (spoofing) | AT-LOG-06, AT-SEC-04, AT-SEC-11 |
| Model | Read-only tools; limits; schema; validator; escaping; code-built links | AT-SEC-07…10, AT-DX-14 |
| Workspace | Hooks off; LFS off; no submodules; realpath confinement; cleanup | AT-CTX-01, AT-CTX-03, AT-SEC-06, AT-SEC-09 |
| Tenancy | Scoped tokens; RLS (P1) | AT-SEC-03 |
| Credentials | ADR-16 | AT-SEC-05, AT-SEC-14 |

## 6. Operations (P1, summarised from S1)

- Health and readiness endpoints.
- JSON logs with correlation IDs.
- A per-analysis usage and cost record.
- Retention and purge jobs.
- Reconciliation and sweep.
- Runbooks for: failed deliveries, stuck jobs, rate limits, provider outage (fallback = inconclusive "could not complete"), invalid model output, failed migration.

Hosting is chosen at pilot time (ADR-09).

## 7. What exists today

See [README.md](README.md) and [TASKS.md](TASKS.md) statuses. **Before 2026-10-18 no application code existed.**
