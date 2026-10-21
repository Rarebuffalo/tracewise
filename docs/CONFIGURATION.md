# Configuration reference

Tracewise reads its settings from environment variables (`src/tracewise/config.py`, pydantic-settings).
[`.env.example`](../.env.example) lists them with placeholders. **Never commit real values**: `.env`, `.env.*`
(except the example), `*.pem` and `*.key` are git-ignored.

Validation errors name the setting, never its value. Secrets are `SecretStr` and are registered with the log
scrubber.

## Settings

| Variable | Default | Used by | Meaning and constraints |
|---|---|---|---|
| `TW_ENV` | `local` | all | `local`, `test`, `staging` or `prod`. `test` is the only environment that accepts the fake provider. |
| `DATABASE_URL` | — | worker | **Tenant plane**: role `tracewise_app`, subject to row-level security. Must be a different role from the system URL; the worker refuses otherwise. |
| `DATABASE_URL_SYSTEM` | — | web, worker, `ops`, `recovery`, `retention` | **System plane**: role `tracewise_system` (BYPASSRLS, not owner, not superuser). The web process and `ops` refuse any other role. |
| `DATABASE_URL_MIGRATIONS` | — | operators | The owner role for migrations. Migrations are run explicitly (`python -m tracewise.db.migrate upgrade`; programmatic: `tracewise.db.migrate.upgrade`); no process migrates on startup. |
| `GITHUB_WEBHOOK_SECRET` | — | web | The webhook secret from your GitHub App; at least 16 characters. |
| `GITHUB_APP_ID` | — | worker, `recovery` | Your GitHub App's id. |
| `GITHUB_APP_PRIVATE_KEY_PATH` | — | worker, `recovery` | Path to the App's RSA private key (PEM, mode 0600). The key is never stored in an environment variable. |
| `LLM_PROVIDER` | `fake` | worker | `fake` (test only) or `openai`. **`openai` currently refuses to start**: the adapter is implemented offline but not yet validated ([MODEL-ADAPTER.md](MODEL-ADAPTER.md)). |
| `OPENAI_API_KEY` | — | worker | Required by `openai`; never logged. |
| `LLM_MODEL` | — | worker | Model id; no default, no fallback. |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | unset | worker | USD per million tokens for the cost record. Unset means cost is recorded as unpriced. |
| `INVESTIGATION_MAX_TOOL_CALLS` | `12` | worker | 1–12 (the spec's ceiling). |
| `INVESTIGATION_TIMEOUT_S` | `120` | worker | 1–120 seconds. |
| `LOG_MAX_BYTES_PER_JOB` | `2097152` (2 MB) | worker | Per-job log retention budget; logs beyond it are flagged as truncated. |
| `REPORT_MAX_CHARS` | `60000` | worker | Rendered report cap (≥1000). Provisional until GitHub's limits are measured live. |
| `ANALYSIS_QUOTA_MONTHLY` | unset | worker | T-703 / FS-QTA-1: analyses per installation per UTC calendar month (≥1). Unset means no quota. Over quota a run is not analysed, and one neutral "Analysis quota reached" Check Run is published per repository per day, never a comment. The value is an owner decision. |

## Which process needs what

| Process | Required |
|---|---|
| Web (`uvicorn --factory tracewise.web.asgi:create_runtime_app`) | `DATABASE_URL_SYSTEM`, `GITHUB_WEBHOOK_SECRET` |
| Worker (`python -m tracewise.worker`) | `DATABASE_URL`, `DATABASE_URL_SYSTEM`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `LLM_PROVIDER` (+ its settings) |
| `python -m tracewise.ops report\|alerts` | `DATABASE_URL_SYSTEM` |
| `python -m tracewise.recovery deliveries\|runs\|both` | `DATABASE_URL_SYSTEM`, the App id and key |
| `python -m tracewise.retention` | `DATABASE_URL_SYSTEM` |
| `python -m tracewise.preflight [--process web\|worker\|all] [--database]` | Checks the above without starting anything: role separation (including `DATABASE_URL_MIGRATIONS`), webhook secret length and placeholders, App id, key file mode 0600, RSA format and location outside any git working tree, provider and `TW_ENV`. Prints check names and fixed explanations, never values. Exit 0 pass, 2 a check failed, 3 invalid settings. No network; `--database` is read-only |

Exit codes, signals and the full startup checks are in [OPERATIONS.md](OPERATIONS.md) §1a. The environment
inventory per deployment component is in [DEPLOYMENT-BLUEPRINT.md](DEPLOYMENT-BLUEPRINT.md) §5.
