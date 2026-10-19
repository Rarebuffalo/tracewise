# Change Log

## 2026-10-19 (ai): Phase 21 final offline release-readiness audit

- Re-audit recorded in SECURITY-AUDIT §4. No new defects.
- The whole suite (664, slow included) ran under a session-wide socket guard: **0 external connection attempts**, and the guard was proven to fire.
- `make check`: 653 passed, 11 slow deselected.
- Benchmark rerun identical (`docs/benchmark-runs/2026-10-19-phase21-final-rerun.md`). The truth lock is intact.

## 2026-10-19 (ah): Phase 20 local operator acceptance

`tests/db/test_operator_acceptance.py` walks the 13 operator stages.

**Real components:**
- the uvicorn web process, with every webhook over loopback HTTP and HMAC on the real path;
- Postgres;
- `worker.main()` with a fresh runtime per invocation (a restart each time);
- the tenant-role analysis, audited per transaction;
- the `HTTPProvider` adapter core;
- the investigator, validator and publisher;
- the `ops` and `retention` CLIs.

**Simulated:** GitHub, the model endpoint (provider `fake`) and the git host.

**What it shows:**
- forged signature refused;
- removed repository out of scope;
- duplicate delivery and duplicate run deduplicated;
- a transient Check Run failure, then retry after restart, gives exactly one commit comment and one Check Run;
- the log fetched, and a validated `diagnosed` result at line 41;
- the ops report with no tenant content;
- suspension refuses new runs;
- nothing written after deletion;
- graceful web shutdown and restart, with readiness;
- the retention CLI purges the tenant and leaves a tombstone;
- no token minted for any other installation.

**Test-harness finding (not a product defect):** a simulated restart's new token cache received a token the local git host rejects. The run then fell back, never read the file, and the validator **correctly** abstained (`location_not_examined`). The harness now hands the git host's token to every mint, and the test asserts `diagnosed`, so a silent abstention cannot pass.

**Repeat runs:** chain, adversarial, signal, cross-phase and acceptance ×3: 18 passed each. DB suite in reverse order: 258 passed.

## 2026-10-19 (ag): Phase 19 model adapter core (T-605 preparation; no real model)

- `investigate/http_adapter.py`: `HTTPProvider` over a pluggable `WireCodec`. It covers:
  - a `SecretStr` key, scrubbed from logs and never in messages;
  - validated configuration (key, model, HTTPS endpoint);
  - bounded retries for 429, 5xx, timeouts and transport errors, within the investigation's time budget;
  - permanent 401/403/4xx, never retried; no redirects followed;
  - a byte cap on the body, and an output-length cap;
  - strict decoding;
  - redacted errors.
- **No OpenAI codec.** The API contract is not in the recorded evidence; the details to record are listed as C-1 to C-9 in `docs/MODEL-ADAPTER.md`. `LLM_PROVIDER=openai` still refuses, saying why.
- `tests/investigate/test_http_adapter.py` (35 adapter **contract** tests with a test-defined wire format) covers:
  - valid text and tool calls;
  - 7 malformed or empty shapes;
  - oversize body and overlong text;
  - auth and other 4xx errors;
  - bounded 5xx retries, rate limits with `retry-after`, timeouts and transport errors;
  - the time budget;
  - 10 configuration refusals;
  - key scrubbing;
  - the real investigator, validator and renderer: valid diagnosis, unsupported claim, provider failure;
  - prompt injection in a repository file and a log, with an obeying model: forbidden tools rejected, no other host contacted, no dangerous fix.
- These are not real-model or accuracy evidence.

## 2026-10-19 (af): Phase 18 runnable web and worker entry points

### Dependency

`uvicorn>=0.30`, installed **offline from the local uv cache** (0.54.0 and click; no network).

### Code

| File | Change |
|---|---|
| `web/asgi.py` | `create_runtime_app` factory. Validates settings (names only in errors; secret ≥16 characters). Uses the system pool. Never migrates. Closes the pool on shutdown. |
| `web/app.py`, `web/health.py` | Lifespan hook. `/readyz` also needs the schema at this build's head (`schema_mismatch` → 503). |
| `worker.py` | `python -m tracewise.worker` (exit codes in OPERATIONS §1a) |
| `db/session.py` | `require_system_plane`, `require_schema_at` |
| `db/migrate.py` | `head_revision` |
| `investigate/providers.py` | Explicit provider selection: `fake` only with `TW_ENV=test`; no fallback |
| `config.py` | `invalid_fields` |
| `logging.py` | `alembic` added to the quiet loggers |

**What the worker refuses (exit 2):**
- a missing setting;
- the same URL for both roles;
- wrong roles (system or owner as tenant; tenant or owner as system);
- a schema not at head;
- an unreadable key;
- the fake provider outside test.

**Signals:** the first SIGTERM or SIGINT is graceful; a second aborts. Startup sweeps stale workspaces.

### Tests

- **`tests/db/test_process_entrypoints.py`** (19, real `uvicorn` and `python -m tracewise.worker` subprocesses):
  - web refuses missing or short secrets;
  - web serves health, readiness, signed and forged pings, and no docs routes;
  - no database writes at startup and no migration;
  - graceful shutdown;
  - an unreachable database gives readiness 503 without crashing or leaking;
  - schema-mismatch readiness;
  - the worker refuses 10 unsafe configurations;
  - an unreachable database gives exit 1 without leaking;
  - idle start, then SIGTERM, then exit 0 with no writes;
  - a permanent failure is recorded once and never re-claimed.
- **`tests/db/test_worker_main.py`** (3, real signals in-process with fake GitHub):
  - SIGTERM mid-job finishes the job, with exactly one write per surface;
  - a second SIGINT aborts, then a restart recovers the job with exactly one write per surface;
  - an unexpected loop error gives exit 1 after a single attempt.

### Not done

Hosting, credentials, schedules (gated). T-1002 is partial.

## 2026-10-19 (ae): Phase 16 offline release-readiness package

- `docs/OPERATIONS.md`: covers
  - install order and the role template;
  - credential separation;
  - App permissions and surfaces, with the G-PLAT-11 risk;
  - webhook verification;
  - worker and recovery operation, with exit codes;
  - retention operation and recovery;
  - observability (provisional threshold);
  - backup, rollback and incidents;
  - privacy and retention (D-12 pending);
  - the release checklist with stop conditions.

  It states that there are **no web or worker process entry points** and **no real model adapter** yet (T-1002, T-605).
- `docs/LIVE-VALIDATION-PLAN.md`: stages S0–S5 for G-PLAT-1 to G-PLAT-12, F-1 to F-3, the bundled token, the PR→commit fallback, the Check Run under a missing permission, suspension, deletion and repository removal mid-publication, redelivery and listing, reinstallation, and duplicate delivery. Each step has expected observations, evidence, cleanup and abort conditions. **Not executed.**
- The documentation index now lists the audit and review documents.

## 2026-10-19 (ad): Phase 15 independent end-to-end verification

The Phase 10 chain test was reviewed. It uses the real app, queue, worker, recovery and purge, but it did not prove four things:
- the tenant role was in use;
- evidence collection happened;
- the PR surfaces were covered;
- tampered signatures were rejected.

**New:** `tests/db/test_full_chain.py`, parametrized for push and pull_request. It:
- rejects a tampered body (nothing recorded);
- retries a transient Check Run failure (2 attempts);
- verifies a stage mark for each step: the log API and its blob redirect requested, an excerpt from the log in the validated diagnosis, provider recorded as `fake`, the code-context location in the published body;
- shows exactly one write per surface, with no commit comment on a matched PR;
- shows **every analysis and publisher transaction ran as `tracewise_app` with tenant 9**, audited per transaction;
- runs recovery through its real paths (already received; sweep duplicate);
- uninstalls and purges, then checks no write after the purge and no token for any other installation.

### Repeat runs

| Run | Result |
|---|---|
| Chain tests ×5 | all passed |
| DB suite ×2 | 236 passed each |
| DB suite in reverse file order | 236 passed |

SIMULATED: GitHub API, model, git host.

## 2026-10-19 (ac): Phase 14 observability and retention verification

### Defects fixed (tests written first)

| ID | Defect | Fix |
|---|---|---|
| SA-8 | Five redaction bypass shapes | New scrubber patterns |
| O-1 | One malformed `stage_ms.total` (non-numeric) crashed `ops.report` | Type-checked extraction; negative or invalid values are ignored |

### Tests

- 12 new tests in `test_logging.py` (bypass shapes; benign text unchanged).
- `test_observability.py`:
  - malformed or incomplete ops records;
  - a failure injected in each of 4 pipeline stages produces `job.retry_scheduled` with the error type only, and the secret-bearing exception text appears in neither logs nor `job.last_error`;
  - the report carries no tenant content.
- `test_retention.py`:
  - 1-second boundaries either side of the 90/14/365-day cut-offs (strict "older than");
  - rows with no expiry timestamp are kept.

### Retention conflict check

Implementation versus documented policy: no conflict found. The open interpretations remain D-12. The 0.2 alert threshold remains provisional.

## 2026-10-19 (ab): Phase 13 recovery and concurrency adversarial tests

### Defects found (regression tests written first) and fixed in `recovery.py`

