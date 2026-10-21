# First private staging: one VM, Docker Compose (T-1002)

**Status:** prepared and rehearsed locally (latest 2026-10-22, project `tw-rehearsal2`, `localhost`, loopback-only
port override, throwaway secrets, run as the host user). Rehearsed: missing-secret refusal (no directory created),
role template, `\password` via `psql -c`, `migrate status`/`upgrade`, preflight, key mount (0600, read-only),
`up -d web worker proxy` with the proxy waiting for readiness, `/healthz` and `/readyz` 200, 404 for every other path,
signed `ping` accepted, unsigned refused (401), a 20 MB body passed and a 27 MB body refused (413) through the proxy,
`retention` twice, `ops report`, `ops alerts`, `pg_dump`/`pg_restore` as the owner, graceful worker stop, no secret
in any log. **Not rehearsed:** steps marked **(live)**; public certificate issuance and renewal; `chown 10001` key
ownership (the rehearsal ran as the host user); the cron entries on a real host; `recovery deliveries|runs` (they
contact GitHub; only `recovery --help` ran). Nothing has been deployed.

Two milestones, kept apart:

- **Milestone A: GitHub pipeline with the fake provider** (this document, steps 1–12). It proves intake, queueing,
  evidence collection, publication, lifecycle and recovery against real GitHub. Every analysis ends "could not
  complete": **it says nothing about diagnosis quality.**
- **Milestone B: the real-model smoke test (T-605).** Separate approval, separate procedure (§B below and
  docs/SMOKE-RUNBOOK.md). It does not change this deployment.

## Why this setup

| Requirement (DEPLOYMENT-BLUEPRINT §2a) | How it is met | Evidence |
|---|---|---|
| `tracewise_system` with `BYPASSRLS`, not superuser; owner not superuser | Self-managed `postgres:16`: the repository's role template runs unchanged as `postgres` | Rehearsal: template exit 0; roles `tracewise_system` bypassrls=t, others f; migration 0011 as the non-superuser owner |
| HTTPS to `POST /webhooks/github`, ≥25 MB bodies, ≥10 s | Caddy with automatic certificates; no body limit at the proxy (the app caps 25 MB); only 3 routes proxied | Rehearsal: `/healthz` 200, `/readyz` 200, `/docs` 404, signed ping `pong`, unsigned 401. **Public certificate issuance needs DNS + inbound 80/443 (live)** |
| Long-running worker, stop grace ≥600 s | `stop_grace_period: 10m` | Rehearsal: idle worker stops in 1 s, exit 0, `worker.stopping` → `worker.stopped` |
| Scheduled recovery, retention, alerts | Cron on the VM running the `jobs` profile (step 11) | Commands are the repository's CLIs |
| Secrets as files and env, outside the image | `$TW_SECRETS_DIR` (mode 700, files 600), one env file per process | Compose refuses to start without `TW_SECRETS_DIR` |
| Separate runtime roles per process | web gets only the system URL and the webhook secret; worker the two runtime URLs and the App key; migrate only the owner URL | Preflight exit 0 in the rehearsal |

**Main trade-off:** you operate the host: OS patching, PostgreSQL backups (`pg_dump`, OPERATIONS §8), disk, restarts,
and a single point of failure. Acceptable for a private staging with test organisations; revisit before a pilot.

