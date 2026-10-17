# Resource and Setup Checklist

Date: 2026-10-15. Prices marked [NEW-V] were verified on that date (see the [DECISION-REGISTER](DECISION-REGISTER.md) log). Everything else is marked [INF] or [UNK].

**Rules**

- **Never paste secrets into chat, tickets or docs.** Store them in a password manager, the local `.env` (git-ignored), or `fly secrets`.
- **Do not create paid or production resources before the stated gate.**

## 1. Inventory

| # | Resource | Why | Needed by | Setup checklist | Cost / tier | Secret storage | Can postpone? |
|---|---|---|---|---|---|---|---|
| R1 | GitHub account with 2FA | Owns Apps and the test org | Phase 0 | Enable 2FA; use a dedicated work account if possible | Free | Password manager | No |
| R2 | GitHub org `tracewise-bench` (test org) | Benchmark repos; dev and staging App installs; G-5 comparison | Phase 0 | Create org; create repos per benchmark case; public visibility is acceptable (synthetic code only) | Free | — | No |
| R3 | Fine-grained PAT ("lab token") | Phase 0 study and CLI. Unauthenticated log download returns 403 [NEW-V]. | Phase 0 | Public repositories read-only; expiry 30 days | Free; 5,000 req/h [NEW-V] | `.env` `GITHUB_TOKEN_LAB` or OS keychain | No |
| R4 | GitHub Copilot Pro (1 month) | G-5 native comparison ("Fix with Copilot" is Pro and above [R-03]) | Phase 0 (T0.05) | Subscribe on the personal account; test only in `tracewise-bench` | $10/mo per R-03 (verify at purchase) | — | Only if the user declines G-5 (OQ-03) |
| R5 | `tracewise-dev` GitHub App | Local integration | Phase 2 (T2.01) | §3 below | Free | Private key in `./secrets/dev-app.pem` (git-ignored, chmod 600); webhook secret in `.env` | No |
| R6 | Webhook tunnel (smee.io channel or Cloudflare Tunnel) | Deliver webhooks to localhost | Phase 2 | Create a channel; set it as the dev App webhook URL | Free | Channel URL is semi-secret (anyone with it can read deliveries) → use `cloudflared` for anything beyond fake repos | No |
| R7 | Fly.io account | Staging and production hosting (ADR-09) | Phase 6 (T6.04) | Create org; add a payment card; `fly auth login`; create apps `tracewise-staging` and `tracewise` | shared-cpu-1x 512 MB $3.69/mo, 1 GB $6.70/mo [NEW-V] | `fly secrets set` | Until Phase 6 |
| R8 | Neon account | Postgres for staging and prod | Phase 6 (local Docker before that) | Projects `tracewise-staging` and `tracewise-prod`; roles `tw_owner` and `tw_app`; Launch plan for prod | Free: 100 CU-h, 6 h history. Launch: $0.106/CU-h, $0.35/GB-mo, 7-day history [NEW-V]. Prod ≈ $20/mo. | `fly secrets` (`DATABASE_URL`, `DATABASE_URL_MIGRATIONS`) | Until Phase 6 |
| R9 | `tracewise-staging` GitHub App | Staging soak | Phase 6 | As in §3, with the staging webhook URL | Free | Fly secrets | Until Phase 6 |
| R10 | Domain plus DNS | Stable webhook URL, privacy page, App homepage | Phase 6 | Register; CNAME `app.` and `staging.` to Fly; Fly certs | ≈$10–15/yr [INF] | Registrar account in the password manager | Could use `*.fly.dev` for staging; production should use our own domain |
| R11 | Sentry account | Error tracking (ADR-12) | Phase 6 (T6.05) | Developer plan; 2 projects (web, worker) or 1 with environments | Free: 5k errors, 1 user [NEW-V] | `SENTRY_DSN` in Fly secrets (low sensitivity) | Yes (logs only) |
| R12 | `tracewise` production GitHub App ("Any account") | Partner installs | T6.10, after G-PILOT and G-PAY | As in §3, visibility "Any account" | Free | Fly secrets | Until the pilot |
| R13 | Anthropic API account and key | Optional LLM adjudicator (4B) | Phase 4B only | Create the org; set a **monthly spend limit** (e.g. $20); create a workspace "tracewise-eval" and later "tracewise-prod"; check Settings → Privacy for the data-retention setting [NEW-V] | Pay-as-you-go: Haiku 5.5 $0.10/$0.50; Sonnet 5.5 $2/$10 per MTok [NEW-V]. Eval budget ≈ $5–15 [INF]. | `.env` locally; Fly secrets | **Yes**: the MVP is deterministic |
| R14 | Object storage | Not needed (ADR-04) | — | — | — | — | Not required |
| R15 | Billing provider | Not needed for the first pilots (ADR-11) | — | Manual invoice | — | — | Not required |
| R16 | Benchmark data | 16 cases plus a 200-run labeled set | Phase 0 / T5.04 | TEST-AND-RELEASE-PLAN §2–3 | Free | Raw public logs stay local, never committed unredacted | No |
| R17 | Customer consent | Installing our App on partner orgs; using their failures in evaluation | T6.10 | Written pilot terms (T6.07 template): scope, data, retention, deletion, sub-processors, price | — | Signed copy in the password manager or Drive | No (for the pilot) |
| R18 | Third-party App installs for competitive testing (The Plumber, FailBrief, FixSense) | Optional broader benchmark (R-04 §5) | Optional | **Only with explicit user approval**, only on `tracewise-bench` | Free tiers | — | **Yes**: not required for G-0 (G-5 uses GitHub-native tools) |