| ID | Defect | Fix |
|---|---|---|
| R-1 | A 4xx, invalid JSON or malformed page from one repository **raised out of the sweep**. Later repositories were never swept and no summary was emitted. Because the cursor never passed it, the same repository blocked every future pass. A permanent delivery-list error also raised. | Faults are isolated per repository (`failed_repos`; the pass is incomplete) |
| R-2 | 5xx and timeouts were labelled `rate_limited`, and a 5xx on one repository stopped the whole sweep. | Labels: `rate_limited`, `github_unavailable`, `list_failed`. Only a rate limit stops the sweep. |
| R-3 | A redelivery POST interrupted by a 5xx or transport error was not recorded, so its cooldown and cap were bypassed. | Recorded as `uncertain` |

### Tests

`tests/db/test_recovery_faults.py` (10) and `tests/db/test_adversarial.py` (9):

- a worker crash (BaseException) after claim, after evidence, during diagnosis and during publication, followed by a restart (new HTTP client and token cache) and reaping of the expired lease: exactly one commit comment and one Check Run;
- duplicate delivery (same and new GUID) after completion writes nothing;
- retry exhaustion ends dead, with the commit comment never duplicated;
- two workers racing for one job;
- repository removal during publication (**pending D-10**);
- purge alongside jobs in every state.

Repeated 3× with no failure.

## 2026-10-19 (aa): Phase 12 fresh-install and migration lifecycle

- `scripts/db/provision_roles.sql`: a reviewed role template. It has no passwords and creates a non-superuser migration owner. Hardening: no TEMP and no CREATE for PUBLIC.
- `tests/db/test_fresh_install.py` (9) runs on a new cluster bootstrapped only by that template and migrated by the non-superuser owner. It checks:
  - role attributes, with no passwords;
  - the exact table set, RLS on exactly the 10 tenant tables, the policies and the grant matrix;
  - `alembic_version` and audit append-only;
  - the purge function: owned by the non-superuser owner, `pg_temp` last, EXECUTE only for the owner and system;
  - runtime paths: tenant isolation, the purge, and refusal of temp tables and migration-state writes;
  - full downgrade to base and upgrade, with an **identical** catalogue snapshot;
  - roles created after migration get no access (fail closed);
  - the schema guard catches an unprotected tenant table;
  - malformed, unreachable or unknown-role URLs fail without leaking the password.

## 2026-10-19 (z): Phase 11 independent audit of Phases 5–10

### Defects found, regression tests written first, fixed

| ID | Severity | Defect | Fix |
|---|---|---|---|
| SA-5 | Medium | The purge's SECURITY DEFINER `search_path` let caller temp tables redirect it onto an active tenant (demonstrated). | Migration 0009 |
| SA-6 | Low | Nested log fields were not scrubbed. | Recursive filter |
| SA-7 | Medium | The CLIs ran without logging configuration (no secret filter on WARNING+). An unreachable database gave an unhandled traceback. | `configure_cli()`; `DatabaseUnavailable` handled |

### Other changes

- The ops alert rule is validated: threshold in (0, 1], `min_sample` ≥ 1. The output labels the default threshold `provisional`.
- T-706 status corrected to **partial**: no cost figure without T-605 prices, and no alert routing.

### Tests

- `tests/db/test_cli_entrypoints.py` (5)
- 1 new test in `test_retention.py`
- 2 new tests in `test_db_security.py`
- 1 new test in `test_logging.py`

A mutation check confirmed the new tests fail without the fixes.

## 2026-10-19 (y): Final integration and acceptance audit (Phase 10)

- `tests/db/test_cross_phase.py::test_full_chain_webhook_to_retention_purge` covers the full chain. GitHub, the model and the git host are simulated.
- Full suite: 544 passed. That includes 11 slow tests; there are 0 live tests.
- `make check`: 533 passed, 11 slow deselected.
- The slow-inclusive benchmark is identical to Phase 0 (`docs/benchmark-runs/2026-10-19-phase10-final-rerun.md`).
- Secret, quarantine and leftover scans are clean.

## 2026-10-19 (x): Benchmark integrity and review queue (Phase 9)

- Truth lock verified; no case file changed since d4745aa.
- `tests/bench/test_review_items.py` (4) pins today's oracle outcomes for D-5 (B-01), B-04, B-12 and B-02.
- `docs/BENCHMARK-REVIEW-QUEUE.md` lists options and recommendations for D-5, B-04, B-12, A-05, E-01 and B-02, kept separate from the canonical benchmark.

No truth, scorer or policy change.

## 2026-10-19 (w): GitHub integration contract audit (Phase 8)

Record: `docs/GITHUB-CONTRACT-AUDIT.md`. Every gate (G-PLAT-1 to G-PLAT-12) is mapped to its recorded documentation, recorded responses and local tests. All of them remain live gates.

### Tests

`tests/db/test_github_contracts.py` (5):

- **F-1:** a simulated refusal of the bundled publish-token mint blocks all three surfaces (pinned; the fix awaits review);
- a suspension or repository removal mid-job cancels with zero writes;
- **F-2:** a suspension between surfaces does not stop the remaining writes;
- **F-3:** a run cancelled while suspended stays `duplicate_run` after `unsuspend`.

No product behaviour changed.

## 2026-10-19 (v): T-704 retention and tenant purge

**Scope:** FS-SEC-3, FS-INS-3, AT-SEC-12, AT-INS-03 (the "purge" half). Design: ARCHITECTURE §4.9; interpretations D-12 (for review).

### Code

| File | Change |
|---|---|
| `db/migrations/versions/0008_retention_purge.py` | `tracewise_purge(batch_limit)`: a fixed-policy SECURITY DEFINER function, EXECUTE for `tracewise_system` only, no date input, bounded steps, an advisory try-lock. Adds `installation.purged_at`, `analysis.content_purged_at` and age indexes. Reversible. |
| `retention.py` (new) | `python -m tracewise.retention`: a bounded batch loop. Exit codes: 0 done, 3 unfinished, 1 error. Events: `retention.batch`, `retention.finished`, `retention.failed`. |

### Tests

`tests/db/test_retention.py` (14):

- an empty database;
- exact age boundaries for every rule, mixing eligible and ineligible rows; non-terminal jobs are never touched;
- idempotent repeats;
- bounded batches and resume after interruption;
- tenant purge:
  - only the deleted tenant is affected, and the other tenant is byte-for-byte unchanged;
  - audit events are kept, a tombstone remains, and there is no resurrection by late events;
  - the grace period is honoured;
  - the purge waits for in-flight jobs;
  - it is bounded and resumable, and `purged_at` is set only at the end;
- a `deleted` installation without a purge date is reported, not purged;
- run deduplication survives delivery expiry;
- privileges:
  - the tenant role cannot purge;
  - the system role still cannot DELETE content;
  - the function has a fixed `search_path`, no date argument, and a clamped limit;
- a concurrent purge returns `locked`;
- a privilege error and a mid-run outage are reported as failures, with committed batches kept;
- CLI exit codes;
- 0008 down and up;
- **AT-SEC-12:** after 20 real-pipeline analyses, no raw log or source file is stored, excerpts are ≤2 KB, and the retention job deletes by age.

Full suite: 534 passed.

### Not done

- No schedule.
- Never run against real data.

## 2026-10-19 (u): T-706 observability

**Scope:** FS-OPS-1, FS-OPS-2, AT-OPS-01, AT-OPS-02. Design: ARCHITECTURE §4.8.

### Code

| File | Change |
|---|---|
| `observe.py` (new) | `event()`: stable dotted names, never raises. `bind()`: correlation ids. Word-based field deny-list. `Stages` timer. |
| `logging.py` | The formatter includes bound ids. Every URL query string is redacted. `httpx`, `httpcore` and `urllib3` are set to WARNING (SA-4). |
| Instrumentation | Webhook, worker, queue reaper, analyze handler, publisher and recovery now emit events (catalogue in §4.8) |
| `db/migrations/versions/0007_analysis_ops_record.py` | `analysis.stage_ms`, `publish_result`, `finished_at`; an index on `created_at` |
| `repositories.py` | `record_analysis_ops`; `upsert_analysis(cost_usd=…)` |
| `ops.py` (new) | `python -m tracewise.ops report\|alerts`: measured p50/p95 with sample sizes, and the failure-rate rule. On demand only. |
| `config.py`, `.env.example` | Optional `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` |

### Tests

| File | Covers |
|---|---|
| `tests/unit/test_observe.py` (7) | Sanitising, bound ids, thread locality, JSON scrubbing, never-raise, stage timer |
| `tests/unit/test_logging.py` (+1) | Query redaction; quieted loggers |
| `tests/db/test_observability.py` (12) | Event order and ids end to end; the per-analysis record; cost only from configured prices; no token, signed URL, log or source content in any line; retry vs dead vs cancel; stale-lease visibility; an ops-record failure does not republish; an instrumentation fault does not break processing; webhook duplicate vs rejection vs scope; report and alert with hand-calculated percentiles, thresholds and exclusions; CLI exit codes |

Full suite: 520 passed.

### Not done

- No cost figure, because no prices are set (T-605).
- No latency measured on real traffic.
- No scheduling or routing of alerts.

## 2026-10-19 (t): Security audit (Phase 5)

