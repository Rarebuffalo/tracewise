# Operations and release readiness (offline package, Phase 16)

This document prepares a **later, approved** pilot. Nothing here has been deployed, scheduled or run against GitHub or a real database. Every command below was exercised only against disposable local fixtures.

## 0. Current status

| Ready (verified offline) | Not ready |
|---|---|
| Schema, migrations 0001–0011, roles, RLS, the purge function (`tests/db/test_fresh_install.py`) | Hosting, process supervision, TLS and ingress for the webhook URL (T-1002, gated) |
| **Process entry points** (Phase 18): web via uvicorn, worker via `python -m tracewise.worker` (§1a) | |
| Webhook intake, queue, worker, publisher, recovery, retention and observability (offline suites) | **No real model adapter** (D-7). The only provider is `fake`. A real one is T-605. |
| CLIs: `python -m tracewise.{recovery,ops,retention,bench}` | Credential provisioning (D-11), schedules, alert routing (T-1002) |

**Stop condition for any pilot:** do not start one until T-605 (model adapter and evaluation) and T-1002 (process wiring, hosting) are approved and done, and stages S0–S3 of [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) pass.

## 1. Fresh installation and migration order

1. **Roles.** A database administrator runs `scripts/db/provision_roles.sql` as superuser, once. It creates the non-superuser owner and the `tracewise_app` and `tracewise_system` roles, and the `tracewise` database. It sets no passwords and revokes TEMP and CREATE from PUBLIC.
2. **Authentication.** Configure authentication for the three roles (password, certificate or IAM) **outside this repository**. That is the D-11 decision.
3. **Migrate.** Run the migrations as the owner: `python -m tracewise.db.migrate upgrade` with only `DATABASE_URL_MIGRATIONS` set. It refuses (exit 2, before any change) a missing owner URL, a URL or user shared with a runtime URL, a connection that turns out to be `tracewise_app`/`tracewise_system`, a **superuser** (the SECURITY DEFINER purge would then run with superuser rights; `--allow-superuser` is for disposable development clusters only), or a role that does not own the existing schema; exit 1 is an unreachable database or a failed migration. `python -m tracewise.db.migrate status` prints the current and head revisions (exit 0 at head, 4 behind). This applies 0001–0011. The runtime roles must exist before this step, otherwise they get no grants, which fails closed.
4. **Verify.** Run the checks on the target database before use:
   - `SELECT version_num FROM alembic_version` must return `0011`;
   - **Migration 0010** (per-installation keys) is reversible only while no two installations share an old global key. After a repository transfer they may, and the downgrade then refuses (`downgrade 0010 refused: …`) without deleting anything; the operator must resolve the rows explicitly.
   - the grant and RLS checks in `tests/db/test_fresh_install.py`. Adapt that file's queries to read-only use; do not run the test suite against a real database.
5. **New migrations** must keep `tests/db/test_db_security.py` passing:
   - every tenant table has RLS and its policy;
   - every other table is declared system-only;
   - any SECURITY DEFINER function pins `pg_temp` last.

## 1a. Running the processes locally

Placeholders only; use non-production roles on a disposable database. Neither process migrates, so run the migrations first (§1).

**Environment variables:**

| Variable | Web | Worker | Notes |
|---|---|---|---|
| `DATABASE_URL_SYSTEM` | required | required | `tracewise_system` (BYPASSRLS) |
| `DATABASE_URL` | — | required | `tracewise_app` (RLS); must be a different role |
| `GITHUB_WEBHOOK_SECRET` | required (≥16 characters) | — | Same value as in the App settings |
| `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` | — | required | Project App only; the key file is RSA PEM with mode 0600 |
| `LLM_PROVIDER` | — | required | `openai` (with `OPENAI_API_KEY`, `LLM_MODEL`), or `fake`, which is accepted **only** with `TW_ENV=test` |
| `TW_ENV` | optional | optional | `local`, `test`, `staging` or `prod` |

**Web** (ASGI factory; nothing runs at import):