**Why not a managed PostgreSQL first:** support for creating a `BYPASSRLS` role is not verified for the common
services. Neon documents it only for projects created after 2023-08-15; Azure Flexible Server documents that its admin
cannot create non-admin BypassRLS roles on PostgreSQL 15 and below; the RDS and Cloud SQL documentation found shows
no way to do it (only the provider's internal role has it). A managed service is possible later **after** a test
`CREATE ROLE … BYPASSRLS` succeeds there.

**What could invalidate this choice:** a VM provider that blocks inbound 80/443 or outbound HTTPS to `github.com`
and `api.github.com`, or no DNS name you control for `TW_DOMAIN` (Caddy then cannot obtain a certificate).

## Readiness status (2026-10-22)

`READY` = evidence exists; `BLOCKED` = needs an external resource or your action; `NOT VERIFIED` = can only be
checked on the real host. Nothing below is marked done without evidence.

| | Item | Status | Evidence now / evidence that changes it |
|---|---|---|---|
| A | Linux VM, DNS name | BLOCKED | You provision it; `getent hosts <TW_DOMAIN>` resolves to the VM |
| A | Firewall (80/443 in, SSH from your address, outbound HTTPS) | BLOCKED | `curl -sI https://api.github.com` from the VM returns 200; an external scan shows only 22 (restricted), 80, 443 |
| A | Test org, `tw-push`, `tw-pr`, `tw-fork` + fork | BLOCKED | Exist with synthetic code and a CI workflow you can fail |
| A | Dev App (exact permissions, `workflow_run`, webhook URL and secret), **not installed** | BLOCKED | App settings page shows them; App id and key downloaded |
| A | Seven secret files, mode 600, `app.pem` owned by uid 10001 | BLOCKED | `ls -ln $TW_SECRETS_DIR` |
| A | Host access with Docker Engine and Compose v2 | BLOCKED | `docker compose version` on the VM |
| B | Image builds, non-root uid 10001, git present, no default process, allowlist build context | READY | `make image-check` (8/8) and `tests/unit/test_staging_compose.py` |
| B | Roles: only `tracewise_system` has BYPASSRLS; migration as the non-superuser owner; superuser and non-owner refused | READY | Compose rehearsal; `tests/db/test_migrate_cli.py`, `tests/db/test_least_privilege.py` |
| B | Preflight (config, key, roles, schema head, definer owner) | READY | Rehearsal exit 0; `tests/unit/test_preflight.py`, `tests/db/test_preflight_database.py` |
| B | Health/readiness, proxy routes, signature check, 25 MB limit, proxy waits for readiness | READY | Rehearsal over local HTTPS (`tw-rehearsal2`) |
| B | Backup and fresh-volume restore | READY (local) | Throwaway-container restore above; `tests/db/test_backup_restore.py` |
| B | Regression suite, truth lock, protected paths | READY | `make ci` and `python -m tracewise.bench verify` in the latest handoff |
| C | Public DNS, certificate issuance and renewal | NOT VERIFIED | `curl -sv https://<TW_DOMAIN>/healthz` shows a publicly trusted certificate; renewal: certificate still valid after 60+ days |
| C | Outbound GitHub from the containers | NOT VERIFIED | S0 publishes; `docker compose logs worker` shows no `github_unavailable` |
| C | uid 10001 reads `app.pem` | NOT VERIFIED | Step 9 preflight exit 0 on the VM (`github_app_private_key` pass) |
| C | Real proxy and network timing (GitHub's 10 s) | NOT VERIFIED | GitHub's delivery log shows 2xx within 10 s for S0 |
| C | Cron jobs and recovery against real GitHub | NOT VERIFIED | S1 recovery JSON; cron entries' logs after you enable them (after S1) |

## Milestone A: setup, in order

Run on the VM from a checkout of the approved commit; working directory `deploy/staging`. Every Compose command
needs `TW_SECRETS_DIR` and `TW_DOMAIN` exported (Compose refuses to start without them). Never paste a secret into a
command line, a ticket or chat.

| # | Create / configure | Command | Success | If it fails |
|---|---|---|---|---|
| 1 | **(live)** Linux VM with Docker Engine and the Compose plugin; a DNS A/AAAA record `TW_DOMAIN` → the VM | `docker compose version`; `getent hosts <TW_DOMAIN>` | Compose v2+; the name resolves to the VM | Fix DNS; wait for propagation before step 9 |
| 2 | **(live)** Firewall: inbound 80 and 443 open to the internet (certificate issuance and GitHub webhooks); SSH only from your address; nothing else. Outbound HTTPS allowed | `curl -sI https://api.github.com` from the VM | HTTP 200 | Open outbound 443; GitHub access is required by the worker, recovery and git fetch |
| 3 | **(live, you)** Test organisation with `tw-push`, `tw-pr`, `tw-fork` (+ a fork of it); a dev GitHub App with permissions exactly Actions read, Contents read, Metadata read, Pull requests write, Checks write; event `workflow_run`; webhook URL `https://<TW_DOMAIN>/webhooks/github`; a random webhook secret (≥16 characters). **Do not install it yet** (that is S0). Download its private key | GitHub UI | App id and `.pem` in hand | The App's first `ping` delivery fails until step 9; harmless |
| 4 | Secrets directory outside the checkout | `sudo install -d -m 700 -o "$USER" /etc/tracewise`; `export TW_SECRETS_DIR=/etc/tracewise TW_DOMAIN=<host>` | `ls -ld /etc/tracewise` shows `drwx------` | — |
| 5 | Secret files, each `chmod 600` (names only; values from your password manager): `pg_superuser_password`; `system.env` (`DATABASE_URL_SYSTEM`); `web.env` (`TW_ENV=test`, `GITHUB_WEBHOOK_SECRET` = the App's secret); `worker.env` (`TW_ENV=test`, `LLM_PROVIDER=fake`, `DATABASE_URL`); `app.env` (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/app.pem`); `migrate.env` (`DATABASE_URL_MIGRATIONS`); `app.pem` (`sudo chown 10001 app.pem`). URLs: `postgresql://<role>:<password>@db:5432/tracewise` with roles `tracewise_owner` (migrate), `tracewise_app` (worker), `tracewise_system` (system); **percent-encode** any password character outside letters, digits and `-._~` (rehearsed with `@`, `/` and `:`). Each process receives only its files: web = system + web; worker = system + worker + app; recovery = system + app; retention and ops = system; migrate = migrate; preflight = all | `ls -l $TW_SECRETS_DIR` | seven files, `-rw-------`; `app.pem` owned by uid 10001 | A missing file stops Compose ("bind source path does not exist" or "env file … not found"); create it. Nothing creates a directory in its place |
| 6 | Image (no registry until you authorise publishing) | from the repository root: `make image` | `Successfully tagged tracewise:local` | Re-run; needs outbound access to the base image registries |
| 7 | Database and roles | `docker compose up -d db`; `docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -f /provision/provision_roles.sql`; then for each of `tracewise_owner`, `tracewise_app`, `tracewise_system`: `docker compose exec db psql -U postgres -d tracewise -c '\password <role>'` (prompts; use the values in the env files) | template exits 0; `docker compose exec db psql -U postgres -tAc "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname LIKE 'tracewise%'"` shows only `tracewise_system` with `t` | Template errors mean it ran twice or on the wrong database: `docker compose down -v` (deletes the empty database) and repeat |
| 8 | Migration (owner URL only) | `docker compose --profile jobs run --rm migrate upgrade`; `docker compose --profile jobs run --rm migrate status` | `{"before": null, "after": "0011", ...}`; status exit 0 with `"at_head": true` | Exit 2: the named setting is wrong (never the URL). Exit 1: database unreachable or migration failed; fix and re-run (upgrade is idempotent) |
| 9 | Preflight | `docker compose --profile jobs run --rm preflight` | exit 0; warnings only `llm_provider` (fake) and `analysis_quota_monthly`; confirm the 4 `manual` lines against the App | Exit 2: fix each `fail` check by name; exit 3: an invalid setting (named) |
| 10 | Start | `docker compose up -d web worker proxy`; `docker compose ps` | the proxy starts only after web is `healthy` (`/readyz` 200); worker and proxy `Up`; `docker compose logs worker` shows `worker.started` | `docker compose logs <service>`; the worker exits 2 on a configuration refusal (the message names the setting) |
| 11 | **(live)** Health and ingress | `curl -s -o /dev/null -w '%{http_code}' https://<TW_DOMAIN>/healthz` and `/readyz`; any other path | 200, 200, 404. Then "Redeliver" the App's `ping` in GitHub: 200 `pong`, web log `webhook.ping` | No certificate: check DNS and inbound 80/443, `docker compose logs proxy`. `/readyz` 503: its body names `unavailable`, `wrong_database_role` or `schema_mismatch`. Ping 401: the webhook secret in `web.env` differs from the App's |
| 12 | **(live)** Live validation | docs/LIVE-VALIDATION-PLAN.md "Stage gates": readiness, then S0, S1 … S5 in order | each gate's "Proceed when" | each stage's cleanup and the plan's rollback conditions |
| 13 | Schedules, after S1 and your approval (cron on the VM) | see below | entries run; `recovery` JSON `"completed": true` | `recovery` exit 1 is "incomplete" (re-run later); `retention` exit 3 is "run again"; `ops alerts` exit 2 is "firing" |

```bash
*/15 * * * * cd <checkout>/deploy/staging && TW_SECRETS_DIR=/etc/tracewise TW_DOMAIN=<host> docker compose --profile jobs run --rm recovery deliveries
0 * * * *    cd <checkout>/deploy/staging && TW_SECRETS_DIR=/etc/tracewise TW_DOMAIN=<host> docker compose --profile jobs run --rm recovery runs
30 3 * * *   cd <checkout>/deploy/staging && TW_SECRETS_DIR=/etc/tracewise TW_DOMAIN=<host> docker compose --profile jobs run --rm retention
*/10 * * * * cd <checkout>/deploy/staging && TW_SECRETS_DIR=/etc/tracewise TW_DOMAIN=<host> docker compose --profile jobs run --rm ops alerts
```

Alert routing is still your decision (threshold 0.2 is provisional).

**Milestone A is complete when** (fake provider; diagnosis content is **not** under test):
- S0: one failing push on `tw-push` → exactly one `workflow_run.completed` ingested (`webhook.ingested` `enqueued`), one
  commit comment with the `<!-- tracewise:cc:wfN -->` marker and one neutral Check Run "Tracewise" carrying the
  could-not-complete notice; two re-runs give one delivery per attempt, the comment count stays 1 and the Check Run is
  updated in place.
- S1–S3 pass their gates (no second job per run attempt; declined permission recorded as `unpublished_permission`;
  suspension, removal and uninstall cancel without writes).
- No abort condition occurred (no token in logs, no write outside the three surfaces or the test organisation).

**Backup and restore** (OPERATIONS §8). Take a backup before every migration, as the owner, over the container's
local socket:

```bash
docker compose exec -T db pg_dump -U tracewise_owner -d tracewise -Fc > /var/backups/tracewise-$(date +%F).dump
```

**Restore** (verified locally on 2026-10-22 with throwaway `postgres:16` containers: revision, rows, RLS, no TEMP for
the runtime roles, non-superuser purge owner, `migrate status` at head): start from an **empty** `pgdata` volume,
run step 7 (the role template creates the hardened `tracewise` database the env files name, then set the three
passwords), then

```bash
docker compose exec -T db pg_restore --exit-on-error -U tracewise_owner -d tracewise < <backup file>
docker compose --profile jobs run --rm migrate status
docker compose --profile jobs run --rm preflight
```

and start the services only when both exit 0. Do **not** restore into an ad-hoc `CREATE DATABASE`: it misses the
template's hardening (runtime roles would get TEMP) and the env files would not point at it. Keep dump files as
secret as the database: they hold the diagnosis excerpts. Never downgrade below migration 0005 with data present.

**Certificates:** Caddy obtains and renews the certificate for `TW_DOMAIN` itself; it needs the DNS record, inbound
80 and 443, and the `caddy_data` volume kept (deleting it forces a new issuance; issuers rate-limit repeated ones).

**Teardown:** `docker compose --profile jobs down` keeps the data; `docker compose --profile jobs down -v` deletes it.

## Milestone B: real-model smoke test (T-605), separate

Nothing here is enabled: `LLM_PROVIDER=openai` refuses to start in this build. Prerequisites (SMOKE-RUNBOOK §1,
items A-1 to A-7): your written authorisation for one smoke run (≤3 requests); the exact model id and its source; a
project-scoped key in a file outside the repository (`chmod 600`, never an env var or chat); confirmation of the
account's retention and training settings; approval of the request content, the command and the cost bound.
**Command** (run by you, on your machine, not on the staging VM): SMOKE-RUNBOOK §2. **Success:** the outcome classes
in SMOKE-RUNBOOK §6 (the endpoint accepts the recorded request shapes and returns the recorded response shapes). A
pass proves the contract, not diagnosis quality; wiring the provider and the real-model evaluation are further,
separate approvals.