Record: `docs/SECURITY-AUDIT.md`.

### Pre-signed URLs

The S3 pre-signed URLs in the public marketplace snapshot belong to GitHub's screenshot proxy. They expired on 2026-10-17 (five-minute window). They appear in one file and one commit, and there is no secret key or session token.

Not edited. Redacting the query strings before any push is a review item.

### Database fixes

| ID | Change |
|---|---|
| SA-1 | Migration 0006 revokes write access to `alembic_version` from both runtime roles |
| SA-2 | `require_tenant_plane()` fails closed when the analyze handler is given a pool that bypasses RLS |
| SA-3 | A schema guard fails if a table carrying an installation has no RLS policy, or if a new table is not declared |

### Other changes

- Tests: `tests/db/test_db_security.py` (8).
- Docs: fresh database setup order (IMPLEMENTATION-PLAN §4.1), ARCHITECTURE §4.7 guards.
- Full suite: 500 passed.

## 2026-10-18 (s): Cross-phase integration audit (T-701, T-702, T-705)

### Tests

`tests/db/test_cross_phase.py` (2 tests): signed webhooks through the real app, recovery against the fake API, and the real worker on the RLS tenant pool.

- **Uninstall:**
  - queued and retry_wait jobs are cancelled;
  - the orphaned running job (expired lease) is reclaimed by the reaper and cancelled by the handler's scope check;
  - redelivery skips the inactive installation;
  - the sweep skips it;
  - a redelivered webhook is refused;
  - late `created`, `unsuspend`, `new_permissions_accepted` and `added` events do not resurrect it;
  - zero GitHub writes, provider calls, token mints, analyses or publications.
- **Sweep across two installations:**
  - the system plane enqueues both;
  - the tenant plane sees only its own swept rows;
  - suspending one installation cancels its job;
  - the other publishes once under RLS;
  - unsuspend does not revive the cancelled job;
  - a repeated sweep adds nothing.

### Benchmark

The full slow-inclusive rerun is identical to Phase 0 (`docs/benchmark-runs/2026-10-18-phase4-rerun-after-t701-t702-t705.md`). Truth files are unchanged since d4745aa.

## 2026-10-18 (r): T-705 Postgres row-level security and tenant isolation

**Scope:** FS-SEC-6, AT-SEC-03. Two database roles: a tenant plane under RLS and a system plane (D-11, ARCHITECTURE §4.7).

### Code

| File | Change |
|---|---|
| `db/migrations/versions/0005_rls.py` | `tracewise_tenant()`; RLS plus a `tenant_isolation` policy on 10 tables; grants for `tracewise_system` (when the role exists); revokes the recovery tables from `tracewise_app`; reversible |
| `db/session.py` | `transaction(pool, tenant=id)` sets `tracewise.installation_id` transaction-locally; invalid ids are rejected |
| `jobs/handlers/analyze.py`, `github/publish.py` | Every tenant-plane transaction names the job's installation |
| `config.py`, `.env.example`, `recovery.py`, `web/app.py` | `DATABASE_URL_SYSTEM` for the system plane; recovery uses it |
| `tests/pg.py`, `tests/db/conftest.py` | The disposable cluster creates `tracewise_system` (BYPASSRLS). `pool` is the system plane; the new `tenant_pool` is `tracewise_app`, and every end-to-end worker test now runs the analyze handler on it. |

### Tests (all as the actual runtime role `tracewise_app`)

- **`tests/db/test_rls.py`** (10 tests):
  - role attributes (neither runtime role is superuser or owner; only the system role bypasses RLS);
  - own rows readable and writable; other tenant's rows invisible, with UPDATE and DELETE matching nothing;
  - cross-tenant INSERT, UPDATE and publication reservation rejected by WITH CHECK;
  - missing or empty context: nothing visible, inserts fail;
  - malformed context is an error, and an unknown tenant sees nothing;
  - context does not survive COMMIT or ROLLBACK on a reused pooled connection (same backend pid);
  - 20 rounds of overlapping transactions for two tenants;
  - no access to the recovery tables, and neither `row_security = off` nor `ALTER TABLE` gets around RLS;
  - the system plane sees both tenants and `audit_event` stays append-only;
  - 0005 down and up.
- **`test_analyze_worker.py`:** a background job runs as `tracewise_app`; a job naming another installation's repository cannot see it, dies permanently, and mints no token for that installation.
- **Mutation check:** with the tenant argument removed from the handler, the end-to-end tests fail.

### Not done / review

- `tracewise_system` provisioning and credential separation are deployment items (D-11).
- RLS is not a barrier against arbitrary SQL execution as the app role.

## 2026-10-18 (q): T-702 redelivery and failed-run recovery

**Scope** (FS-EVT-5, AT-REL-03):

- (a) Deliveries API redelivery.
- (b) Bounded failed-run sweep.

The other recovery scenarios were mapped to existing mechanisms (ARCHITECTURE §4.6) and not re-implemented.

### Code

| File | Change |
|---|---|
| `db/migrations/versions/0004_recovery.py` | `recovery_checkpoint`, `redelivery_request`; runtime role gets SELECT/INSERT/UPDATE (no DELETE); reversible |
| `github/endpoints.py` | `list_app_hook_deliveries`, `redeliver_app_hook_delivery` (App JWT), `list_workflow_runs` (Actions read, analysis scope) |
| `github/client.py` | `GitHubHTTP.app_paginate`, `app_post` |
| `recovery.py` | `redeliver_failed_deliveries`, `sweep_failed_runs`, `RecoverySummary`, `python -m tracewise.recovery {deliveries,runs,both}` |
| `tests/db/conftest.py` | Recovery tables truncated between tests (state leaked before this fix) |

### Bugs found by the tests and fixed

| Bug | Effect |
|---|---|
| `last_requested_at` written with the DB clock while cooldown compares the injected clock | Two time sources |
| A later stop reason overwrote an earlier one | Page cap reported as request cap |
| **Security-relevant:** a run's `repository` was overwritten before being checked | The foreign-repository guard was vacuous; a listing entry GitHub attributed to another repository would have been enqueued under ours |

### Tests

- **`tests/db/test_recovery.py` (14 tests):**
  - redelivery once per GUID (latest attempt);
  - skips for already received, later success, unhandled event, inactive installation (lifecycle events still redelivered), too old, malformed;
  - cooldown and the 3-attempt cap;
  - rate limits on list and on redeliver, with resume and no repeat;
  - cursor pagination, page cap (no checkpoint advance), request cap;
  - **AT-REL-03(a) end to end**: redelivery → signed webhook replayed twice → one job → real worker → one commit comment + one Check Run → a later pass sees it as received;
  - **AT-REL-03(b) end to end**: an undelivered failed run → sweep → one job → published once; a repeated sweep adds nothing;
  - scope and ownership, including a foreign-repo listing;
  - non-failed and malformed runs;
  - rate-limited sweep resuming at the unfinished repository;
  - a refused token for one installation;
  - an interrupted sweep re-run without duplicates;
  - sweep concurrent with a webhook giving one job;
  - the entry point (refuses without project config; non-zero on an incomplete pass).
- **`test_schema_repositories.py`:** 0004 round trip and grants.

### Verification (actually run)

| Command | Result |
|---|---|
| ruff check / format check | pass (130 files) |
| mypy | no issues in 79 files |
| Full pytest (slow included) | **479 passed** in 176.6 s |
| Recovery, lifecycle, webhook and queue suites, ×3 | 78 passed each time |
| `check_docs.py` | PASS |

### Status

| Item | Status |
|---|---|
| T-702 | done at REPLAY level |
| AT-REL-03 (a), (b) | **REPLAY passed** |
| Live API behaviour | G-PLAT-12 |
| Production schedule | Not configured (by instruction) |

## 2026-10-18 (p): T-701 installation lifecycle

**Phase 0 (`3e2ceed`):** complete slow-inclusive oracle benchmark run (115 required, 111 executed, 4 P2 not applicable, 0 errors). A-05 fails its over-specified truth (decision pending). An unexecuted required run now makes the suite incomplete. Truth and lock unchanged.

**Gaps found before coding:**

- Lifecycle webhooks were recorded but never applied.
- Workflow-run ingestion enqueued jobs for suspended or uninstalled installations and removed repositories.
- The handler checked scope only at job start.

### Code

| File | Change |
|---|---|
| `db/migrations/versions/0003_lifecycle_outcomes.py` | Delivery outcomes `processed`, `repo_not_in_scope`, `repo_disabled`, `installation_inactive`; partial index on pending jobs per installation; reversible |
| `db/repositories.py` | `installation_status`, `set_installation_status` (never resurrects `deleted`), `mark_installation_deleted` (purge +7 days, idempotent), `repository_added`, `repository_removed` (owner-checked), `ingest_scope` |
| `jobs/queue.py` | `cancel_pending(installation_id, repo_id?)`: queued/retry_wait → cancelled, with a reason |
| `web/lifecycle.py` | Validated `installation` and `installation_repositories` processing, in the same transaction as the delivery record; audit events |
| `web/webhooks.py` | Dispatches lifecycle events; invalid payloads → 400 `rejected` |
| `web/ingest.py` | Failure events refused with explicit outcomes (AT-INS-04) |
| `jobs/handlers/analyze.py` | Reasons `cancelled_uninstalled`, `installation_suspended`, `repo_not_in_scope`, `repo_disabled`; scope re-checked before persisting or publishing, including notices |

