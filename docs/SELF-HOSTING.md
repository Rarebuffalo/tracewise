# Self-hosting Tracewise

This is the authoritative guide for running Tracewise on your own Linux machine or server with Docker Compose. The
step-by-step command table for a server lives next to the Compose files in
[deploy/staging/README.md](../deploy/staging/README.md) (the directory name is historical: the same bundle serves
staging and self-hosting). Everything here describes what the code does today; where something has not been
verified it says so.

## 1. What you get, and what you do not (yet)

Tracewise is a GitHub App you run yourself. When a GitHub Actions run fails (conclusion `failure` or `timed_out`),
GitHub sends a signed `workflow_run` webhook. Tracewise verifies the signature, queues the run, downloads the failed
jobs' logs (at most 5 jobs), reads the code at the failing commit and the push's diff, runs a deterministic
pre-pass (failed step, first error, sibling failures), then a bounded, read-only AI investigation, validates every
claim against the evidence, and publishes **one** report per run:

- a neutral Check Run named **"Tracewise"** on the commit (it never fails or blocks your build), and
- a **commit comment** (push runs; written once) or a **PR comment** (pull-request runs; updated in place).

When the evidence is not enough, the report says it could not determine the root cause instead of guessing.
Re-runs update the existing Check Run and comment; duplicate webhooks are ignored.

**Current limits you must know before inviting anyone:**

| | Status |
|---|---|
| Real AI diagnoses | **Not available yet.** The OpenAI provider is implemented and tested offline but refuses to start until the smoke test is approved and run (§9). |
| What runs today | The **fake provider** (`LLM_PROVIDER=fake`, only with `TW_ENV=test`). No analysis names a root cause. Two outcomes depend on the failed job's log: **(1) no recognised error line** (for example only `Process completed with exit code 1`): the deterministic pre-pass ends the analysis as `inconclusive` (`no_error_line`) **without invoking the provider**; this is a completed analysis, so it is published under the existing policy (commit comment on push runs, PR comment on PR runs, and the Check Run). **(2) a recognised error line** (for example a Python traceback): the investigation runs, the fake provider fails each attempt, and after the retries (about 1–3 minutes) the run ends `could_not_complete`, published on the Check Run (and the PR comment on PR runs), never as a commit comment (FS-ERR-1, D-8). Either way it proves the GitHub pipeline (delivery, queue, logs, permissions, publication), **not** diagnosis quality. |
| Live GitHub validation | **Not done.** The staged plan is [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md). |
| Architectures | **amd64 verified** (image build and stack checks). **arm64 not verified** (§11). |

## 2. Prerequisites

- Linux with Docker Engine and the Compose plugin **v2.24 or newer** (`docker compose version`). Earlier versions
  lack the `!override` tag used by the local-trial file.
- `git`, `make`, `curl`, `openssl` on the host. No Python, PostgreSQL or registry is needed to run the stack.
- To build: outbound access to Docker Hub, `ghcr.io` (the `uv` image) and PyPI during `make image`.
- For real GitHub deliveries: a server with a public DNS name and inbound 80/443 (§5). A laptop can run the local
  trial but cannot receive GitHub's webhooks.
- Optional, for development and the offline test suite: `uv` and PostgreSQL server binaries (see
  [DEVELOPMENT.md](DEVELOPMENT.md)).

## 3. Local trial (one machine, nothing exposed)

The same stack, published only on `127.0.0.1:8443` by [compose.local.yaml](../deploy/staging/compose.local.yaml).
Use it to rehearse setup, migrations, preflight, health and signed test deliveries. It was rehearsed on 2026-10-22
(amd64): preflight exit 0, `/healthz` and `/readyz` 200 through HTTPS, a signed `ping` accepted, the port
**not** reachable from the machine's network address, and the database intact after `down`/`up`.

1. Build the image from the repository root: `make image` (tags `tracewise:local`).
2. Create the secrets directory and files exactly as for a server (§6), with `TW_DOMAIN=localhost`. The App id and
   key can be from a dev App that is not installed anywhere.
3. In `deploy/staging`, add `-f compose.yaml -f compose.local.yaml` to every `docker compose` command of the
   server procedure (roles, `migrate upgrade`, `preflight`, `up -d web worker proxy`).
4. Check: `curl -sk https://localhost:8443/readyz` → 200 `{"status":"ready"}`; any other path → 404.
5. Signed test delivery (a `ping`; no GitHub involved), using the webhook secret from `web.env` without printing it:

```bash
SECRET=$(sed -n 's/^GITHUB_WEBHOOK_SECRET=//p' "$TW_SECRETS_DIR/web.env")
BODY='{"zen":"local trial"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -sk https://localhost:8443/webhooks/github -H 'X-GitHub-Event: ping' -H 'X-GitHub-Delivery: local-1' -H "X-Hub-Signature-256: sha256=$SIG" --data "$BODY"
unset SECRET
```

Expect `{"outcome":"pong"}`; without the signature header, 401. A synthetic `workflow_run` is **not** a safe test
here: the worker would call the GitHub API for an installation that does not exist.

Receiving real webhooks on a laptop needs a public relay; §3a describes the prepared tunnel procedure. A relay sends
your webhook payloads through a third party.

## 3a. Real GitHub deliveries to a laptop through a tunnel (prepared, not yet run)

A temporary HTTPS tunnel lets GitHub reach the local trial without a server. **Executed once on 2026-10-22** for a
GitHub App `ping` (Stage 1): GitHub's redelivered `ping` reached Tracewise through the tunnel and was answered 200
`pong` after signature verification (`webhook.ping` in the web log). The first `workflow_run` test followed on
2026-10-23 (§3b).

**How the pieces connect.** Public `https://<tunnel-host>/webhooks/github` → tunnel agent on this machine →
`https://localhost:8443/webhooks/github` (Caddy, loopback only) → `web:8000`. Two facts measured with the local
trial decide the agent's settings:

- Caddy's local certificate is for `localhost`, so the agent must connect to **`https://localhost:8443`** (TLS
  name `localhost`). Connecting to `127.0.0.1:8443` or with the tunnel's own name fails the TLS handshake.
- The local Caddy site only serves the name `localhost`. ngrok forwards the public hostname as `Host`, and Caddy
  answers that with an **empty 200 without reaching Tracewise** (observed on the first attempt: `server: Caddy`,
  no request in the web log). The traffic policy
  [deploy/staging/ngrok-local.yml](../deploy/staging/ngrok-local.yml) rewrites `Host` to `localhost`; Caddy routing
  and signature verification are unchanged.