```
DATABASE_URL_SYSTEM=postgresql://tracewise_system@/tracewise?host=<socket-dir> \
GITHUB_WEBHOOK_SECRET=<webhook-secret> \
uv run uvicorn --factory tracewise.web.asgi:create_runtime_app --host 127.0.0.1 --port 8000
```

- `/healthz` is liveness and never touches the database.
- `/readyz` returns 200 only when the database is reachable, `DATABASE_URL_SYSTEM` connects as the BYPASSRLS system role, **and** the schema is at this build's revision. Otherwise it returns 503 with `unavailable`, `wrong_database_role` or `schema_mismatch`.
- The web process refuses to start (non-zero exit; the message names the setting and the role, never the URL) when `DATABASE_URL_SYSTEM` is reachable but uses the tenant role, the owner or a superuser. This is the same contract as the worker. An unreachable database does not block startup; readiness reports it.
- `python -m tracewise.ops report|alerts` checks the same role first. A wrong role prints `{"error": "wrong_database_role"}` and exits 1, like `database_unavailable`. Under RLS the tenant role would see no rows, and that must never be reported as `insufficient_data`. Exit 2 still means a firing alert.
- A missing or invalid setting stops startup with its **name** only.
- SIGTERM shuts down gracefully, closing the pool. uvicorn then re-raises the signal, so the exit status is −15 after "Application shutdown complete."

**Worker:**

```
DATABASE_URL=postgresql://tracewise_app@/tracewise?host=<socket-dir> \
DATABASE_URL_SYSTEM=postgresql://tracewise_system@/tracewise?host=<socket-dir> \
GITHUB_APP_ID=<app-id> GITHUB_APP_PRIVATE_KEY_PATH=<path-to-pem> LLM_PROVIDER=openai OPENAI_API_KEY=<key> LLM_MODEL=<model> \
uv run python -m tracewise.worker [--worker-id ID] [--once] [--idle-sleep 1.0]
```

Note: `LLM_PROVIDER=openai` **currently refuses to start** (the adapter is validated offline only; see
[MODEL-ADAPTER.md](MODEL-ADAPTER.md) §2b). The example shows the intended production shape. For local process
checks use `TW_ENV=test LLM_PROVIDER=fake` ([DEVELOPMENT.md](DEVELOPMENT.md) §4).

The worker refuses to start (exit 2) when:
- a setting is missing;
- the same URL is used for both roles;
- the tenant URL is not an RLS-restricted role (system, owner or superuser);
- the system URL is not the BYPASSRLS role;
- the schema is not at this build's head;
- the key is unreadable;
- the fake provider is configured outside `TW_ENV=test`.

An unreachable database at startup gives exit 1. At startup it sweeps workspaces left by a killed process.

| Signal | Effect |
|---|---|
| First SIGTERM or SIGINT | Stop claiming, finish the current job, close the pools, exit 0. The handlers are installed before startup validation (`worker.starting`), so a stop during startup also exits 0 without claiming. Only a signal during interpreter start-up and imports (under 1 s) uses the default action. |
| Second signal | Immediate abort. The job's lease expires and another worker reclaims it, publishing once (tested). |

An unexpected error in the loop exits 1 instead of spinning.

## 2. Roles and credential separation

| Variable | Role | Used by | Must never be |
|---|---|---|---|
| `DATABASE_URL_MIGRATIONS` | `tracewise_owner` | Migrations only | Used by any runtime process |
| `DATABASE_URL` | `tracewise_app` (RLS) | Analyze handler, publisher | The system or owner role; the handler refuses these (`WrongDatabaseRole`) |
| `DATABASE_URL_SYSTEM` | `tracewise_system` (BYPASSRLS) | Webhook intake, lifecycle, queue, recovery, retention, ops | Given to the analysis path |
| `DATABASE_URL_OPERATOR` | one **personal** login per person, member of `tracewise_operator` | `ops requeue` only | Shared between people, a service role, or stored in the services' secrets directory |

- Keep three separate secrets, with separate rotation.
- RLS limits forgotten filters and wrong ids. It does **not** contain arbitrary SQL running as `tracewise_app` (SECURITY-AUDIT §2).
- The system role bypasses RLS. Its code paths are guarded by application checks.