### Tests

- **`tests/db/test_lifecycle.py` (14 tests):**
  - created (idempotent); suspend/unsuspend (pending jobs cancelled, running left to its lease owner, no resurrection);
  - deleted (purge scheduled, terminal against late `created`/`unsuspend`);
  - AT-INS-04; owner-checked removal; disabled flag preserved;
  - 4 invalid payloads; an unhandled action;
  - a stale queued job; **AT-INS-03 mid-job uninstall through the real worker with zero GitHub writes, no analysis and no publication**;
  - a refused token mint mid-job; deletion racing ingestion (no publication).
- **`test_schema_repositories.py`:** 0003 round trip.
- **`test_webhook.py`:** the "other events" test now uses `check_suite` (`installation` is handled since T-701).

### Verification (actually run)

| Command | Result |
|---|---|
| ruff check / format check | pass (127 files) |
| `uv run mypy` | no issues in 77 files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (slow included) | **464 passed** in 176.6 s |
| Lifecycle, worker, webhook and queue suites, ×3 | 92 passed each time |
| `check_docs.py` | PASS |

### Status

| Item | Status |
|---|---|
| T-701 | done at REPLAY level |
| AT-INS-03, AT-INS-04 | **REPLAY passed** |
| Purge execution | T-704 |
| Live lifecycle behaviour | G-PLAT-6 |

New finding: **G-PLAT-11** (publish-token scope bundling). New decision for review: **D-10** (lifecycle ordering).

## 2026-10-18 (n): synthetic benchmark: harness (T-601), cases and truth (T-602), scorer and report (T-603)

### Inspection

- **State:** clean `main` at `e46f088`; no remote.
- **Canonical scope** (TASKS / BENCHMARK), which is wider than the request:
  - T-602 covers **B-01…B-17 plus A-04…A-06 and E-01…E-06**.
  - BENCHMARK §1: every case runs on **C1 and C2**.
  - BENCHMARK §4: **3 repetitions**, `truth.yaml` hashed and committed **before** the first run, and the exact point table.
  - B-15 and B-16 need P2 features.
- **Tools available offline:** pytest, ruff, mypy, tsc. Not available: jest, vitest, eslint (a network install would be needed).

**Checklist:**

| Requirement | Implementation | Verification |
|---|---|---|
| Per-track report with §4 metrics | `score.py` / `report.py` | `test_score.py` (hand-calculated), sample report |
| Real tool runs and reproducible logs | `generate.py` | `test_logs_regenerate_identically…` (slow) |
| Truth committed and locked before runs | `TRUTH.lock` in d4745aa; the harness refuses on mismatch | `test_truth_lock_detects_changes`, `test_refuses_to_run…` |
| Every case present, valid, evidence resolvable | `integrity.py` | `test_no_integrity_problems`, `test_integrity_catches…` |
| P2 cases explicit | `not_applicable` with reason | `test_p2_cases_are_explicit…` |
| Synthetic kept separate from META | `data_kind` guard in the scorer | `test_serialisation_report_and_separation` |

### Code (`src/tracewise/bench/`)

| File | Content |
|---|---|
| `model.py` | Strict schemas for `case.yaml`, `truth.yaml` (§5 plus the documented §5.1 extensions) and `reference.yaml`; `REQUIRED_CASES` (26) |
| `fixture.py` | Pure-Python commit snapshots, deterministic git builder (fixed identity and dates, so fixed SHAs), compare-API files from the real `git diff` |
| `envelope.py` | GitHub log envelope and jobs-API documents with fixed timestamps |
| `generate.py` | Real local tool runs with path, timing and banner normalisation; `--check` |
| `gitserve.py`, `replay.py` | Local `git http-backend` server (now shared with tests) and an offline GitHub REST replay |
| `harness.py` | Runs the **real** `collect_evidence` → `diagnose` → `render` per case × commit × repetition; Track A uses the real pre-pass. Per-run isolation (errors recorded by type); P2 → `not_applicable`; slow → `not_executed`; planted secrets generated at run time; checks for secrets reaching the provider or output and for symlink content; deterministic run id; truth-lock enforcement. |
| `providers.py` | Scripted providers: `oracle` (from `reference.yaml`), `wrong_cause`, `wrong_location`, `fabricated`, `abstain`, `timeout`, `malformed`, `adversarial`. None reads truth. |
| `integrity.py` | Schema, ids, runs, logs, evidence resolution, location bounds, external-state and lock checks |
| `score.py`, `report.py`, `__main__.py` | §4 scoring (rules in BENCHMARK §4.1), Tracks A/B/C/D/E/R, MVP targets labelled as targets, safety failures, per-case table, limitations; CLI `verify`, `generate`, `run`, `score` |
| `cases/` | 26 cases, logs and `TRUTH.lock` |

### Other changes

- `investigate/provider.py`: `Provider.name` / `model` are read-only properties (type variance). The AT-SEC-10 introspection test still asserts `step` is the only operation.
- `tests/git_server.py` now reuses `bench.gitserve`.
- `pyproject.toml`: the fixtures are excluded from ruff and mypy, so tooling can never rewrite ground-truth data (this had happened once during authoring and was caught by the integrity check). PyYAML added.
- `.gitattributes`: fixture whitespace is preserved verbatim.
- `tests/unit/test_github_client.py`: the AT-SEC-01 source scan exempts exactly `bench/replay.py` and `bench/harness.py`, with a new check that they only build `httpx` clients with an in-process transport.
- `jobs/worker.py`: restored a justification comment that an earlier auto-fix had stripped.

### Tests (37 new; 448 total)

| File | Tests |
|---|---|
| `tests/bench/test_integrity.py` | 6, including the slow regeneration check |
| `tests/bench/test_score.py` | 17, hand-calculated |
| `tests/bench/test_harness.py` | 13, known-behaviour providers |
| `tests/unit/test_github_client.py` | 1 new |

### Benchmark runs (scripted, protocol validation only)

- **Oracle, full suite, 3 repetitions:**
  - 115 required runs: 110 executed, 0 errors, 4 P2 not applicable, 1 slow not executed.
  - Two full runs are identical apart from wall-clock fields.
  - Sample report: `docs/benchmark-runs/2026-10-18-oracle-protocol-validation.md`.
- **A-05** run separately with `--include-slow`: a 200 MB log in about 59 s. It fails its truth (see BENCHMARK §8).
- **Product, truth and reference findings** are listed in BENCHMARK §8, and **none were tuned away**.

### Verification (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 124 files already formatted |
| `uv run mypy` (strict) | no issues in 75 source files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **448 passed** in 172.6 s |
| `uv run pytest tests/bench -m "not slow"`, ×3 | 35 passed each time |
| `python -m tracewise.bench verify` | OK: 26 cases, truth lock matches |
| `python -m tracewise.bench generate --check` (via the slow test) | logs reproduce exactly |
| `python3 -I scripts/check_docs.py` | PASS |

### Status

| Item | Status |
|---|---|
| T-601, T-602, T-603 | done |
| AT-DX-15 | **Not met yet.** It requires the measured OpenAI run (T-605). Scripted results are protocol validation, not accuracy. |

## 2026-10-18 (m): publication (T-502), failure outcomes (T-503) and the wired `analyze` worker

### Inspection

- **State:** clean tree on `main` at `803913d`; one migration (0001); no remote.
- **Gaps found:**
  - No `analyze` handler was registered, so enqueued jobs were never processed.
  - The `publication` table could not represent `unpublished_permission` (FS-PUB-5), which attempt last wrote a surface, or a content digest.
  - **Bug in T-302:** `GitHubHTTP` retried POST inline on transport errors and 5xx, which could duplicate a comment or check run when GitHub had applied the write but the response was lost. POST is no longer retried inline.

**Decision review:**

| Decision | Outcome |
|---|---|
| D-4 | Kept; scope tightened by D-8 (the fallback applies to completed analyses only) |
| D-5, D-6 | Kept (stricter than the spec) |
| D-7 | Kept (provider stays injectable) |
| D-8, D-9 | New (flagged) |

### Acceptance criterion → implementation → test

| AT | Implementation | Test (`tests/db/test_analyze_worker.py` unless noted) |
|---|---|---|
| AT-PUB-01 | Commit comment (write-once) + neutral Check Run | `test_01` |
| AT-PUB-02 | PR comment via API association; no commit comment | `test_02` |
| AT-PUB-03 | `Tracewise`, `neutral`, `external_id=run_id`, report in `output.text`, ≤1 annotation | `test_01`, `assert_neutral` (every test) |
| AT-PUB-04 | Keys per workflow | `test_pub04_…` |
| AT-PUB-05 | Re-runs: PR comment and Check Run updated in place; commit comment unchanged | `test_17_…`, `test_pub05_…` |
| AT-PUB-06 | Fork association + 403 → `unpublished_permission` | `test_pub06_…` ×2 |
| AT-REL-01 | Provider failure: retry ≤2, then could-not-complete (Check Run + PR comment; no commit comment) | `test_11_…` ×2 |
| AT-REL-02 | Rate limit / 5xx: job-level backoff; no duplicate publish | `test_05`, `test_14`, `test_06` |
| AT-REL-05 | No Pull requests write: Check Run published, naming it | `test_10b_…`, `test_pub06_…[False]` |
| FS-LOG-3 / AT-LOG-03 | Logs 410/403: controlled notices, no retry | `test_09`, `test_10`, `test_jobs_api_forbidden_…` |

