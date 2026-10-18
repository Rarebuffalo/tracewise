# Operations and release readiness (offline package, Phase 16)

This document prepares a **later, approved** pilot. Nothing here has been deployed, scheduled or run against GitHub or a real database. Every command below was exercised only against disposable local fixtures.

## 0. Current status

| Ready (verified offline) | Not ready |
|---|---|
| Schema, migrations 0001–0009, roles, RLS, the purge function (`tests/db/test_fresh_install.py`) | **No process entry point for the web server or the worker.** `create_app()` and `Worker` exist; wiring them into processes is T-1002. |
| Webhook intake, queue, worker, publisher, recovery, retention and observability (offline suites) | **No real model adapter** (D-7). The only provider is `fake`. A real one is T-605. |
| CLIs: `python -m tracewise.{recovery,ops,retention,bench}` | Credential provisioning (D-11), schedules, alert routing (T-1002) |

**Stop condition for any pilot:** do not start one until T-605 (model adapter and evaluation) and T-1002 (process wiring, hosting) are approved and done, and stages S0–S3 of [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) pass.

## 1. Fresh installation and migration order

1. **Roles.** A database administrator runs `scripts/db/provision_roles.sql` as superuser, once. It creates the non-superuser owner and the `tracewise_app` and `tracewise_system` roles, and the `tracewise` database. It sets no passwords and revokes TEMP and CREATE from PUBLIC.
2. **Authentication.** Configure authentication for the three roles (password, certificate or IAM) **outside this repository**. That is the D-11 decision.
3. **Migrate.** Run the migrations as the owner, in order: `tracewise.db.migrate.upgrade(<owner url>)`. This applies 0001–0009. The runtime roles must exist before this step, otherwise they get no grants, which fails closed.
4. **Verify.** Run the checks on the target database before use:
   - `SELECT version_num FROM alembic_version` must return `0009`;
   - the grant and RLS checks in `tests/db/test_fresh_install.py`. Adapt that file's queries to read-only use; do not run the test suite against a real database.
5. **New migrations** must keep `tests/db/test_db_security.py` passing:
   - every tenant table has RLS and its policy;
   - every other table is declared system-only;
   - any SECURITY DEFINER function pins `pg_temp` last.

## 2. Roles and credential separation

| Variable | Role | Used by | Must never be |
|---|---|---|---|
| `DATABASE_URL_MIGRATIONS` | `tracewise_owner` | Migrations only | Used by any runtime process |
| `DATABASE_URL` | `tracewise_app` (RLS) | Analyze handler, publisher | The system or owner role; the handler refuses these (`WrongDatabaseRole`) |
| `DATABASE_URL_SYSTEM` | `tracewise_system` (BYPASSRLS) | Webhook intake, lifecycle, queue, recovery, retention, ops | Given to the analysis path |

- Keep three separate secrets, with separate rotation.
- RLS limits forgotten filters and wrong ids. It does **not** contain arbitrary SQL running as `tracewise_app` (SECURITY-AUDIT §2).
- The system role bypasses RLS. Its code paths are guarded by application checks.

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

Expired leases are reaped at the next claim (`queue.lease_expired`). Handlers are idempotent at GitHub: they reconcile before creating, and POSTs are never retried inline.

**Recovery:** `python -m tracewise.recovery {deliveries|runs|both}` runs one bounded pass.

| Exit | Meaning |
|---|---|
| 0 | Complete |
| 1 | Incomplete, or the database was unavailable. The JSON summary says why: `rate_limited`, `github_unavailable`, `list_failed`, `page_cap`, `request_cap` or `failed_repos`. |

- Checkpoints in `recovery_checkpoint` advance only after the step they cover, so a pass is safe to re-run.
- Redelivery is limited to 3 attempts and a 15-minute cooldown, uncertain attempts included.
- **No schedule is installed.** Suggested cadence for the pilot, to be decided at T-1002: deliveries every 15 min, runs every hour.

## 6. Retention and purge

`python -m tracewise.retention [--batch-limit N] [--max-batches M]` runs bounded batches of `tracewise_purge()`.

| Exit | Meaning | Action |
|---|---|---|
| 0 | Done | None |
| 3 | More remains | Run again |
| 1 | Error | See the JSON `error` and the `retention.failed` event |

- Re-running is always safe: batches are idempotent and committed one at a time. A concurrent run returns `locked`.
- **Recovery after a failure:** fix the cause (database reachability, privileges), then re-run. A partial tenant purge resumes, and `purged_at` is set only when the tenant is fully purged.
- Policy is in §9. **No schedule is installed.** Suggested cadence: daily.

## 7. Observability

- **Events:** the stable event catalogue is in ARCHITECTURE §4.8. JSON lines go to stderr with correlation ids. Secrets, query strings, auth and cookie values are scrubbed, and request-URL library loggers are quieted.
- **Report:** `python -m tracewise.ops report [--window-hours 24]` gives outcomes, job states, retries and p50/p95, each with its sample size (`null` when there is no data), plus tokens, cost (`null`/"unpriced" until prices are set) and publication states.
- **Alert:** `python -m tracewise.ops alerts` evaluates the failure rate, (dead + could_not_complete) / finished, over 1 h. It exits 2 when firing and logs `alert.failure_rate`.
- **Threshold 0.2 with ≥10 jobs is PROVISIONAL.** It is not a user-approved SLO. The output says `threshold_status: provisional`.
- No alert is routed anywhere (T-1002).

## 8. Backup, rollback and incident response

| Situation | Action |
|---|---|
| Before any migration | Back up the database (operator tool, e.g. `pg_dump`). Migrations are reversible (`downgrade`), but **never downgrade below 0005 with tenant data present**: that removes RLS. |
| Bad application release | Stop the workers (the leases expire and jobs are retried later), deploy the previous build, re-run `recovery both`. Publication is idempotent. |
| Database outage | The webhook returns 503; GitHub records failed deliveries. After recovery, run `recovery deliveries`. Workers back off (`worker.db_unavailable`). |
| GitHub outage or rate limit | Jobs retry with backoff. Recovery passes stop with `rate_limited` or `github_unavailable`; re-run later. |
| Suspected credential leak | Rotate the affected secret at its source: the App private key or webhook secret in GitHub's App settings, the database role credential, the model key. Then restart the processes. Logs are scrubbed, but check `logs` access too. |
| Suspected cross-tenant exposure | Stop workers and intake. Preserve the logs. Run the RLS and schema guards (`test_db_security.py` queries) against the database, read-only. Review `audit_event`. |
| Uninstalled tenant asks for deletion before the grace period | A policy decision. The purge honours `purge_after` (+7 days, FS-INS-3). |

## 9. Data retention and privacy

- **Never stored:** raw logs and source code (AT-SEC-12, verified offline after 20 analyses).
- **Stored:** redacted excerpts of 2 KB or less inside the diagnosis document.

| Data | Retention |
|---|---|
| Diagnosis document (holds the excerpts) | 90 days |
| Analyses, with their publications | 180 days |
| Deliveries | 14 days |
| Fingerprints, runs, terminal jobs, usage, audit, redelivery bookkeeping | 365 days |
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