## 2. Local development setup (after approval)

1. Install Python 3.12, `uv`, Docker, `flyctl` (later) and `gh`.
2. `git clone` the new `tracewise` repo, then `cp .env.example .env`, then fill in local values. Secrets come from the password manager.
3. `make up` starts Postgres 16 and PgBouncer. Then run `make migrate` and `make test`.
4. Start a tunnel: `npx smee-client -u $SMEE_URL -t http://localhost:8000/webhooks/github` (or `cloudflared`).
5. `make dev-web` and `make dev-worker`.
6. Push a failing commit in `tracewise-bench/<case>` and watch the logs.

## 3. GitHub App registration checklist (dev, staging, prod)

1. Settings → Developer settings → GitHub Apps → New GitHub App. **Register under the test org for dev and staging.**
2. **Name:** `tracewise-dev`, `tracewise-staging`, or `tracewise`.
3. **Homepage:** the privacy or landing URL.
4. **Callback URL:** empty. **Request user authorization during installation:** unchecked.
5. **Setup URL:** optional (prod).
6. **Webhook:** active. **URL:** the tunnel (dev) or `https://<env-host>/webhooks/github`. **Secret:** generate with `python -c "import secrets;print(secrets.token_urlsafe(48))"` and store it immediately. **SSL verification:** enabled.
7. **Repository permissions:**

   | Permission | Level |
   |---|---|
   | Actions | Read-only |
   | Checks | Read and write |
   | Contents | Read-only |
   | Metadata | Read-only (automatic) |
   | Everything else | No access |

8. **Organization and account permissions:** none.
9. **Subscribe to events:** ☑ Workflow run, nothing else. Installation events arrive by default [NEW-V].
10. **Where can it be installed:** "Only on this account" (dev, staging) or "Any account" (prod).
11. Create the App. Record the **App ID** (non-secret) in `docs/github-apps.md`. Generate a **private key** (`.pem`) and store it per R5, R9 or R12. Never commit it.
12. Install the App on selected repos only. Record the **installation ID** (visible in the installation URL or via `GET /app/installations`) for testing. The service discovers installation IDs from webhooks; no configuration is needed.
13. **Verify:** `GET /app` with the JWT returns exactly these permissions and events.

## 4. Infrastructure setup (Phase 6)