### Code

| File | Change |
|---|---|
| `db/migrations/versions/0002_publication_state.py` | `source_run_id`, `source_attempt`, `content_digest` (64-hex CHECK), `missing_permission`; adds the `unpublished_permission` state; reversible |
| `db/repositories.py` | `mark_published(…, source_run_id, source_attempt, content_digest)`; `mark_unpublished_permission` (never overwrites `published`); `find_workflow_run`; `repository_scope` |
| `github/endpoints.py` | `list_commit_comments` (GET, Contents read, already inside the publish scope); no new permission |
| `github/client.py` | POST never retried inline |
| `github/publish.py` | `Publisher.commit_comment / pr_comment / check_run`, `PublishTarget.check()` (installation, repository, SHA, IDs, publish scope); row lock, stale guard, unchanged skip, lease check before each write, reconcile before create, `unpublished_permission` |
| `report/render.py` | `check_output()`, `render_could_not_complete()` (no exception text), `publication_notes()` |
| `jobs/queue.py`, `jobs/worker.py` | `JobCancelled` → `cancel_running` (owner only) |
| `jobs/handlers/analyze.py` | `AnalyzeDeps`, `make_analyze_handler()`: the connected flow and the outcome → job-state mapping |
| `tests/github_state.py` | Stateful fake publication API with write counting and fault injection |

### Tests (32 new; 411 total)

- `tests/db/test_analyze_worker.py`: 28 tests through the **real `Worker` and the registered handler**, against a disposable Postgres, the local git http-backend, the stateful fake API and the scripted provider. They cover all 18 requested scenarios, plus AT-PUB-04/05/06, a spoofed marker comment, an unexpected bug (never success; notice on the last attempt), the jobs-API 403 notice, and no personal token in requests.
- **Guards:** only loopback connections are allowed; `GITHUB_TOKEN` and `GH_TOKEN` are set to sentinels and asserted absent from every request.
- **Assertions:** fake GitHub objects, POST and PATCH counts, publication rows and states, `analysis.status`, and job status, attempts and result.
- `tests/unit/test_github_client.py`: POST timeout or 502 → exactly one request; PATCH still retried.
- `tests/db/test_schema_repositories.py`: 0002 down/up; `unpublished_permission` never overwrites `published`; digest CHECK.

### Verification (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 108 files already formatted |
| `uv run mypy` (strict) | no issues in 63 source files |
| Targeted: `pytest tests/db/test_analyze_worker.py tests/db/test_schema_repositories.py tests/unit/test_github_client.py tests/db/test_queue.py tests/db/test_worker.py` | 95 passed (before the last 2 tests were added) |
| Concurrency, retry, idempotency and crash subset (12 tests), ×5 | 12/12 each time |
| Full suite `uv run pytest -o addopts="--strict-markers" -p no:warnings` (slow included) | **411 passed** in 121.4 s on the final tree |
| `python3 -I scripts/check_docs.py` | PASS |

### Status

- T-502 and T-503: **done at REPLAY level**.
- **LIVE halves stay open** as gates: AT-PUB-01 (G-PLAT-5: commit comment with Contents read), AT-PUB-02/03/05 (LIVE), AT-PUB-06 (G-PLAT-4), AT-PUB-08 (G-PLAT-3: size limits), G-PLAT-10 (attribution fields and list consistency used by reconciliation).

### Not done / honest limits

- **Not exactly-once:** see ARCHITECTURE §4.4 for the remaining window.
- **Not yet implemented:** the installation lifecycle (T-701), deliveries redelivery and the failed-run sweep (T-702), quotas (T-703), RLS (T-705).
- **No production entry point:** the worker process that builds `AnalyzeDeps` from settings and an App key does not exist yet, because building it needs real App credentials.

## 2026-10-18 (l): diagnosis engine and report (T-401…T-404, T-501) as a connected offline slice

### Inspection findings (before coding)

- **Task graph:** matches the request. T-401←T-103; T-402←T-401, T-305; T-403←T-402; T-404←T-403; T-501←T-403.
- **Boundary:** `collect_evidence()` yields `Evidence`, which carries the pre-pass, retained logs, trigger diff, `CodeSource` and `ToolBox`. The source is valid only inside that block.
- **Gaps found:** `investigate/` and `report/` were empty, and the worker's `analyze` handler is not wired. Wiring it needs publishing (T-502/T-503), which is out of scope.
- **Contract gap:** FS-DX-4 requires a system-copied snippet and FS-RPT-4 a ≤15-line snippet, but Diagnosis v2 had no field. Added `problem_snippet`, `inconclusive_reason` (fixed code) and `validation_flags` (codes). All three are filled by code only; SPEC §3.1 is updated.
- **Ambiguity:** FS-DX-7's high-confidence wording, resolved as **D-5** (stricter reading; flagged for review).

### Checklist (acceptance criterion → implementation → test)

| AT / FS | Implementation | Test |
|---|---|---|
| AT-SEC-10 | Fixed 4-tool `TOOL_SPECS`; `Provider` exposes only `step` | `test_loop::test_sec10_…` |
| FS-DX-3 budgets, 1 repair | `investigate/loop.py` | `test_loop` (13 tests on budgets, repair, provider failures) |
| AT-DX-14 | Rule 2 → 6 in `validate.py` | `test_validate::test_dx14_…` (6 cases) |
| AT-DX-05 | Snippet copied from the source at `head_sha` | `test_validate::test_b02_…` |
| AT-DX-12 | `confidence.assess` (D-5) | `test_validate` (high, medium, low, conflict, truncation, every result) |
| AT-DX-13 | No real error line → inconclusive, provider never called | `test_loop::test_no_error_line_…`; `test_validate::test_statuses_…` |
| FS-ATR-1 / T-306 rule | Attribution from pre-pass ∪ validated location; unknown when not diagnosed | `test_validate::test_t306_…`, `test_inconclusive_never_clears_the_push` |
| AT-SEC-07 | `report/render.py` escaping and code spans | `test_render::test_sec07_…`, `test_code_spans_…` |
| AT-SEC-08 | Delimiting; D-6 H-2 | `test_loop::test_untrusted_…`, `test_validate::test_sec08_…`, e2e injection |
| AT-RPT-01…09, 11 | Renderer sections and links | `test_render` (16 tests) |

### Code

| File | Interface |
|---|---|
| `investigate/provider.py` | `Provider` protocol (`step(StepRequest) -> StepResponse`), message, tool-call, spec and usage types, `ProviderError` / `ProviderTimeout`. No SDK or network. |
| `investigate/fake.py` | `ScriptedProvider`: deterministic; records requests |
| `investigate/prompt.py` | Fixed system policy, `TOOL_SPECS`, nonce `Delimiter`, bounded `render_bundle(ev)` (≤24k chars) |
| `investigate/schema.py` | `ModelDraft` (strict), `parse_draft()`; forbidden fields dropped and reported |
| `investigate/loop.py` | `investigate(ev, provider, InvestigationLimits)` → `InvestigationResult(outcome, draft, …)`. Outcomes: `answered`, `no_error_line`, `provider_failed`, `provider_timeout`, `budget_exhausted`, `invalid_output`, `unproductive`. `validate_call()`; `InvestigationLimits.from_settings()`. |
| `investigate/validate.py` | `finalize(ev, inv) -> ValidatedDiagnosis` (rules 1–8, D-6); `ValidatedDiagnosis.verify()` (SHA-256) |
| `investigate/confidence.py` | `assess()`, `changed_lines()`, `error_evidence()`, `conflicts()` (D-5) |
| `analysis/diagnose.py` | `diagnose(ev, provider) -> ValidatedDiagnosis` |
| `report/render.py` | `render(vd, max_chars=60000, marker=None) -> str`; `esc()`, `code()`, `fence()`, `build_links()` |
| `contracts.py` | Three system-filled Diagnosis fields (above) |

### Bugs found by the tests and fixed

- The causal-claim filter (H-1) missed "the README change in this push caused …", where the noun came before the verb. It now works per sentence.
- The renderer backslash-escaped text inside inline code spans, which GitHub would display literally. A literal `code()` helper was added.

### Tests added (83)

| File | Tests |
|---|---|
| `tests/investigate/test_loop.py` | 29 |
| `tests/investigate/test_validate.py` | 30 |
| `tests/report/test_render.py` | 16 |
| `tests/context/test_diagnose_e2e.py` | 8 |
| `tests/investigate/factory.py` | Offline evidence from real pytest/ruff output |

**Connected e2e path** (fake GitHub API + local git http-backend + scripted provider): `collect_evidence` → `diagnose` → `render`.