### 2a. Operator logins (requeue identity, migration 0013)

The requeue audit records the PostgreSQL login that ran it (`session_user`). That record is only as trustworthy as
the logins, so:

1. **One login per person; never shared, never a service role.** As the database administrator (the role that ran
   `scripts/db/provision_roles.sql`), in `psql` connected to the `tracewise` database:

   ```
   CREATE ROLE ops_<name> LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS IN ROLE tracewise_operator;
   ```

   The login has no password yet. Group membership is its only privilege: EXECUTE on `tracewise_requeue`. It has no
   table access.
2. **Set the credential without it touching shell history, logs or chat.** In `psql`, run `\password ops_<name>`.
   `psql` prompts for the password, hashes it client-side (SCRAM) and sends only the hash. Never use
   `ALTER ROLE ... PASSWORD '...'` (statement logs and history keep it). Never put a password in a SQL file, a ticket
   or a message. Generate it with the password manager or `openssl rand -base64 32`, and type or paste it only into
   the `\password` prompt. If the deployment uses certificate or IAM authentication, use that instead and skip
   passwords entirely.
3. **Deliver it to that person only, through the team's password manager.** No secret manager is chosen for this
   project yet (deployment decision T-1002). Whatever is chosen must: hold one entry per operator, restrict each
   entry to its owner, keep an access log, and support rotation. Do **not** add operator credentials to
   the services' secrets directory (`deploy/staging`): those files are read by service processes, not people.
4. **Supply `DATABASE_URL_OPERATOR` for one command, not in a profile file.** For example, read from the password
   manager into the environment of a single run. Better, use libpq's own files: `~/.pgpass` (mode 600) or a
   `PGSERVICEFILE` entry, so the URL itself holds no password (`postgresql://ops_<name>@host/tracewise`). Never echo
   the URL, never put it on the command line, never commit it.
5. **Remove access** the same day someone leaves the rota:

   ```
   REVOKE tracewise_operator FROM ops_<name>;
   ALTER ROLE ops_<name> NOLOGIN;
   ```

   Keep the role, so audit rows naming it stay attributable. Drop it only after its audit rows have expired (365 days).
6. **Rotate** with `\password ops_<name>` (step 2), at least when a device is lost or a person changes teams.

**Why `--operator` is only a cross-check:** anyone can type any name. The identity is what PostgreSQL authenticated.
`--operator` only makes a human typo or a wrong `DATABASE_URL_OPERATOR` visible (`operator_mismatch`) before
anything is read.

**Limits of the attribution:**
- A database superuser can run `SET SESSION AUTHORIZATION ops_<name>` and act as that person. Superusers are refused
  by the function itself, but impersonation through `SET SESSION AUTHORIZATION` cannot be prevented inside the
  database. Keep superuser access to the database administrator, separately audited (`log_connections`, and the host's
  own access logs).
- A shared or leaked password makes the record name the wrong person. Steps 1–6 exist to prevent that.

## 3. GitHub App

**Permissions** (FS-INS-2): exactly these, no user-to-server authorisation, and the `workflow_run` event. GitHub also sends `installation` and `installation_repositories` events to every App.

| Permission | Level |
|---|---|
| Actions | read |
| Contents | read |
| Metadata | read |
| Pull requests | write |
| Checks | write |

| Surface | When | Permission | Notes |
|---|---|---|---|
| Commit comment | Push failure, or a PR run whose association is ambiguous or failed (D-4) | Contents read (doc EV-P09; live gate G-PLAT-5) | Write-once per (repo, sha, workflow) |
| PR comment | PR failure with a matched PR | Pull requests write | Upserted |
| Check Run "Tracewise" | Every outcome | Checks write | Neutral; updated in place |

**Known risk (G-PLAT-11, F-1):** one publish token bundles Contents read, Pull requests write and Checks write. If GitHub refuses to mint it for an installation that declined one permission, **no** surface publishes (simulated). Verify in S2 of the live plan before the pilot. The fix (per-surface tokens) awaits approval.

## 4. Webhook setup and signature verification