1. **Neon:**
   - Create the prod project (region near Fly's primary region).
   - Create roles: `tw_owner` (owner) and `tw_app` (login, no ownership).
   - Note both direct and pooled connection strings.
2. **Fly:**
   - `fly launch --no-deploy`.
   - In `fly.toml`: `[processes] web="uvicorn tracewise.api.app:app --host 0.0.0.0 --port 8080"`, `worker="tracewise worker"`, and `[deploy] release_command="tracewise db upgrade"`.
   - VM sizes per Plan §13.1.
   - `min_machines_running=1` for `web` in prod.
3. **Secrets:** `fly secrets set` for every *secret* row in §6.
4. **DNS and certs:** `fly certs add app.<domain>`.
5. **Deploy pipeline:** GitHub Actions on a tag, using `FLY_API_TOKEN` as a repo secret with deploy-only scope.

## 5. Cost estimate summary

Details are in Plan §14.

| Phase | One-off | Monthly |
|---|---|---|
| Phase 0 | Copilot Pro ≈ $10; domain (optional) | $0 |
| Phases 1–5 (local) | — | $0 |
| Staging and prod (Phase 6) | Domain ≈ $12/yr | ≈ $36–40 (Fly ≈ $10.4 prod + staging ≈ $5–8 + Neon ≈ $20) |
| LLM (optional) | Eval ≈ $5–15 | Pilot usage ≈ $1–20 at blended $0.007–0.021 per failed run |

## 6. `.env.example` specification

| Variable | Purpose | Required | Secret | Example / default |
|---|---|---|---|---|
| `TW_ENV` | `local` / `staging` / `production` | yes | no | `local` |
| `TW_LOG_LEVEL` | Log level | no | no | `INFO` |
| `TW_PUBLIC_BASE_URL` | Base URL for links and the setup page | prod | no | `https://app.example.com` |
| `DATABASE_URL` | Runtime DB URL (`tw_app` role) | yes | **yes** | `postgresql+asyncpg://tw_app:CHANGE_ME@localhost:5432/tracewise` |
| `DATABASE_URL_MIGRATIONS` | Migration URL (`tw_owner` role) | yes | **yes** | `postgresql+asyncpg://tw_owner:CHANGE_ME@localhost:5432/tracewise` |
| `DB_STATEMENT_CACHE_SIZE` | Set to 0 behind PgBouncer | no | no | `0` |
| `GITHUB_APP_ID` | App ID | yes (phase ≥2) | no | `123456` (placeholder) |
| `GITHUB_APP_SLUG` | App slug, for links | yes | no | `tracewise-dev` |
| `GITHUB_APP_PRIVATE_KEY_PATH` *or* `GITHUB_APP_PRIVATE_KEY` | PEM path (local) or contents (Fly secret) | yes | **yes** | `./secrets/dev-app.pem` |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret | yes | **yes** | `CHANGE_ME` |
| `GITHUB_WEBHOOK_SECRET_PREVIOUS` | Accepted during rotation | no | **yes** | empty |
| `GITHUB_API_URL` | API base | no | no | `https://api.github.com` |
| `GITHUB_TOKEN_LAB` | PAT for CLI lab/analyze on public repos | CLI only | **yes** | empty |
| `WORKER_CONCURRENCY` | Jobs in parallel per worker | no | no | `4` |
| `WORKER_LEASE_SECONDS` | Job lease | no | no | `300` |
| `JOB_TIMEOUT_SECONDS` | Per-job hard timeout | no | no | `180` |
| `LOG_MAX_BYTES` | Per-job-log download cap | no | no | `52428800` |
| `LOOKBACK_RUNS` | Lane history limit | no | no | `100` |
| `LOOKBACK_DAYS` | Lane history limit | no | no | `90` |
| `MAX_INTERMEDIATE_LOGS` | First-bad scan budget | no | no | `5` |
| `PURGE_GRACE_DAYS` | Delay before purging an uninstalled tenant | no | no | `7` |
| `RECONCILE_INTERVAL_MINUTES` | Delivery reconciliation cadence | no | no | `15` |
| `REGISTRY_LOOKUPS_ENABLED` | PyPI/npm context lookups | no | no | `false` |
| `LLM_ENABLED` | Master switch | no | no | `false` |
| `LLM_PROVIDER` | `anthropic` | if LLM | no | `anthropic` |
| `ANTHROPIC_API_KEY` | API key | if LLM | **yes** | empty |
| `LLM_MODEL_DEFAULT` | Chosen by eval (T4B.04) | if LLM | no | `claude-haiku-5-5` (candidate, pending eval) |
| `LLM_MODEL_ESCALATION` | For conflicts, if the eval shows a benefit | no | no | `claude-sonnet-5-5` (candidate) |
| `LLM_MAX_COST_PER_ANALYSIS_USD` | Per-analysis guard | no | no | `0.30` |
| `LLM_DAILY_BUDGET_USD` | Alert or auto-disable threshold | no | no | `5` |
| `SENTRY_DSN` | Error tracking | staging/prod | low | empty |
| `SENTRY_TRACES_SAMPLE_RATE` | Performance sampling | no | no | `0` |

The file contains placeholders only. **No real values are ever committed.** CI uses dummy values and a test RSA key generated at test time.

## 7. Prerequisites by milestone

| Milestone | Must exist |
|---|---|
| Start Phase 0 | R1, R2, R3 (+ R4 if G-5 is approved) |
| Start Phase 2 | R5, R6 |
| Start Phase 4B | R13 (with a spend limit) |
| Start Phase 6 | R7, R8, R9, R10, R11 |
| First external install | R12, R17, and G-PILOT passed |