- **Scenarios:** known cause (B-02); determinism over 3 full fresh runs; ambiguous (model abstains); injected log text (unread location rejected; read README plus a `curl | sh` fix → fix dropped, not high, no `curl` or URL in the report); missing code context (git and the API both fail); invalid output twice; provider timeout; budget exhaustion.
- **Guard during reasoning and rendering:** `socket.connect` raises; every subprocess is either the isolated grep worker or a local `git cat-file`/`ls-tree` with no `fetch`.

### Verification (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 102 files already formatted |
| `uv run mypy` (strict) | no issues in 59 source files |
| `uv run pytest … tests/investigate tests/report tests/context/test_diagnose_e2e.py` | 82 passed (then 83 with the settings test), ×5 runs |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **379 passed** in 97.8 s on the final tree (378 before the settings seam was added) |
| Timing and concurrency subset (git, grep, DB, worker) | 10/10, ×3 runs |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance-test status (honest)

| Test | Status |
|---|---|
| AT-SEC-10, AT-DX-05, AT-DX-12, AT-DX-14 | **Passed** (unit/offline) |
| AT-RPT-01, AT-RPT-02, AT-RPT-04…09, AT-RPT-11, AT-SEC-07 | **Passed** (unit/offline, B-02 replica) |
| AT-DX-13 | **Partial:** passed on hand-written B-13/B-14-shaped logs (timeout line; `Killed` plus exit 137); rerun on T-602 fixtures |
| AT-RPT-03 | **Partial:** the ≤800-character limit holds; "2 blind graders" is a human check, not done |
| AT-SEC-08 | **Partial:** code guarantees hold (delimiting, no unread location, no unsafe command in a fix); "the model does not adopt it" needs a real model (T-605) |
| AT-DX-01, AT-DX-04, AT-DX-08, AT-DX-09, AT-DX-10, AT-DX-11, AT-DX-06 | **Not met:** model accuracy on BENCH cases. A scripted fake proves the protocol only. Needs T-601…T-605. |

### Task status

- T-401: **in-progress** (OpenAI adapter deferred, D-7).
- T-402: **in-progress** (implementation complete; its acceptance tests are BENCH/model-accuracy).
- T-403, T-404, T-501: **done**, with the partial tests above recorded.

### Decisions for review

**D-5** (confidence reading), **D-6** (validator hardening H-1, H-2, H-3), **D-7** (adapter deferral).

### Not done / gaps

- The worker's `analyze` handler is not wired (it needs T-502/T-503 publishing).
- The grep worker is not OS-sandboxed (unchanged).
- The 60k report cap is provisional (G-PLAT-3).

## 2026-10-18 (k): T-307 evidence collection (new task), batch verification

**Why a new task:** the analysis flow's retrieval steps 2–6 were not owned by any task. T-402, the only task depending on T-305, is reasoning and also needs T-401. T-307 was added (0.75 dd); the offline core is now 30.75 dd and the pilot total ≈44.5 dd.

| File | Content |
|---|---|
| `analysis/collect.py` | `collect_evidence(job, rc, fetcher=…)` (context manager). Lists failed jobs through the jobs API (≤5 downloaded; the rest listed), streams **only those** jobs' logs into the pre-pass, computes the trigger diff, opens the code context and builds the `ToolBox` with `get_diff`. Statuses: `ok`, `logs_unavailable` (all logs 404/410 or vanished, no pre-pass result kept), `permission_denied` (permission recorded), `no_failed_jobs`. Accepts only the analysis-scope client of the run's repository. `implicated_paths` holds pre-pass locations only; T-403 must add the diagnosis location before `relevance()`. No model calls. |
| `tests/context/test_collect.py` (7 tests) | **Offline end to end** (fake API plus local git server; the token is minted in-test and accepted by the git server). B-02 replica: 3 siblings, step and command from the jobs API, trigger diff, git source at the exact SHA, `read_file` at `pricing.py:41`, `files_examined`; only the failed job's log was requested; no token reached the blob host; workspace removed; token not logged. Log 410, 404, blob 404 and 403 statuses; partial logs; job cap; no failed jobs; scope and repository guards. |
| `tests/github_fake.py` | `next_tokens` hook |
| Docs | TASKS (T-307, totals, critical path), IMPLEMENTATION-PLAN layout |

### Batch verification (actually run, `~/tracewise`)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 86 files already formatted |
| `uv run mypy` (strict) | no issues in 50 source files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **296 passed** in 89.9 s |
| `python3 -I scripts/check_docs.py` | PASS |
| Timing- and concurrency-sensitive subset (git timeout, transfer, cleanup, SIGKILL sweep, grep ReDoS, queue concurrency, worker heartbeat, lost lease, DB down, end-to-end concurrency), 5 repetitions | 10/10 each time |

### Acceptance-test status after this batch

| Test | Status |
|---|---|
| AT-CTX-01, AT-CTX-03, AT-CTX-04, AT-SEC-06 | Passed (UNIT/offline; the AT-CTX-01 LIVE half is gated) |
| AT-LOG-01 | **Passed at REPLAY level** (offline fake API) |
| AT-CTX-02 | Partial: needs the full pipeline |
| AT-LOG-03 | Partial: statuses are produced; "publish OK" needs T-502/T-503 |
| AT-SEC-09 | Partial: needs T-402/T-403 |
| AT-ATR-01, AT-ATR-02, AT-ATR-03, AT-ATR-09 | Partial: unit level |
| AT-PUB-09, AT-PUB-10 | Partial: association only |

## 2026-10-18 (j): T-303 review, ambiguous PR association

**Reasoning:** FS-PUB-7, AT-PUB-09 and AT-PUB-10 define only "match → PR comment" and "no match → commit comment". The "lowest PR number" tie-break added in (f) had no basis in the requirements, so it was removed.

| Area | Change |
|---|---|
| `github/pulls.py` | Outcomes: `matched`, `none`, `ambiguous` (all candidates listed, none chosen), `error` (malformed response). Malformed items are skipped individually; duplicate entries count once; 403 and installation errors propagate to the permission paths. |
| `tests/unit/test_github_pulls.py` (18 tests, replacing 10) | Single match; fork `head=` fallback; no match; 2 and 3 matches are ambiguous; fork-filter ambiguity; duplicates; recorded closed/merged PR (and the same data opened); mismatched head SHA; closed; other base repo; 9 malformed item shapes; 3 malformed response shapes; 403 propagates; no `head=` lookup for same-repo runs; analysis scope refused; the webhook `pull_requests` field is never used (signature, model and job payload). |
| Docs | DECISIONS **D-4** (flagged default: ambiguous or error means no PR comment; commit comment plus Check Run instead); ADR-15; FS-PUB-7 |

**Validation:** targeted `pytest tests/unit/test_github_pulls.py`: 18 passed. ruff and mypy clean. The full suite runs at the end of this batch.

## 2026-10-18 (i): T-306 trigger diff and `touches_implicated`

### Code

| File | Content |
|---|---|
| `context/trigger.py` | `compute_trigger_diff`: parent lookup for a push, or a supplied base for a PR; the compare API with validated SHAs; file names validated; renames counted; truncation flagged; failures become an explicit unknown. `relevance` is three-valued and code-only; unknown, truncated-without-overlap and empty-implicated cases give `None`. Wording follows FS-ATR-1 and never uses causal language. `to_attribution`. `TriggerDiff.render` feeds the `get_diff` tool. |
| `contracts.py` | `Attribution.touches_implicated` is now `bool \| None` (FS-ATR-1 says true/false/unknown); the SPEC JSON was updated to match |

### Tests

`tests/context/test_trigger.py` (13 tests):

- **AT-ATR-01:** README-only push.
- **AT-ATR-02:** the implicated file was changed.
- **AT-ATR-03:** fork PR given a base SHA.
- **AT-ATR-09:** B-17 touch reported as evidence only; META P-03 using the **real recorded** pallets/flask commit with no implicated paths gives unknown.
- **Unknown cases:** root commit, compare 404, invalid parent, malformed response.
- **Truncation:** at 300 files and at 251 commits.
- **Inputs:** renames and unsafe names.
- **Output:** statement length; `render` and `get_diff`.

The fixture `recorded/flask-commit-d73fa1cdcb.json` was copied unchanged from the public evidence folder.

### Validation (actually run)

| Command | Result |
|---|---|
| ruff check and format check | pass (83 files) |
| mypy | no issues (48 files) |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **281 passed** in 97.2 s |
| `check_docs.py` | PASS |

### Acceptance tests

| Test | Status |
|---|---|
| AT-ATR-01, AT-ATR-02, AT-ATR-03, AT-ATR-09 | **Partial: unit level only.** Their environments are B-02/B-17 benchmark runs (T-601+), and AT-ATR-02 needs the diagnosis location from T-403. |

## 2026-10-18 (h): T-305 read-only investigation tools

### Code

| File | Content |
|---|---|
| `context/tools.py` | `ToolBox` over one `CodeSource`. Tools: `read_file(path, start, end)` with numbered lines, ≤250 lines, clipped to EOF, the resolved symlink path logged; `list_dir(path)` showing files, dirs, symlinks and submodules ("not inspected"); `grep(pattern, glob, ignore_case)`; `get_diff()`. ≤12 calls, output cap, a call log, and `files_examined()` derived from successful reads only. Unknown tools and bad arguments are returned as errors. |
| `context/grep_worker.py` | Isolated matcher process (`-I`, empty env, `cwd=/`, CPU and memory rlimits) with a parent timeout. Contains ReDoS from model-supplied patterns. |
| `context/paths.py` | `"/"` is no longer accepted as the repository root (only `""` and `"."`) |