- Endpoint: `POST /webhooks/github`. Secret: `GITHUB_WEBHOOK_SECRET`.
- Verification: HMAC-SHA256 over the raw body against `X-Hub-Signature-256`, compared in constant time.

| Condition | Response | Recorded? |
|---|---|---|
| Missing or wrong signature | 401 | No |
| Body over 25 MB | 413 | No |
| Bad headers | 400 | No |
| Invalid payload | 400 | Yes, as `rejected` |
| Secret not configured | 503 | No |

- Accepted deliveries are deduplicated by `X-GitHub-Delivery` (14 days) and by run (repo, run, attempt; 365 days). The delivery, run and job rows are inserted in one transaction.
- `GET /healthz` is liveness; `/readyz` is readiness and checks the database.
- GitHub requires a 2xx within 10 s (EV-P05); all work is queued.

## 5. Worker and recovery

**Queue:**
- 120 s lease, heartbeat every lease/3;
- ≤2 running jobs per installation;
- 10-minute deadline;
- 3 attempts with backoff (honouring `retry-after`).

**Attempt deadline (C-4, 2026-11-01):** each attempt derives one deadline from the job's 10-minute deadline, less a
60 s publication reserve. Log downloads stop at it (the report says the logs are incomplete), the git fetch timeout
is capped by it, and the investigation gets only what is left (it is not started with under 10 s left: the report
says "the analysis ran out of time", with no model call). Publication uses the reserve and is never cut mid-request.
The two values are code defaults (`analysis/attempt.py`) pending owner decision O-2.

**Attempt ownership and stale workers (D-1, D-2; migration 0012):** a job attempt owns the job only while the row
says so (`locked_by` and `attempts`, status `running`). When a lease expires, the next claim reaps it
(`queue.lease_expired`) and the new claim is a takeover (`job.claimed` with `takeover: true`, a higher `attempt`).
From then on the old worker cannot renew its lease, persist an analysis, record a publication, write the ops record,
complete, fail or cancel the job: each refusal is logged as `job.stale_attempt_rejected` (with the `stage`) and the
old worker stops (`job.stale_attempt_stopped`). One limit remains: a GitHub request already in flight at the moment of
takeover can still be applied; it is never recorded, and the new owner adopts it (see ARCHITECTURE §4.4).
**Deploy order:** run the migration (0012) before starting workers at this version; workers refuse to start on an
older schema. Rolling back the code needs no schema change; downgrading 0012 makes this code refuse to start.

**Re-running a dead job (I-6):**

```
DATABASE_URL_OPERATOR=<your own login> python -m tracewise.ops requeue --job-id N --reason {transient_outage|fixed_configuration|fixed_permission|operator_request} [--dry-run] [--operator YOUR_LOGIN]
```

**Who may run it:** a person with their **own** database login that is a member of `tracewise_operator` (create one
per person: `scripts/db/provision_roles.sql`). The decision and the writes happen in `tracewise_requeue` (migration
0013). The audit actor is `operator:<session_user>`, the login PostgreSQL authenticated, not a typed name.
`--operator` is only a cross-check: a mismatch is refused (`operator_mismatch`). Shared service roles (owner, tenant,
system) and superusers are refused (`not_authorised`) before any job is looked at.

**What it does:** it requeues only a `dead` analysis job of an active installation and an enabled repository, with no
job for the same run queued, waiting or running.
- **Concurrency:** requeues of one run are serialised by an advisory lock, so concurrent operators get one new job,
  and the others get `live_job_exists`.
- **Result:** it inserts a new linked job (fresh attempt and deadline) and keeps the dead row. The job and its
  `audit_event` (`job.requeued`: actor, reason code, job ids, the limit in force) commit together or not at all.
  `--dry-run` writes nothing.
- **Unchanged for the re-run:** the quota gate and publication reconcile apply as usual.
- **Exit status:** 0 when queued (or `would_requeue` with `--dry-run`); 1 when refused (the JSON `outcome` or
  `error` says why).

