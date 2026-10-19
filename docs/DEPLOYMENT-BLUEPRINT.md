# Deployment blueprint (T-1002 design; NOT a deployment)

This is a vendor-neutral design for a staging, then pilot, deployment. **Nothing has been deployed, configured or scheduled.** The hosting platform is **not chosen**: the repository holds no evidence of the intended environment (ADR-09 is "decided at T-1002"), so this document gives requirements, not vendor configuration. All values are placeholders.

## 1. Done versus remaining

| Done (verified locally) | Remaining (environment-dependent; gated) |
|---|---|
| Web ASGI factory and worker CLI, with startup validation, role and schema checks, readiness, graceful shutdown (OPERATIONS §1a; `test_process_entrypoints.py`, `test_worker_main.py`) | Choose a host or platform (ADR-09) and a managed Postgres |
| Migrations as a separate owner operation (`db/migrate.py`); the role template (`scripts/db/provision_roles.sql`) | Provision roles and credentials, with separation (D-11) |
| Recovery, ops and retention CLIs with exit codes | Schedules for recovery, retention and alerts |
| Structured JSON logs with scrubbing; the failure-rate rule | Log shipping, alert routing, error reporting (ADR-12 "Sentry at pilot") |
| | TLS, a public webhook URL, ingress limits; backups; a staging soak (T-1003) |

## 2. Processes

| Process | Command | Replicas | Notes |
|---|---|---|---|
| **web** | `uvicorn --factory tracewise.web.asgi:create_runtime_app --host 0.0.0.0 --port <PORT>` | ≥1 | Stateless. Each uvicorn worker process has its own pool (max 10 connections, `make_pool` default). It must answer within GitHub's 10 s (EV-P05); it only records and enqueues. |
| **worker** | `python -m tracewise.worker` | ≥1 | One job at a time per process. Run N processes for N parallel jobs; the queue caps **2 running jobs per installation** across all workers (FS-EVT-6). It holds two pools (system and tenant, max 10 each); size them to the platform's connection budget. |
| **migrate** (job) | `tracewise.db.migrate.upgrade(DATABASE_URL_MIGRATIONS)` | One-off, before a release | **The only process with owner credentials.** Never part of web or worker startup. Both refuse to run on a schema other than their build's head. |
| **recovery** (job) | `python -m tracewise.recovery deliveries` / `runs` | Scheduled (gated) | Bounded and checkpointed; exit 1 means incomplete. Suggested cadence for decision: deliveries every 15 min, runs hourly. |
| **retention** (job) | `python -m tracewise.retention` | Scheduled (gated) | Exit 3 means run again; 1 means error. Suggested: daily. |
| **alerts** (job) | `python -m tracewise.ops alerts` | Scheduled (gated) | Exit 2 means firing. **Threshold 0.2 is provisional.** It needs routing. |

**Shutdown:**
- **web:** SIGTERM drains in-flight requests and closes the pool. uvicorn re-raises SIGTERM, so the exit status is −15; the orchestrator must treat that as clean.
- **worker:** SIGTERM stops claiming and finishes the current job, which can take up to the 10-minute deadline. Set the orchestrator's grace period to **at least 600 s**, or accept that a killed job's lease (120 s) expires and another worker re-runs it. Publication is idempotent, so a re-run is safe.

## 3. Ingress and TLS (web only)