### Tests

| File | Coverage |
|---|---|
| `tests/context/test_tools.py` (23 tests) | **AT-CTX-03:** read and list refuse 7 and 6 escape forms; grep never reads outside the tree and skips symlinks. **AT-CTX-04:** `files_examined` equals the log, including EOF clipping, symlink resolution, and excluding beyond-EOF reads, failed reads and grep. **AT-SEC-09 (tool half).** ReDoS `(a+)+$` contained. Budget, output cap, statuses, `list_dir` and `get_diff`. A run over real Git objects from the local server. |
| `tests/context/test_paths.py` (35 tests) | Path, link, repo and SHA rules |

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check …`, `ruff format --check …` | pass (81 files) |
| `uv run mypy` | no issues (47 files) |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **268 passed** in 103.1 s |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance tests

| Test | Status |
|---|---|
| AT-CTX-03, AT-CTX-04 | **Passed** (UNIT) |
| AT-SEC-09 | Still **partial**: the symlink is refused and injected text is returned as inert data, but "instructions ignored" by the model needs T-402/T-403 |

### Open risk

The grep worker is isolated by process, rlimits and timeout, not by an OS sandbox (seccomp or namespaces). It only ever receives text, and the code performs no I/O beyond stdin/stdout.

## 2026-10-18 (g): T-304 secure code context (no checkout)

### Code

| File | Content |
|---|---|
| `context/paths.py` | Validation of owner/repo, 40-hex SHAs and repo-relative paths (NFC, no control or format characters, no `..`, `.`, empty or `.git` segments, no backslashes, length cap). Lexical in-tree symlink resolution. |
| `context/source.py` | `CodeSource` model: tree entries (file/symlink/submodule), `read()` with statuses (`ok`, `not_found`, `too_large`, `binary`, `symlink_escapes`, `symlink_loop`, `submodule`, `is_directory`, `invalid_path`, `budget_exhausted`, `unavailable`). Symlinks ≤5 hops, inside the tree only. Per-file 1 MB cap; aggregate read budget; `skipped` map (`files_skipped`). `UnavailableSource`. |
| `context/gitfetch.py` | `GitFetcher` with a private bare repo and **no checkout**; fetch by SHA with `--depth=1` and a blob filter; token as a Basic header via `GIT_CONFIG_*` env; from-scratch env; protocol and redirect lock-down; timeout, transfer cap (polled, plus a final check) and output caps, with a process-group SIGKILL on breach or cancellation; reads under `GIT_NO_LAZY_FETCH=1` without credentials; cleanup in `finally`; `sweep_workspaces()`. `GitObjectSource`. |
| `context/contents_api.py` | `ContentsApiSource`: Trees API listing (truncation flagged), Contents API at `ref=<sha>` with blob-SHA and size checks, `git/blobs` for symlink targets; oversized files never requested |
| `context/provider.py` | `open_code_context()`: Git first, then the Contents API, then `UnavailableSource`. Caller exceptions propagate and the workspace is always removed. |
| `github/endpoints.py` | `get_tree` and `get_blob` added (GET, Contents read) |
| `github/client.py` | `RepoClient.full_name`, `git_fetch_token()` (analysis scope only), `invalidate_token()` |

### Tests (offline)

- **`tests/git_server.py`:** `git http-backend` behind a WSGI shim on 127.0.0.1, with a per-run token. It records the auth headers it receives and can inject faults (status, delay).
- **`tests/context/test_gitfetch.py` (21 tests):** exact commit; LFS pointer not smudged; submodule reported; no hooks dir and no checkout; planted hooks never run; large blob skipped **with no lazy network fetch**; binary skipped; symlink escape, loop and chain; 9 unsafe-path forms; token never in argv, on disk or in logs, and the header received on every pack request; wrong token; missing commit; missing repo; HTTP 500; timeout with no leftover process; transfer cap; cleanup on exception and on KeyboardInterrupt; input validation and fixed host; read budget; sweep; **AT-SEC-06** with a SIGKILLed child process.
- **`tests/context/test_contents_api.py` (8 tests):** exact-SHA reads; size cap without a request; symlinks; submodules; unsafe names; blob-SHA mismatch rejected; truncated tree; failover git → API; both failing → unavailable; git preferred with no API calls; caller errors propagate with cleanup; publish scope cannot fetch code; budget.
- **`tests/unit/test_github_client.py`:** a named regression test for the log-cap bug (the cap crossed inside a later chunk).

### Bug found and fixed

The transfer cap was checked only while git was running. A fast transfer finishing between two polls escaped it. A final check now runs after the process exits.

### Docs

- **ARCHITECTURE:** ADR-14 revised (no checkout); new §4.2; G-PLAT-9.
- **SPEC:** FS-CTX-1 and FS-CTX-5 wording (objects and tree-path confinement).
- **IMPLEMENTATION-PLAN:** layout and step 6.
- **TASKS:** T-304 marked done.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `uv run ruff format --check src tests scripts` | pass (76 files) |
| `uv run mypy` | no issues (45 files) |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **210 passed** in 96.9 s |
| `python3 -I scripts/check_docs.py` | PASS |
| Leftover temp repos, clusters, servers or processes | none |

### Acceptance tests

| Test | Status |
|---|---|
| AT-CTX-01 | **Passed** (UNIT, local fixture repo). The LIVE half is gated (G-PLAT-9). |
| AT-CTX-02 | **Partial:** skipping and listing pass. "The analysis still completes" needs the pipeline (T-402+). |
| AT-SEC-06 | **Passed** (SIGKILLed process, then the sweep) |
| AT-SEC-09 | **Partial:** symlink refusal passes. "Instructions ignored" needs the investigator (T-402/T-403). |

### Open risk

The token is readable by the same OS user through `/proc/<pid>/environ` while a fetch runs (ARCHITECTURE §4.2).

## 2026-10-18 (f): T-303 PR association

### Code

| File | Content |
|---|---|
| `src/tracewise/github/pulls.py` | `associate_pr`. Calls `/commits/{sha}/pulls` first, then, for forks only, `/pulls?state=open&head=owner:branch`. Keeps open PRs into this repository whose `head.sha` equals the run's SHA; with several matches, the lowest PR number. No match means a push (commit comment). Never reads `workflow_run.pull_requests`. |
| `src/tracewise/github/client.py`, `endpoints.py`, `auth.py` | `SCOPES` moved to `endpoints.py`. `RepoClient` now refuses endpoints outside its token scope **before** minting or sending anything. |

### Tests

`tests/unit/test_github_pulls.py` (10 tests):

- same-repo PR;
- fork PR via the `head=` filter;
- fork with no match is treated as a push;
- the **real recorded** pallets/flask response (closed, merged PR) is not associated; the same data marked open is;
- stale head, closed and other-base PRs are ignored;
- lowest number wins;
- no `head=` lookup for same-repo runs;
- the analysis scope cannot list pulls.

A further test in `test_github_client.py` covers scope enforcement in both directions, with no requests made.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `ruff format --check` | pass (66 files) |
| `uv run mypy` | no issues in 40 files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **180 passed** in 81.2 s |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance-test status

| Test | Status |
|---|---|
| AT-PUB-09 | REPLAY **association half passed**. "→ PR comment on #n" needs the publisher (T-502). |
| AT-PUB-10 | REPLAY **association half passed**. The LIVE half (G-PLAT-4, real fork behaviour) is gated. |

## 2026-10-18 (e): T-301 GitHub App auth, T-302 REST client

### Code

| File | Content |
|---|---|
| `src/tracewise/github/endpoints.py` | Registry of the 16 callable endpoints, each with its authorising permission. `APP_PERMISSIONS` lists the five in FS-INS-2. Per-purpose scopes: `ANALYSIS_SCOPE` (read only) and `PUBLISH_SCOPE`. |
| `src/tracewise/github/auth.py` | `AppCredentials` (RS256 App JWT, 9 min; key hidden). `TokenProvider` mints repository-scoped, purpose-scoped installation tokens; checks the grant and fails closed on over-broad grants; keeps them in memory per (installation, repo, scope); refreshes 5 min before expiry; supports invalidate and drop-installation; registers tokens with the log scrubber. |
| `src/tracewise/github/client.py` | `GitHubHTTP`: registry-only calls; rate-limit handling (`retry-after`, `x-ratelimit-reset`, ≥60 s secondary; inline ≤10 s, otherwise deferred to the queue); 5xx and transport retries; error taxonomy; JSON cap; API-host-only pagination with a page cap; safe log redirect (https, allowlisted host, no credentials, **no Authorization header**, streamed, 512 MB cap). `RepoClient`: bound to one repository, re-mints once on 401, encoded path parameters, contents-path guard, `list_jobs`, `failed_jobs`, `job_log_lines`. |
| `src/tracewise/github/errors.py` | Errors mapped onto queue semantics: `GitHubRetryable`, `PermissionDenied`, `NotFound`, `Gone`, `InstallationUnavailable`, `TokenScopeError`, `UnsafeRedirect`, `ResponseTooLarge` |
| `pyproject.toml`, `uv.lock` | `httpx` moved to runtime; `pyjwt[crypto]` added |

### Tests and fixtures

| File | Content |
|---|---|
| `tests/github_fake.py` | In-process fake GitHub on `httpx.MockTransport`. The RSA key is generated in memory per session; no key file exists. |
| `tests/fixtures/github/recorded/` | Two **real anonymous** responses copied unchanged from the public evidence folder (provenance in `tests/fixtures/github/README.md`). All other responses are **synthetic**, shaped after the GitHub docs. |
| `tests/unit/test_github_auth.py` | 16 tests |
| `tests/unit/test_github_client.py` | 25 tests |
| `tests/db/test_github_worker.py` | 1 test |

### Bug found by the tests and fixed

A log chunk crossing the download cap was discarded whole, losing complete lines that fit. The client now keeps everything up to the cap.

### Docs

- **ARCHITECTURE:** §4.1 (GitHub credentials and calls); G-PLAT-8 (the log-redirect host allowlist is an unverified assumption).
- **IMPLEMENTATION-PLAN:** package layout.
- **TASKS:** T-301 and T-302 marked done.

### Validation (actually run, in `~/tracewise`)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 64 files already formatted |
| `uv run mypy` (strict) | no issues in 39 source files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **169 passed** in 80.9 s |
| `python3 -I scripts/check_docs.py` | PASS |
| Secret scan of the staged diff | No private keys, PATs or API keys outside the redaction code and tests |

### Acceptance-test status (honest scope)

| Test | Status |
|---|---|
| AT-SEC-01 | **Passed (static):** every registered endpoint is covered by the five permissions; no contents, workflow or issues writes; no HTTP import or API host outside the client. Whether GitHub's real permission checks agree (e.g. a commit comment with Contents read) is **G-PLAT, LIVE**. |
| AT-SEC-05 | **Passed (fixture level):** tokens are never logged (not emitted, and scrubbed if they were) and never reused across installations, repos or scopes |
| AT-LOG-01 | **Partial:** the token request is scoped, only failed jobs are selected, and the redirect is followed within one call (fake transport). The pipeline wiring that downloads only failed jobs' logs is T-701-era handler work. |
| AT-LOG-03 | **Partial:** the client raises `NotFound`, `Gone` or `PermissionDenied`. The `logs_unavailable` / `permission_denied` report is T-503. |
| AT-REL-02 | **Partial:** the rate limit reschedules ≥60 s through the real queue, and the next attempt survives a 502. "No duplicate publish" needs T-502. |
| AT-SEC-03 | Not claimed. The client binding prevents cross-repo paths, but the RLS half is T-705. |

**Not tested anywhere:** real GitHub behaviour. No network calls were made.

## 2026-10-18 (d): T-106 webhook endpoint

### Code

| File | Content |
|---|---|
| `web/webhooks.py` | `POST /webhooks/github`. Checks run in this order, and nothing is parsed before the signature passes: declared length >25 MB → 413 without reading; streamed body capped at 25 MB → 413; no secret configured → 503 (fail closed); HMAC-SHA256 constant-time → 401; delivery and event headers validated → 400; JSON and schema → 400, recorded as `rejected`; DB unavailable → 503 with nothing persisted. Responses: 202 `enqueued`, 200 for duplicates and ignored deliveries, 200 `pong`. Blocking DB work runs in the threadpool. |
| `web/ingest.py` | One transaction holds the delivery row (deduped on `X-GitHub-Delivery`), the installation and repository upserts, the run row and the job (deduped on `(repo, run, attempt)`). Non-analysed conclusions and actions are recorded as `ignored`. |
| `web/health.py`, `web/app.py` | `/healthz`, `/readyz` (DB ping, returns 503 when the DB is down). App factory with no docs or OpenAPI endpoints. |

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check`, `ruff format --check`, `uv run mypy` (strict, 35 files) | pass |
| `uv run pytest` (all, slow included) | **127 passed** in 79 s |
| End-to-end concurrency test | 5 consecutive runs, all passed |
| Disposable clusters | No leftover clusters or processes after the run |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance-test status after T-106