**Re-run limit:** `tracewise_requeue_max_reruns()` returns 2 per original job (**provisional**, pending the owner).
Only the schema owner can change it, by replacing that one-line function (normally a reviewed migration). Sessions
cannot override it. Values outside 0–10 are refused.

**Read and validation failures:** `context.read_retry` / `context.read_retries_exhausted` (transient GitHub
failures on code reads), `context.read_permanent_error` (one file unreadable; the analysis continues),
`analysis.validation_unavailable` (validation could not read the code; the attempt is retried),
`analysis.permanent_failure` (the analysis ended on a permanent error; a could-not-complete notice is published),
`context.source_unavailable` / `analysis.source_unavailable` (the code could not be reached; retried, then "could not
complete"), `tool.error` (a tool returned an error: `category` says which kind), `tool.internal_error` (a defect in a
tool: investigate the `where` location; the job retries, then ends `dead` with a notice).

**Publication recovery (F1):** an analysis whose publication did not complete is published by the next attempt, or
by a requeue of the dead job, without a new investigation (`analysis.publication_resumed`). `ops report` shows it
under `publication_incomplete` (`analyses`: pending for over 15 minutes; `surfaces_unconfirmed`: reserved but never
confirmed). With either above zero, check `job` for that run; if the job is `dead`, requeue it (§5, requeue).
`ops report` also shows the current `queue` (queued, retry_wait, running, running with an expired lease, oldest
waiting age), `provider_failures` in the window, and the last `retention` run.

**Publication:** `publication.attempted` precedes each GitHub write; `publication.result` reports the outcome per
surface; `publication.outcome_uncertain` means a write failed transiently and may still have been applied (the next
attempt reconciles); `publication.reconciled` means a retried or taken-over job rewrote a surface in place;
`publication.superseded_retained` means the write-once commit comment shows an earlier attempt's report (the Check
Run says so; the App cannot edit commit comments without Contents write).

**Database session bounds (all runtime pools: web, worker, recovery, retention, ops):** `statement_timeout` 30 s and
`lock_timeout` 10 s per session (`db/session.py`). Hitting either is reported as the database being unavailable, so
the job or pass is retried later instead of holding a worker. They are set per session, so `options` in a database
URL are left alone; they are code constants, not environment settings.

Expired leases are reaped at the next claim (`queue.lease_expired`). Handlers are idempotent at GitHub: they reconcile before creating, and POSTs are never retried inline.

**Recovery:** `python -m tracewise.recovery {deliveries|runs|both}` runs one bounded pass.