- TLS terminates at the platform. Only `POST /webhooks/github`, `GET /healthz` and `GET /readyz` exist; no docs routes.
- **Request size:** the app enforces 25 MB (GitHub's payload cap, EV-P04). Any proxy limit must be at least 25 MB.
- **Request timeout:** at least 10 s.
- Do **not** add IP allowlisting based on assumptions. The HMAC signature is the control (EV-P07). If allowlisting is wanted, use GitHub's published meta ranges (live gate).
- Health checks: liveness on `/healthz` (no database access); readiness on `/readyz` (database reachable and at the schema head; 503 otherwise).

## 4. Secrets and credential separation

| Secret | Consumer | Separation rule |
|---|---|---|
| `DATABASE_URL_MIGRATIONS` (owner) | migrate job only | Never mounted into web or worker |
| `DATABASE_URL_SYSTEM` (`tracewise_system`) | web, worker, recovery, retention, ops | Distinct credential from the tenant URL |
| `DATABASE_URL` (`tracewise_app`) | worker only | The worker refuses a role that bypasses RLS, and refuses the same URL as the system one |
| `GITHUB_WEBHOOK_SECRET` (at least 16 characters) | web only | Same value as the App's webhook settings |
| App private key file (`GITHUB_APP_PRIVATE_KEY_PATH`) and `GITHUB_APP_ID` | worker, recovery | Mounted as a 0600 file, not an env value |
| `OPENAI_API_KEY` | worker only | Only after T-605; the adapter is not enabled yet |

Inject secrets through the platform's secret store. Never bake them into images or logs. They are registered with the log scrubber at process start.

## 5. Environment variable inventory (placeholders)

| Variable | web | worker | recovery | retention | ops | migrate | Example (placeholder) |
|---|---|---|---|---|---|---|---|
| `TW_ENV` | opt | opt | opt | opt | opt | — | `staging` |
| `DATABASE_URL_SYSTEM` | **req** | **req** | **req** | **req** | **req** | — | `postgresql://tracewise_system@<host>/tracewise` |
| `DATABASE_URL` | — | **req** | — | — | — | — | `postgresql://tracewise_app@<host>/tracewise` |
| `DATABASE_URL_MIGRATIONS` | — | — | — | — | — | **req** | `postgresql://tracewise_owner@<host>/tracewise` |
| `GITHUB_WEBHOOK_SECRET` | **req** | — | — | — | — | — | `<from secret store>` |
| `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` | — | **req** | **req** | — | — | — | `<app id>`, `/run/secrets/app.pem` |
| `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY` | — | **req** | — | — | — | — | blocked until T-605 |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | — | opt | — | — | — | — | from T-605 |
| `INVESTIGATION_MAX_TOOL_CALLS` (≤12), `INVESTIGATION_TIMEOUT_S` (≤120), `REPORT_MAX_CHARS` | — | opt | — | — | — | — | defaults |
| `LOG_MAX_BYTES_PER_JOB` | — | opt | — | — | — | — | FS-LOG-4 per-job **retention** budget (default 2 MB); wired since Phase 31 |

## 6. Database

- **Roles:** `tracewise_owner` (owns the schema; migrations), `tracewise_app` (tenant plane, RLS), `tracewise_system` (BYPASSRLS; system plane). All are non-superuser. The template revokes TEMP and CREATE from PUBLIC. That revoke **has not been applied to any real database**.
- **Minimum permissions:** as granted by migrations 0001–0009 (verified by `test_fresh_install.py`):
  - the app role has DML on tenant tables, filtered by RLS, and no recovery tables;
  - the system role has DML on all tables, no DELETE on content, audit append-only, and EXECUTE on `tracewise_purge` only;
  - neither runtime role can write `alembic_version` or create objects.
- **Connection budget:**
  - web: 10 × uvicorn workers per replica;
  - worker: 20 per process (two pools);
  - each job opens, at most, the CLI's single pool.

  Size `max_connections` (or a pooler) accordingly. A pooler in **transaction mode** is compatible **in principle** with the transaction-local tenant setting (`set_config(..., true)`). However, psycopg's automatic server-side prepared statements can conflict with some poolers in that mode (it may need `prepare_threshold=None`). This is **not verified**: test it on staging.
- **Backups:** platform point-in-time recovery. Take a manual backup before every migration. Never downgrade below 0005 with tenant data present (that removes RLS).

## 7. Logs, failures, alerts

- Logs are JSON lines on stderr. Ship them to the platform's log store and retain them according to the privacy decision.
- **Alert on:**
  - `alert.failure_rate` (exit 2 from `ops alerts`);
  - `worker.failed` or `worker.refused`;
  - the web process failing readiness;
  - `retention.failed`;
  - recovery exit 1 on several consecutive runs;
  - `job.record_failed`;
  - `analysis.ops_record_failed`.
- Routing (pager, email) is a decision for T-1002.

## 8. Staging validation before any production use

1. Fresh install from the template; migrate; run the read-only checks from `test_fresh_install.py`.
2. Deploy web and worker. Readiness is 200. Configuration-refusal checks: wrong role and same URL give exit 2.
3. Live plan S0–S3 against the test org (LIVE-VALIDATION-PLAN), with a model enabled only if T-605 is done.
4. Verify the pooler with RLS: two tenants processed concurrently, and tenant isolation queries (as in `test_rls.py`) against staging.
5. Exercise recovery, retention (with a seeded expired tenant) and ops alerts manually. Then enable schedules, after approval.
6. Soak (T-1003). Measure p50/p95 (`ops report`) and confirm cost, if priced.

Any failure is a stop condition (OPERATIONS §10).