| Test | Status |
|---|---|
| AT-EVT-01, AT-EVT-02 | **Passed** (REPLAY, synthetic payloads) |
| AT-EVT-05 | **Passed**: 100 deliveries with the worker stopped, each <1 s; delivery and job joined 1:1; a mid-transaction DB failure rolls everything back, and the redelivery succeeds |
| AT-EVT-06 | **Passed**: same delivery ×3 (sequential and 24 concurrent requests); a new delivery for the same run; `in_progress` after `completed`; a re-run attempt enqueues a new job |
| AT-SEC-02 | **Passed**: missing, invalid, wrong-algorithm, wrong-secret and tampered signatures → 401 with no rows; >25 MB → 413 (declared and streamed) |
| AT-EVT-03 | **Partial**: `timed_out` enqueues a job. "The report mentions the timeout" needs T-501. |
| AT-REL-04 | **Partial**: 50 deliveries from one installation through the webhook and 6 real workers peaked at ≤2 concurrent, and the other installation finished in less than half the backlog time. The handler is a stub until the analysis pipeline exists. |
| AT-EVT-04 | LIVE (G-PLAT-1); gated |

**Note:** Starlette warns that its test client should move from `httpx` to `httpx2`. This is a test-only dependency; it will be revisited when the dependency is bumped.

## 2026-10-18 (c): T-104 schema and repositories, T-105 job queue and worker

### Code

| File | Content |
|---|---|
| `db/migrations/versions/0001_initial.py` | The 10 tables from ARCHITECTURE §3, CHECK constraints for every state column, a write-once trigger for published commit comments, runtime-role grants (DML only; `audit_event` append-only) |
| `db/migrate.py`, `db/migrations/env.py`, `db/urls.py` | Programmatic Alembic upgrade and downgrade, run with the owner role |
| `db/session.py` | Pool for the runtime role. `transaction()` maps pool timeouts and connection failures to `DatabaseUnavailable`, with no URL in the message. |
| `db/repositories.py` | Deliveries, installations and repos, runs, analyses, publications (reserve/lock, write-once, upsert), signatures (counted once per run, redacted), usage, audit. Errors are stored redacted and capped at 500 chars. |
| `jobs/queue.py` | Explicit state machine. Enqueue deduped on `dedupe_key`. Serialised claims with `SKIP LOCKED`, ≤2 running per installation, one running job per run. Lease, heartbeat and reaping. Backoff of 30 s and 120 s (±20%, ≥ `retry-after`). `RetryableError` vs `PermanentError`. 10-minute deadline from the first claim. Every transition out of `running` is fenced on `locked_by`. |
| `jobs/worker.py` | Claim, handle, then complete or fail. A heartbeat thread runs alongside; a lost lease raises before side effects. When the DB fails while recording an outcome, the job is retried after lease expiry (handlers must be idempotent). `run_forever` backs off exponentially while the DB is down. |
| `contracts.py` | `workflow_id` and `head_repo_id` added to the job payload; `WorkflowRunEvent.dedupe_key` |
| `tests/pg.py`, `tests/db/` | **Disposable Postgres:** `initdb` into a private 0700 temp dir, Unix socket only, removed after the session. System Postgres, its configuration and user data are not touched. |

### Docs

- **D-1, D-2, D-3** clarified as requested ([DECISIONS.md](DECISIONS.md)). D-1 is now a provisional hypothesis, with its denominator and method in [VALIDATION-PLAN.md](VALIDATION-PLAN.md) §3.
- **ARCHITECTURE §3:** the job state machine and `target_key`.
- **Package layout:** the `db/` file names.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check`, `ruff format --check`, `uv run mypy` (strict, 31 files) | pass |
| `uv run pytest -m "not slow"` | **82 passed** (45 earlier + 37 new DB tests) |
| Timing-sensitive DB tests (concurrency, heartbeat, lost lease, DB down) | 10 consecutive runs, all passed |
| `python3 -I scripts/check_docs.py` | PASS |

**The DB tests cover:**

- **Migrations and roles:** down/up/down; runtime role refused DDL and audit edits.
- **Constraints:** CHECK violations.
- **Delivery and run idempotency.**
- **Publications:** commit comment write-once; PR comment and Check Run upsert.
- **Signatures:** counting.
- **Queue state machine:** every transition, retries, `retry-after`, attempts exhausted, permanent errors, the deadline, lease expiry fencing, cancel, and a rollback mid-claim.
- **Caps and concurrency:** the per-installation cap with 50 jobs from one installation; one running job per run; 8 concurrent workers × 50 jobs with no double claim and the cap never exceeded.
- **Worker:** handler outcomes; heartbeat; lost lease; DB down at claim (no URL leaked); DB failure on complete or fail, leading to a safe re-run.

### Coverage gaps (not claimed as passed)

| Test | Status |
|---|---|
| AT-EVT-05, AT-EVT-06 | Need the webhook endpoint (T-106) |
| AT-REL-04 | Queue level only (cap of 2 per installation, other installations progress). The end-to-end check through webhook and worker is still open. |
| AT-PUB-01, AT-PUB-02 | Only the storage half (write-once and upsert keys). Publishing is T-502. |

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
