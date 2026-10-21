# Development guide

How to set up Tracewise locally, run it, and troubleshoot it. For contribution rules see
[../CONTRIBUTING.md](../CONTRIBUTING.md); for the test strategy see [TESTING.md](TESTING.md); for settings see
[CONFIGURATION.md](CONFIGURATION.md).

## 1. Tools

| Tool | Version | Why |
|---|---|---|
| Python | ≥ 3.12 (`requires-python`; development uses 3.14) | Runtime |
| [uv](https://docs.astral.sh/uv/) | current | Installs the locked dependencies (`uv.lock`) and runs every command |
| PostgreSQL server binaries | any supported release with `initdb`, `pg_ctl`, `psql`, `pg_dump`, `pg_restore` | The database tests start disposable clusters; local runs need a server |
| git | any | The code-context tests run a local `git http-backend` |

Node, npm and the JS test tools are **not** needed: their logs are fixtures.

```bash
uv sync
```

## 2. Package layout

| Path | Contents |
|---|---|
| `src/tracewise/web/` | FastAPI app: webhook endpoint, signature check, ingest, lifecycle events, health probes |
| `src/tracewise/jobs/` | PostgreSQL queue, worker loop, the `analyze` handler |
| `src/tracewise/github/` | GitHub App auth, HTTP client, publisher (Check Run, PR comment, commit comment) |
| `src/tracewise/prepass/` | Log envelope and retention, redaction, extractors, primary-error ranking |
| `src/tracewise/context/` | Read-only code context: confined workspace, the four investigation tools, trigger diff |
| `src/tracewise/investigate/` | Provider interface, bounded investigation loop, validator, OpenAI codec (offline) |
| `src/tracewise/analysis/` | Evidence collection and diagnosis assembly |
| `src/tracewise/report/` | Markdown rendering and escaping |
| `src/tracewise/db/` | Sessions, repositories, Alembic migrations (`migrations/versions/`) |
| `src/tracewise/bench/` | Offline benchmark harness, cases and truth lock |
| `src/tracewise/{worker,recovery,retention,ops}.py` | Process and CLI entry points |
| `scripts/` | Docs consistency check, fixture generator, role template, the isolated OpenAI smoke harness |
| `tests/` | Unit, DB, investigation, report, context and benchmark tests; fakes; the network guard |

## 3. Everyday commands

```bash
make check
```

```bash
make test-all
```

```bash
uv run ruff format src tests scripts
```

See [TESTING.md](TESTING.md) for focused runs and the CI command.

## 4. Running the processes against a local database

This is for exercising startup, readiness and the queue. **No real diagnosis is produced**: the worker accepts the
fake provider only with `TW_ENV=test`, and the fake fails every model call, so analyses end as "could not
complete". `LLM_PROVIDER=openai` refuses to start until the adapter is validated
([MODEL-ADAPTER.md](MODEL-ADAPTER.md)).

**4.1 A throwaway cluster** (Unix socket only, no TCP, no passwords; never use this for real data):

```bash
export TWDB=$HOME/.local/share/tracewise-dev && mkdir -p "$TWDB/sock"
```

```bash
initdb -D "$TWDB/data" -U postgres --auth=trust -E UTF8 --no-locale
```

```bash
pg_ctl -D "$TWDB/data" -o "-k $TWDB/sock -c listen_addresses=''" -l "$TWDB/pg.log" -w start
```

**4.2 Roles and database** from the reviewed template (creates `tracewise_owner`, `tracewise_app`,
`tracewise_system` and the `tracewise` database, all without passwords):

```bash
psql -h "$TWDB/sock" -U postgres -d postgres -v ON_ERROR_STOP=1 -f scripts/db/provision_roles.sql
```

**4.3 Migrations** run as the owner, through the migration CLI (`status` exits 4 when behind):

```bash
DATABASE_URL_MIGRATIONS="postgresql://tracewise_owner@/tracewise?host=$TWDB/sock" uv run python -m tracewise.db.migrate upgrade
```

**4.4 Web process:**

```bash
DATABASE_URL_SYSTEM="postgresql://tracewise_system@/tracewise?host=$TWDB/sock" GITHUB_WEBHOOK_SECRET=local-dev-secret-0000 uv run uvicorn --factory tracewise.web.asgi:create_runtime_app --host 127.0.0.1 --port 8000
```

Then `curl -s localhost:8000/readyz` should return `{"status":"ready"}`.

**4.5 Worker** (needs a GitHub App id and private key file only to start; with the fake provider it never calls a
model):

```bash
TW_ENV=test LLM_PROVIDER=fake DATABASE_URL="postgresql://tracewise_app@/tracewise?host=$TWDB/sock" DATABASE_URL_SYSTEM="postgresql://tracewise_system@/tracewise?host=$TWDB/sock" GITHUB_APP_ID=1 GITHUB_APP_PRIVATE_KEY_PATH=/path/to/dev-app.pem uv run python -m tracewise.worker --once
```

**4.6 Stop and clean up:**

```bash
pg_ctl -D "$TWDB/data" -m fast stop && rm -rf "$TWDB"
```

Production-shaped setup (role authentication, the secret store, process supervision) is in
[OPERATIONS.md](OPERATIONS.md) and [DEPLOYMENT-BLUEPRINT.md](DEPLOYMENT-BLUEPRINT.md).

## 5. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| DB tests are reported as **skipped** | `initdb` is not on `PATH`. On Debian/Ubuntu add `/usr/lib/postgresql/<version>/bin`. CI fails on any skip. |
| `web process refused to start: DATABASE_URL_SYSTEM … not the BYPASSRLS system role` | The system URL uses `tracewise_app` or the owner. Use `tracewise_system`. |
| `/readyz` says `schema_mismatch` | The database is not at this build's migration head; run §4.3. |
| `/readyz` says `wrong_database_role` | As above: the role behind `DATABASE_URL_SYSTEM` is wrong. |
| Worker exits 2 | A setting is missing, the two URLs use the same role, or the fake provider is configured without `TW_ENV=test`. The message names the setting, never its value. |
| `NETGUARD external connection attempts: 1` and a failed run | A test tried to reach a non-loopback host. Use the fakes in `tests/` instead. |
| Socket path errors | Unix socket paths are limited to about 107 bytes; use a short `$TWDB`. |

## 6. Glossary

| Term | Meaning |
|---|---|
| Installation | One GitHub App installation, which is one tenant (`installation_id`) |
| Tenant plane / system plane | `tracewise_app` (RLS, one tenant per transaction) and `tracewise_system` (BYPASSRLS: ingress, queue, recovery) |
| Pre-pass | The deterministic log analysis that runs before any model |
| Primary / cascade | An independent root error, and an error caused by an earlier one (e.g. a missing module after a failed install) |
| Surface | A place a report is published: Check Run, PR comment or commit comment |
| Inconclusive | The explicit outcome when the evidence does not support a diagnosis |
| Truth lock | `TRUTH.lock`, the hash that freezes the benchmark ground truth |
| Live tests | Tests marked `live`, which need an approved test organisation; never run by default |