With the installed ngrok v3 agent (upstream certificates are not verified unless `--upstream-tls-verify` is given,
which is what Caddy's local certificate needs), from `deploy/staging`:

```bash
ngrok http https://localhost:8443 --inspect=false --traffic-policy-file ngrok-local.yml
```

Before configuring GitHub, check the path through the tunnel: `https://<tunnel-host>/healthz` must return
`{"status":"ok"}` and `/docs` 404. An empty 200 with `server: Caddy` means the `Host` rewrite is missing.

`--inspect=false` turns off request capture (the agent's local API on `127.0.0.1:4040` still runs; with inspection
off it records no requests). The agent prints the public URL (`--log stdout --log-format json` shows it when the
inspector is off); the GitHub App's webhook URL is that URL plus `/webhooks/github`. Accounts with an assigned
`ngrok-free` domain keep the same URL between runs; otherwise update the App's webhook URL each time. Then use
"Redeliver" on the App's recent `ping` and expect 200 `{"outcome":"pong"}` and a `webhook.ping` line in
`docker compose logs web`.

**Signature and secrets.** GitHub signs each delivery with the App's webhook secret; the web process verifies it
before parsing (401 otherwise). Generate the secret into the file, never on a command line or in chat, and copy it
into the App settings from the file:

```bash
printf 'TW_ENV=test\nGITHUB_WEBHOOK_SECRET=%s\n' "$(openssl rand -hex 32)" | install -m 600 /dev/stdin "$TW_SECRETS_DIR/web.env"
```

Put the App's real id in `app.env` and its key in `app.pem` (`sudo chown 10001 app.pem`, mode 600). Restart web
and worker after changing them (`docker compose -f compose.yaml -f compose.local.yaml up -d web worker`).

**Privacy.** The tunnel provider terminates TLS and sees webhook payloads (repository and run metadata; never logs
or code, which the worker fetches directly from GitHub). Use a test organisation with synthetic code.

**Shutting down.** Stop the agent (Ctrl-C): the public URL stops working at once. Then, in GitHub, deactivate the
App's webhook or uninstall the App from the test repositories, and rotate the webhook secret if it was ever
exposed. The ngrok authtoken stays in `~/.config/ngrok/ngrok.yml` (mode 600); revoke it in the ngrok dashboard if
you no longer need it. Stop the stack with `docker compose -f compose.yaml -f compose.local.yaml stop`.

**What a laptop tunnel does not validate:** public certificate issuance and renewal (Caddy uses its local CA
here), uptime and behaviour while the laptop sleeps (GitHub records failed deliveries; `recovery deliveries` can
redeliver them later), cron reliability, a server's firewall and restart behaviour, and GitHub's 10-second limit
over a server's network rather than the tunnel's.

## 3b. First real workflow through the tunnel (prepared, not run; needs separate authorisation)

This is LIVE-VALIDATION-PLAN S0 under the owner's decision (option a): fake provider; commit-comment validation and
G-PLAT-5 stay **deferred** (not passed). Which surfaces a run publishes depends on its log (§1): no recognised
error line → `inconclusive` (`no_error_line`), a completed analysis published with the commit comment and the Check
Run; a recognised error line → `could_not_complete`, Check Run only. Executed once on 2026-10-23 with the workflow
below (print plus `sys.exit(1)`, so no error line): run 40008159332 ended `inconclusive` / `no_error_line` and
published one commit comment and one Check Run, as the existing policy requires.

**Credentials the worker needs** (it refuses to start without them; the web process needs only the webhook secret):

| Credential | Needed for | Where it lives | How to supply it |
|---|---|---|---|
| App ID | Signing the App JWT | `app.env`: `GITHUB_APP_ID=<number>` | Not secret; from the App's settings page. Write it with an editor or `printf 'GITHUB_APP_ID=%s\nGITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/app.pem\n' <id> > "$TW_SECRETS_DIR/app.env"` |
| App private key | Minting short-lived installation tokens | `app.pem` (mode 600, owner uid 10001) | Generate it in the App's settings, move the downloaded `.pem` (never paste it) with `install -m 600 <download> "$TW_SECRETS_DIR/app.pem"`, then `sudo chown 10001 "$TW_SECRETS_DIR/app.pem"`, and delete the download |
| Webhook secret | Verifying deliveries (web) | `web.env` | Already set (Stage 1) |
| Installation ID | — | **not configured** | Read from each webhook payload; tokens are minted per installation, repository and purpose |
| Model credentials | — | none | The fake provider needs none; OpenAI stays refused |

**Test repository.** Create a new repository used for nothing else (for example `tracewise-s0-test`, public or
private), containing only a deliberately failing workflow, for example `.github/workflows/s0.yml`:

```yaml
name: tracewise-s0
on: push
jobs:
  fail:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 -c "import sys; print('deliberate failure for the Tracewise S0 test'); sys.exit(1)"
```

Add the workflow file **before** installing the App, so only the deliberate push afterwards produces an analysed
failure. Install the App with **"Only select repositories" → this one repository**; the App receives
`workflow_run` events only for repositories it is installed on, so no other repository is affected.

**Sequence** (each step after the first needs the owner's go-ahead):

1. Start the local stack **with the worker** (§3, now that `app.env` and `app.pem` are filled), run the full
   preflight (`--process all --database`) → exit 0, and start the tunnel (§3a); check `/healthz` through it.
2. Install the App on the test repository. Expect `webhook.lifecycle` with `processed` in the web log (if this
   delivery is missed, the first `workflow_run` creates the installation row itself).
3. Push one commit. Expect `webhook.ingested` with `enqueued`; worker `job.claimed`; log and code collection; then
   one of two outcomes, decided by the log:
   - **no recognised error line** (the workflow below): `analysis.diagnosed` `inconclusive` without a provider call;
     `publication.result` for `commit_comment` and `check_run`; on GitHub one commit comment and one neutral Check
     Run "Tracewise" saying no root cause is claimed;
   - **a recognised error line** (for example `raise RuntimeError(...)`): the fake provider fails each attempt;
     retries after about 30 s and 120 s; `analysis.finished` with `could_not_complete`; `publication.result` for
     `check_run` only; on GitHub one neutral Check Run with the could-not-complete text and **no** commit comment.
4. "Re-run failed jobs" twice. Expect one new delivery per attempt (`run_attempt` 2, 3) and the same Check Run
   updated in place. The write-once commit comment (if the first attempt published one) is never added again.
5. Redeliver one `workflow_run` delivery from the App's Advanced tab. Expect `duplicate_delivery` and no new job.

**Network while it runs:** the laptop needs outbound HTTPS to `api.github.com`, `github.com` (`git fetch`) and the
log storage hosts GitHub redirects to; only `*.actions.githubusercontent.com` and `*.blob.core.windows.net` are
accepted. Any other redirect host makes the run end `logs_unavailable` (also Check-Run-only); record that as a
G-PLAT-8 finding, not a pass.

**Abort** on any write outside the test repository, a token or secret in a log, a duplicate Check Run for one run,
or a job that is neither retried nor finished. **Cleanup:** stop the tunnel; uninstall the App from the repository
(or delete the repository); `docker compose ... --profile jobs down -v` for the test project; keep or delete the
App and its key as you decide (revoke the key in the App settings when done).

## 4. Server deployment overview

Follow [deploy/staging/README.md](../deploy/staging/README.md) steps 1–13 in order; each step lists its command,
expected result and recovery. In short:

1. VM and DNS; firewall (inbound 80/443, SSH from your address only, outbound HTTPS).
2. Create the GitHub App (§7), **not installed** yet.
3. Secrets directory and files (§6).
4. `make image`.
5. Database and roles: `docker compose up -d db`, run `scripts/db/provision_roles.sql`, set the three passwords
   with `\password` (prompts; values never on the command line).
6. `docker compose --profile jobs run --rm migrate upgrade`, then `migrate status` → exit 0, `"at_head": true`.
7. `docker compose --profile jobs run --rm preflight` → exit 0 (warnings for the fake provider and an unset quota
   are expected).
8. `docker compose up -d web worker proxy`; the proxy starts only after `/readyz` succeeds.
9. `https://<TW_DOMAIN>/healthz` and `/readyz` → 200; other paths 404. Redeliver the App's `ping` in GitHub → 200.
10. Install the App on **one test repository**, push a failing commit, and check the result (§8).

## 5. HTTPS, domain and network

- GitHub delivers webhooks only to a publicly reachable HTTPS URL: `https://<TW_DOMAIN>/webhooks/github`.
- Caddy obtains and renews the certificate itself. It needs the DNS record, inbound 80 **and** 443, and the
  `caddy_data` volume kept (deleting it forces a new issuance; issuers rate-limit repeats).
- Only `/webhooks/github`, `/healthz` and `/readyz` are proxied; everything else is 404. PostgreSQL is never
  published. Request bodies up to 25 MB are accepted (GitHub's maximum); larger ones get 413.
- Outbound HTTPS to `api.github.com` and `github.com` is required (API, logs, `git fetch`). Later, the model
  provider's endpoint too.

## 6. Configuration and secrets

All values live in `TW_SECRETS_DIR` (for example `/etc/tracewise`, mode 700), **outside** the repository, each file
mode 600. Each process receives only the files it needs (enforced by `tests/unit/test_staging_compose.py`).

| File | Variables / content | Used by | Where the value comes from |
|---|---|---|---|
| `pg_superuser_password` | database superuser password | `db` only | you generate it |
| `system.env` | `DATABASE_URL_SYSTEM` (`tracewise_system`) | web, worker, recovery, retention, ops | role password you set in step 5 |
| `web.env` | `TW_ENV=test`, `GITHUB_WEBHOOK_SECRET` (≥16 random characters) | web | the same value you enter in the App settings |
| `worker.env` | `TW_ENV=test`, `LLM_PROVIDER=fake`, `DATABASE_URL` (`tracewise_app`), optional `ANALYSIS_QUOTA_MONTHLY` | worker | role password; quota is your choice |
| `app.env` | `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/app.pem` | worker, recovery | the App's settings page |
| `migrate.env` | `DATABASE_URL_MIGRATIONS` (`tracewise_owner`) | migrate (and preflight) | role password |
| `app.pem` | the App's private key; `chown 10001`, mode 600 | worker, recovery (read-only mount) | downloaded from the App's settings page |

Database URLs: `postgresql://<role>:<password>@db:5432/tracewise`; percent-encode any password character outside
letters, digits and `-._~`. A missing secret file stops Compose with an error; nothing is created in its place. The
full variable reference is [CONFIGURATION.md](CONFIGURATION.md). Never paste secrets into chats, tickets,
screenshots or command lines; `\password` and the files above keep them out of shell history.

**Roles (fixed design):** `tracewise_owner` owns the schema and runs migrations only (not a superuser);
`tracewise_app` is subject to row-level security on every tenant table; `tracewise_system` is the only role that
bypasses it. The processes and the migration CLI refuse the wrong role at startup.

## 7. GitHub App

Create it under the organisation (or account) that owns the repositories you want analysed:

- **Repository permissions, exactly:** Actions read, Contents read, Metadata read, Pull requests **write**,
  Checks **write**. Nothing else; no user authorisation or callback URL.
- **Event:** `workflow_run`. (Installation events are always delivered.)
- **Webhook URL:** `https://<TW_DOMAIN>/webhooks/github`; **secret:** the value in `web.env`; active.
- Generate a private key and store it as `app.pem` (§6).
- Install it only on the repositories you want analysed. A declined or missing permission is recorded as
  `unpublished_permission` and named in the Check Run; Tracewise never escalates.

## 8. What a first test shows

With the fake provider, push a commit whose CI fails in a repository where the App is installed. Expect, within
about 1–3 minutes:

- the web log shows `webhook.ingested` with `enqueued`; the worker logs `job.claimed`;
- if the log has **no recognised error line** (only an exit code): the analysis ends `inconclusive`
  (`no_error_line`) at once, without calling the provider. It is a completed analysis, so a push run gets one
  commit comment and one neutral Check Run **"Tracewise"** saying no root cause is claimed (a PR run gets the PR
  comment instead of the commit comment);
- if the log **has a recognised error line**: the fake provider fails each attempt, and after the final attempt
  (about 1–3 minutes) the run ends `could_not_complete`: one neutral Check Run, plus the PR comment on PR runs,
  **never** a commit comment (FS-ERR-1, D-8);
- re-running the failed job updates the same Check Run instead of adding a new one.

Inspect it with the commands in [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) ("How to inspect"). This
proves delivery, queueing, log access and publication permissions; it says nothing about diagnosis quality.

## 9. The real model (separate approval)

`LLM_PROVIDER=openai` refuses to start in this build. Enabling it is three separately approved steps:
(1) one smoke test of the API contract, run by the owner on their own machine with a project-scoped key file
([SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md) §1–§6); (2) wiring the provider; (3) the measured evaluation (T-605). Until
then no logs or code are sent to any model provider. What would be sent, and the limits applied, is listed in
[DATA-INVENTORY.md](DATA-INVENTORY.md) §3 and §5.

## 10. Operating it

| Task | How |
|---|---|
| Start / stop | `docker compose up -d web worker proxy`; `docker compose stop` (the worker finishes its current job; grace 10 min). `docker compose down` keeps data; `down -v` deletes it. |
| Restart behaviour | Services restart automatically (`unless-stopped`) after a crash or a Docker restart. A killed job's lease expires after 120 s and another attempt runs; publication is idempotent. |
| Health | `/healthz` = process alive; `/readyz` = database reachable, right role and schema head (503 with the reason otherwise). |
| Logs | Bounded `json-file` rotation (3 × 10 MB per service). Export evidence promptly: [deploy/staging/README.md](../deploy/staging/README.md), "Logs". |
| Backup / restore | Owner `pg_dump` before every migration; restore onto a fresh volume through the role template: same README, "Backup and restore". |
| Scheduled jobs | `recovery deliveries` (15 min), `recovery runs` (hourly), `retention` (daily), `ops alerts` (10 min) from cron; examples in the README step 13. Overlapping recovery passes refuse to run (`locked`). |
| Troubleshooting | [OPERATIONS.md](OPERATIONS.md) §8a (webhooks, stuck jobs, publication, database, provider, quota) and the table below. |

**Upgrade** (keeps data; take a backup first):

```bash
docker tag tracewise:local tracewise:previous
git pull --ff-only
make image
cd deploy/staging
docker compose exec -T db pg_dump -U tracewise_owner -d tracewise -Fc > /var/backups/tracewise-before-upgrade.dump
docker compose stop proxy web worker
docker compose --profile jobs run --rm migrate upgrade
docker compose --profile jobs run --rm preflight
docker compose up -d web worker proxy
```

Stopping web and worker before migrating avoids old processes running against a new schema (they check the schema
only at startup). **Rollback:** if `migrate upgrade` printed the same `before` and `after` revision (no schema
change), run the previous image (`TRACEWISE_IMAGE=tracewise:previous docker compose up -d web worker proxy`). If
the schema changed, restore the backup onto a fresh volume (README "Backup and restore") and then run the previous
image; the migration CLI has no downgrade command by design.

## 11. Resources and architectures

**Measured (amd64, idle, no jobs, 2026-10-22, `docker stats`):** proxy 19 MiB, web 72 MiB, worker 72 MiB,
db 45 MiB, about 210 MiB in total. Fresh database volume 49 MB. Images: `tracewise:local` 303 MB, `postgres:16`
451 MB, `caddy:2` 66 MB.

**Estimated, not measured (under load):** worker 150–500 MB during an analysis (log processing, a `git` fetch of
up to 256 MB into a temporary workspace, a grep subprocess); PostgreSQL 200–350 MB with all pools in use. Plan for
**2 GB RAM** and **10 GB free disk** (20 GB comfortable, including the build cache); container logs are capped at
about 120 MB in total. One job runs per worker process; run more worker containers for parallelism (the queue caps
2 running jobs per installation).

**Architectures:** amd64 is verified (`make image-check`, Compose rehearsals). arm64 is **not verified**: `uv.lock`
holds Linux aarch64 wheels for CPython 3.14 for every compiled dependency, the Dockerfile has no architecture-
specific step, and the base images are expected to be multi-architecture, but no arm64 image has been built or
run. On an arm64 host, build natively (`make image`) and pass the readiness steps before relying on it.

## 12. Your responsibilities as the operator

Server patching and Docker updates; firewall and SSH access; backups and restore tests; monitoring (`/readyz`,
`ops alerts`) and somewhere for alerts to go; disk space; rotating the webhook secret, the App key and database
passwords (OPERATIONS §8, "Suspected credential leak"); incident response; and deciding retention for your data
(defaults in OPERATIONS §9, pending D-12). Reports you publish are stored by GitHub under your repositories.

## 13. Data handling (summary)

Tracewise stores no webhook bodies, full logs or full source files. It keeps redacted excerpts (≤2000 bytes each)
and a ≤15-line source snippet inside the diagnosis for 90 days, metadata for up to 365 days, and nothing after a
tenant purge except a tombstone and audit rows. Logs are streamed in memory; source is fetched into a temporary
workspace and deleted. Redaction is pattern-based: split or encoded secrets can pass. Details and evidence:
[DATA-INVENTORY.md](DATA-INVENTORY.md); draft notice: [PRIVACY-NOTICE-DRAFT.md](PRIVACY-NOTICE-DRAFT.md) (not
legally reviewed).

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Compose: "required variable TW_SECRETS_DIR" or "bind source path does not exist" | Variables not exported, or a secret file missing | Export `TW_SECRETS_DIR` and `TW_DOMAIN`; create the named file |
| `migrate` exit 2, "superuser" / "runtime role" / "does not own the existing schema" | Wrong URL in `migrate.env` | Use `tracewise_owner`, the role that owns the schema |
| `preflight` exit 2 | A named check failed | Fix that setting; the message names it, never its value |
| `/readyz` 503 `wrong_database_role` or `schema_mismatch` | Wrong URL, or migrations not run | Correct `system.env`; run `migrate upgrade` |
| Worker exits 2 | Configuration refused (role, schema, key, provider) | `docker compose logs worker`; the message names the setting |
| GitHub shows 401 for deliveries | Webhook secret differs between the App and `web.env` | Set both to the same value; restart web |
| Check Run says a permission is missing | The installation lacks a permission | Accept the permission in the installation settings |
| No certificate | DNS not pointing at the VM, or 80/443 blocked | Fix DNS/firewall; `docker compose logs proxy` |
| Every analysis ends "could not complete" or "could not determine the root cause" | Expected with the fake provider: no root cause is ever named | See §1 and §9 |

## 15. Known limitations

Real-model diagnosis unavailable (§9); live GitHub behaviour not yet verified (LIVE-VALIDATION-PLAN S0–S5); arm64
unverified; Python and TypeScript are the languages with dedicated extractors (others use the generic one); the
commit-comment surface is exercised only by completed analyses (with the fake provider: logs without a recognised
error line, §8), and G-PLAT-5 stays deferred; recovery and scheduled jobs are untested
against real GitHub; no hosted service, dashboard or billing exists, by design.