| Exit | Meaning |
|---|---|
| 0 | Complete |
| 1 | Incomplete, or the database was unavailable. The JSON summary says why: `rate_limited`, `github_unavailable`, `list_failed`, `page_cap`, `request_cap`, `app_auth_failed` (a redelivery POST's App JWT was refused; no attempt is counted) or `failed_repos`. |

- Checkpoints in `recovery_checkpoint` advance only after the step they cover, so a pass is safe to re-run.
- One pass of each kind at a time: an overlapping `deliveries` (or `runs`) pass stops at once with `"stopped": "locked"` and exit 1, before any GitHub request (`recovery.locked`). Different kinds may overlap. Safe for cron.
- Redelivery is limited to 3 attempts and a 15-minute cooldown, uncertain attempts included.
- **No schedule is installed.** Suggested cadence for the pilot, to be decided at T-1002: deliveries every 15 min, runs every hour.

## 6. Retention and purge

`python -m tracewise.retention [--batch-limit N] [--max-batches M] [--dry-run]` runs bounded batches of
`tracewise_purge()`. Since migration 0017, data of a run with a live job (queued, waiting or running) is skipped
until the job ends.
- **Audit:** every real run writes one content-free `audit_event` (`system:retention`, `retention.run`: counts,
  batches, completed, error type).
- **Dry run:** `--dry-run` reports exactly what a run would delete now, by running the batches in one transaction
  and rolling it back. It writes nothing, and it holds the same row locks while it runs.

| Exit | Meaning | Action |
|---|---|---|
| 0 | Done | None |
| 3 | More remains | Run again |
| 1 | Error | See the JSON `error` and the `retention.failed` event |

- Re-running is always safe: batches are idempotent and committed one at a time. A concurrent run returns `locked`.
- **Recovery after a failure:** fix the cause (database reachability, privileges), then re-run. A partial tenant purge resumes, and `purged_at` is set only when the tenant is fully purged.
- Policy is in §9. **No schedule is installed.**

**Scheduling (not enabled by this repository).** The deployment schedules its jobs with cron on the VM
([deploy/staging/README.md](../deploy/staging/README.md), step 13: `retention` daily, next to `recovery` and
`ops alerts`). Review a dry run first. Exit 3 means "more remains"; the next scheduled run continues. Check
the `retention.finished` events and the `retention.run` audit rows. Alert on exit 1, or on no `retention.run` row for
two days.

**Operational logs (the 14-day period, D-12 recommendation):** the container logs are rotated by size only (json-file,
10 MB × 3 per service), so their age is not bounded. For a 14-day maximum, use the host's journald:
1. Set `logging: driver: journald` for the services. This is a host and compose change: make it in the deployment,
   not here.
2. Set `MaxRetentionSec=14day` in `/etc/systemd/journald.conf`.
3. Restart journald. That is a host operation: schedule it.

The logs contain no repository content by design (event deny-list), so this bounds metadata, not code or log
excerpts.

## 7. Observability

- **Events:** the stable event catalogue is in ARCHITECTURE §4.8. JSON lines go to stderr with correlation ids. Secrets, query strings, auth and cookie values are scrubbed, and request-URL library loggers are quieted.
- **Report:** `python -m tracewise.ops report [--window-hours 24]` gives outcomes, job states, retries and p50/p95, each with its sample size (`null` when there is no data), plus tokens, cost (`null`/"unpriced" until prices are set) and publication states.
- **Alert:** `python -m tracewise.ops alerts` evaluates the failure rate, (dead + could_not_complete) / finished, over 1 h. It exits 2 when firing and logs `alert.failure_rate`.
- **Threshold 0.2 with ≥10 jobs is PROVISIONAL.** It is not a user-approved SLO. The output says `threshold_status: provisional`.
- No alert is routed anywhere (T-1002).

## 8. Backup, rollback and incident response

**Verified offline (Phase 51, `tests/db/test_backup_restore.py`):** a `pg_dump -Fc` taken as the owner, restored with `pg_restore` into a fresh cluster that already has the three roles, gives the same rows and revision, keeps RLS, the grants and the purge function's pinned `search_path`, satisfies both runtime role checks, and still isolates tenants. The roles must exist before the restore. Not verified: platform point-in-time recovery, restore time at production size.

| Situation | Action |
|---|---|
| Before any migration | Back up the database (operator tool, e.g. `pg_dump`). Migrations are reversible (`downgrade`), but **never downgrade below 0005 with tenant data present**: that removes RLS. |
| Bad application release | Stop the workers (the leases expire and jobs are retried later), deploy the previous build, re-run `recovery both`. Publication is idempotent. |
| Database outage | The webhook returns 503; GitHub records failed deliveries. After recovery, run `recovery deliveries`. Workers back off (`worker.db_unavailable`). |
| GitHub outage or rate limit | Jobs retry with backoff. Recovery passes stop with `rate_limited` or `github_unavailable`; re-run later. |
| Suspected credential leak | Rotate the affected secret at its source: the App private key or webhook secret in GitHub's App settings, the database role credential, the model key. Then restart the processes. Logs are scrubbed, but check `logs` access too. |
| Suspected cross-tenant exposure | Stop workers and intake. Preserve the logs. Run the RLS and schema guards (`test_db_security.py` queries) against the database, read-only. Review `audit_event`. |
| Uninstalled tenant asks for deletion before the grace period | A policy decision. The purge honours `purge_after` (+7 days, FS-INS-3). |

### 8b. Migrations 0012–0017: order, rollback and forward recovery

Order: **stop web and workers**, back up, run `migrate` (as the owner) to `0017`, run `preflight`, and only then
start the new web and worker build. Stopping first matters: 0016 updates `analysis` and 0017 builds an index on
`job`, both in one transaction that blocks writers, and old processes must not run on the new schema. An existing
database provisioned before 0013 needs the `tracewise_operator` group created first (deploy/staging README). Both refuse a schema other than their head (`SchemaMismatch`), so an old worker cannot run unfenced on a new
schema, nor a new worker on an old one. Rollback means downgrading the schema **and** redeploying the matching build
together. Verified on a disposable cluster: `tests/db/test_migrations_0012_0017.py` (populated 0011 upgrade, every
round trip), `test_fresh_install.py` (template plus all migrations), `test_privilege_matrix.py`.

| Revision | What | Downgrade | Data lost on downgrade | Forward recovery after a failed upgrade |
|---|---|---|---|---|
| 0012 | `tracewise_job_owned` (attempt fence) | Drops the function. A build at 0012+ then refuses to start | none | Re-run `migrate`: each revision is one transaction |
| 0013 | `tracewise_requeue`, `tracewise_requeue_max_reruns()` | Drops both. Requeue becomes unavailable; earlier audit rows stay | none (an owner-changed limit returns to 2 on re-upgrade) | Re-run. If `tracewise_operator` was created after 0013, also run the GRANT from `provision_roles.sql` |
| 0014 | Usage breakdown columns | Drops the three columns | **yes**: cached input, reasoning output and `usage_source` values | Re-run |
| 0015 | Least-privilege grants | Restores the 0001/0005 grants exactly | none | Re-run. Grants are idempotent |
| 0016 | Backfill `usage_source = no_call` (proven rows only) | No-op (the values stay true) | none | Re-run |
| 0017 | Purge skips runs with live jobs; `job_live_run` index | Restores the 0008/0009 purge body; drops the index | none | Re-run. `CREATE INDEX` on a very large `job` table takes a lock: run in a quiet window |

## 8a. Troubleshooting (prepared offline; not exercised against a live deployment)

Run every SQL below **read-only, as the system role** (`DATABASE_URL_SYSTEM`); the tenant role sees no rows outside a
tenant transaction. Never paste a URL, token or log blob into a ticket. Start with `python -m tracewise.preflight
--database` (exit 0 required) and `python -m tracewise.ops report`.

| Symptom | Check | Action |
|---|---|---|
| **Webhooks fail** (GitHub shows red deliveries) | Events: `webhook.signature_rejected` (401), `webhook.not_configured` (503), `webhook.db_unavailable` (503), `webhook.too_large` (413), `webhook.bad_headers` / `webhook.payload_rejected` (400). `/readyz` reason. | 401: the App's webhook secret and `GITHUB_WEBHOOK_SECRET` differ; set both again, restart web. 503: fix the setting or the database, then `recovery deliveries` (redelivery is capped and cooled down, §5). 400: a payload outside the contract; record the delivery GUID only. |
| **Webhook accepted, nothing happens** | `SELECT outcome, count(*) FROM webhook_delivery WHERE received_at > now() - interval '1 hour' GROUP BY 1` (column names per migration 0001). `ignored` is expected for successful runs and unsupported events. | `enqueued` but no job progress: see the next row. `duplicate_run`: dedupe by (repo, run, attempt) is working as designed. |
| **Jobs stuck** | `SELECT status, count(*), min(run_after), max(updated_at) FROM job WHERE finished_at IS NULL GROUP BY 1`. `running` with `locked_until < now()` = a dead worker; `retry_wait` with `last_error` = backing off. Events: `queue.lease_expired`, `job.lease_lost`, `worker.db_unavailable`. | No worker running: start one (it reaps expired leases at the next claim). ≤2 running jobs per installation is a limit, not a fault. Never edit `job` rows by hand; a job past `max_attempts` becomes `dead` with a bounded `last_error`. |
| **Publication failed** | `SELECT surface, state, count(*) FROM publication GROUP BY 1, 2`. `unpublished_permission` with `missing_permission` = the installation declined a permission (`publication.permission_refused`); `failed` with `last_error`. | Permission: the installer must accept it in GitHub; Tracewise never escalates. `failed`: transient GitHub errors retry with the job (3 attempts). There is no automatic re-publication after that; a workflow re-run (a new attempt) is analysed and published afresh. Publication reconciles before creating, so retries never duplicate a commit comment (FS-PUB-1 trigger). `recovery runs` only finds failed runs whose webhook never arrived. |
| **Database unavailable** | `worker.db_unavailable`, `webhook.db_unavailable`, `/readyz` → 503 `unavailable`; `ops` exits 1 with `database_unavailable`. | Restore the database. Workers back off on their own; web keeps answering 503 so GitHub records the deliveries. Afterwards: `recovery deliveries`, then `recovery runs`. `wrong_database_role` or `schema_mismatch` instead: a configuration or migration problem, not an outage (preflight names which). |
| **Provider failures** | `SELECT status, count(*) FROM analysis WHERE created_at > now() - interval '1 hour' GROUP BY 1`: a rise in `could_not_complete`; `alert.failure_rate`. The job itself succeeds (it published the could-not-complete notice). | Timeouts, 429 and 5xx are retried inside the investigation's time budget; then the run is reported as could-not-complete, never as a diagnosis. Quota (`insufficient_quota`) and auth (401/403) errors are not retried: fix the account or key at its source, restart the workers. With the `fake` provider no analysis names a root cause: a log with no recognised error line ends `inconclusive` without a provider call, one with an error line ends could-not-complete. |
| **Quota reached** | `analysis.quota_exceeded`; analyses with status `quota_exceeded`; at most one notice per repository per UTC day. | Expected when `ANALYSIS_QUOTA_MONTHLY` is set. Raising it is an owner decision. |

## 9. Data retention and privacy

- **Never stored:** full logs or full source files (AT-SEC-12, verified offline after 20 analyses), webhook bodies, tokens.
- **Stored, redacted, inside the diagnosis document:**
  - log excerpts of at most 2000 bytes each;
  - a source snippet of up to 15 lines at the validated location (the stored copy is at most 2000 bytes; P-3);
  - model-written explanation and fix text.

  The redaction is pattern-based (P-4).

| Data | Retention |
|---|---|
| Diagnosis document (holds the log and code excerpts: the only log-derived content in the database) | 90 days (D-12a). Not 14: the 14-day recommendation concerns operational log files (§6) |
| Analyses, with their publications | 180 days |
| Deliveries | 14 days |
| Fingerprints, runs, terminal jobs, usage, audit (including operator logins on requeue records, and `retention.run` records), redelivery bookkeeping | 365 days |
| Data of a run with a live job | Kept until the job ends (0017) |
| Non-terminal jobs | Never deleted |
| Tenant purge | 7 days after uninstall, once no job is in flight; a tombstone and 365-day audit rows remain |

**These retention interpretations are pending D-12.**

- What goes to a model provider (excerpts, code context) must be stated in the T-1001 privacy notice before any pilot.

## 10. Staged validation and release checklist

See [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) for stages S0–S5.

**Release checklist.** Every item must be true; any "no" is a stop.

1. Offline gate: `make check` and the full suite (`pytest -m "not live"`) pass, and the slow-inclusive benchmark is complete with the truth lock verified.
2. Every review-queue decision that affects the pilot is made and recorded: G-PLAT-11, D-10, D-11, D-12, the threshold, and the benchmark items that affect confidence.
3. T-605: a real-model evaluation was run and reported, with no accuracy claims beyond what it measured.
4. T-1001: privacy notice and pilot terms are ready.
5. T-1002: processes are wired, credentials are provisioned with separation, schedules and alert routing are configured and reviewed.
6. Live plan S0–S3 passed in the test org, with the evidence archived.
7. Backup taken, and the rollback steps rehearsed on staging.

**Stop immediately** (also during a pilot) when any of these happens:
- any cross-tenant read or write;
- any GitHub write outside the three surfaces;
- a duplicated commit comment;
- a token or secret in a log;
- RLS disabled on a tenant table;
- a purge deleting a tenant that is not due;
- `alert.failure_rate` firing, until it is understood.
