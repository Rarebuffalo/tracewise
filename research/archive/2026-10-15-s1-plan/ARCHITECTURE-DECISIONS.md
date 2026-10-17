# Architecture Decisions (ADRs)

Date: 2026-10-15. Status of every ADR: **Proposed**. Each becomes Accepted when the user approves [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md).

Labels: [NEW-V] verified 2026-10-15 (see the [DECISION-REGISTER](DECISION-REGISTER.md) verification log); [INF] inference.

---

## ADR-01 — Python 3.12 + FastAPI + async SQLAlchemy, single package (modular monolith)

- **Decision:**
  - One package, `tracewise`, deployed as one image with `web` and `worker` processes.
  - Libraries: FastAPI, uvicorn, httpx, SQLAlchemy 2 (async) + asyncpg, Alembic, Pydantic v2, structlog, PyJWT[crypto], Typer (CLI). Managed by `uv`.
- **Alternatives:**
  - Django: heavier, and its ORM is sync-first.
  - Litestar: less team familiarity.
  - Node/TypeScript backend: splits the team's strength.
  - Microservices: no requirement.
- **Pros:**
  - Matches the developer's FastAPI experience (SecureLens).
  - Async suits I/O-bound GitHub calls.
  - The same engine is reusable from the CLI.
- **Cons:** mypy-strict with SQLAlchemy needs care.
- **Cost:** none.
- **Migration:** modules are organized by boundary (`github/`, `engine/`, `publish/`), so a later split is possible but not planned.

## ADR-02 — GitHub App as the delivery mechanism; CLI for validation; no GitHub Action

- **Decision:** GitHub App (webhook-driven). A CLI (`tracewise analyze/lab/bench`) uses the same engine with a personal token, for Phase 0 and benchmarks.

| Alternative | Problem |
|---|---|
| **GitHub Action** (runs in the customer's CI) | Needs a workflow change in every repo. Runs only when the job itself runs, so it cannot see across runs without an extra API token. Can't post after a cancelled or timed-out job reliably. Customers pay the runner minutes. |
| **CLI only** | No automatic trigger |

- **Pros:**
  - Zero workflow changes.
  - Check Runs can only be created by Apps [NEW-V].
  - Central history.
- **Cons:**
  - App install trust barrier [R-05 risk 4].
  - We hold the infrastructure.
- **Migration:** an Action wrapper around the CLI could later serve teams that refuse third-party Apps (OQ-01 relates).

## ADR-03 — Postgres job table instead of Redis/arq

- **Decision:**
  - A `job` table with `dedupe_key UNIQUE`, `run_after` and lease (`locked_until`).
  - Claim with `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1`.
  - Enqueue **in the same transaction** as the webhook-delivery insert.
  - Optional `LISTEN/NOTIFY` to reduce polling latency, with a 2 s poll fallback.

| Alternative | Problem |
|---|---|
| arq + Redis [R-06] | Extra service, plus a dual write (DB commit, then Redis push) that can lose a job if the process dies between them, unless we add an outbox |
| Procrastinate (Postgres-based task library) | A viable library alternative. Rejected for now to keep behavior fully visible (~150 lines). Revisit if job features grow. |
| Celery | Heavy |

- **Pros:**
  - Atomic enqueue.
  - One datastore.
  - Easy to inspect with SQL.
  - Retries and dead letters are just columns.
- **Cons:**
  - Polling load. Mitigated by NOTIFY and an index on `(status, run_after)`.
  - Throughput limits are far above pilot volume [INF].
- **Cost:** saves a Redis service (~$0–10/mo).
- **Migration:** handlers are queue-agnostic. Swapping in arq or Procrastinate later only changes `jobs/queue.py`.

## ADR-04 — No object storage; raw logs are transient

- **Decision:**
  - Raw logs are streamed into worker memory, cut down to the relevant sections, then discarded at job end.
  - Only redacted ≤2 KB excerpts with locators are persisted.
- **Alternative:** R2/S3 with a 7-day TTL [R-02, R-06].
- **Pros:**
  - Less customer data held.
  - Simpler privacy story.
  - No extra vendor.
- **Cons:** re-analysis must re-download logs. That is acceptable while GitHub retains them (90 days by default [NEW-V]).
- **Migration:** add a `LogStore` interface if a partner asks for longer re-analysis windows.

## ADR-05 — Tenant = GitHub installation; app-layer scoping now, RLS before the external pilot

- **Decision:**
  - `installation_id` on all tenant rows.
  - Repository layer methods require it.
  - Migration `0004_rls`:
    - `ENABLE` + `FORCE ROW LEVEL SECURITY`;
    - policy `installation_id = current_setting('app.installation_id')::bigint`, which **errors when unset** (fail closed);
    - runtime role `tw_app` (non-owner, `NOBYPASSRLS`);
    - context set per transaction with `set_config('app.installation_id', $1, true)`.
  - System tables (`job`, `webhook_delivery`, `installation`, `audit_event`) are not under RLS and are accessed only via `SystemRepository`.
- **Alternatives:**
  - Schema-per-tenant: heavy migrations.
  - DB-per-tenant: cost.
  - App-layer only: one bug away from a leak.
- **Pooling:** transaction-local `set_config` works with PgBouncer transaction mode. With asyncpg on Neon's pooled endpoint, set `statement_cache_size=0`, or use the direct endpoint for the worker. Verify in T1.04/T6.01.
- **Cons:** every tenant query must run inside an explicit transaction. Enforced by a session helper.

## ADR-06 — Output via Check Run only, conclusion `neutral`

- **Decision:**
  - One Check Run named "Tracewise" per (head_sha, run_id), with `external_id = run_id`.
  - Always `neutral`.
  - No PR comments.
- **Alternatives:**
  - PR comment (needs `pull_requests:write` or `issues:write`; noise complaints [R-03 §6]).
  - Commit comment (needs `contents:read` only per the GitHub permissions table [NEW-V], but it is noisy and has no update semantics).
  - Slack.
- **Pros:**
  - Fewest write scopes.
  - Updatable in place.
  - Visible on PRs and commits.
  - Never blocks merges.
- **Cons:**
  - Less prominent than a comment.
  - Fork-PR behavior is [UNK] (verify in T2.07).
- **Migration:** a PR-comment mode can be added later behind an opt-in permission upgrade (GitHub prompts admins to accept new permissions).

## ADR-07 — No dashboard in the MVP or the first pilot

- **Decision:**
  - The GitHub Check Run is the user interface.
  - Admin work is done via the CLI over `fly ssh console`.
  - A static `/privacy` page.
- **Alternative:** Next.js dashboard plus GitHub OAuth [R-06], about 4–5 dev-days, adding auth, session and RBAC surface.
- **Revisit if:** design partners need cross-run history views or settings UI (OQ-05).

## ADR-08 — LLM optional, off in the MVP; model chosen by eval

- **Decision:**
  - Deterministic engine first.
  - In the pilot, an optional `llm/adjudicate.py` with **no tools**, structured outputs (`output_config.format`), candidate and evidence references by ID, ≤2 calls, and a cost guard.
  - Candidate models: Claude Haiku 5.5 ($0.10/$0.50 per MTok) and Claude Sonnet 5.5 ($2/$10) [NEW-V]. Opus 5.5 ($4/$20) is only for escalation if measured to help.
  - Selection is by the eval in Plan §8.8, not by recency.
- **Alternatives:**
  - Agentic loop with file tools (The Plumber's pattern): latency, cost and injection surface; commoditized by Copilot.
  - Other providers: possible behind the `llm/client.py` interface.
- **Data:** Anthropic deletes API inputs and outputs within 30 days by default; zero data retention (ZDR) is by agreement [NEW-V]. Avoid "Covered Models" that require 30-day retention (e.g. Fable 5.1) [NEW-V].

## ADR-09 — Hosting: Fly.io + Neon Postgres

- **Decision:**
  - Fly app with `[processes] web/worker`: shared-cpu-1x 512 MB web ($3.69/mo) and 1 GB worker ($6.70/mo) [NEW-V].
  - Neon Launch Postgres: pay-as-you-go $0.106/CU-h, $0.35/GB-mo, 7-day history [NEW-V]. About $20/mo always-on at 0.25 CU.

| Alternative | Why not chosen |
|---|---|
| Neon Free | 100 CU-h/project is insufficient for an always-polling worker (0.25 CU × 730 h ≈ 182 CU-h) [NEW-V] |
| Fly Managed Postgres | From $38/mo [NEW-V] |
| Render | Paid prices not retrievable today; free Postgres expires after 30 days with no backups [NEW-V] |
| Railway, single VPS with docker-compose | Cheaper but more ops |

- **Migration:** a standard Postgres URL and a Docker image make moving hosts trivial.

## ADR-10 — Authentication

- **Decision:**
  - Inbound: webhook HMAC only.
  - Outbound: App JWT → installation tokens scoped to the repository and the 4 permissions [NEW-V].
  - No end-user auth: there are no user endpoints.
  - Admin access is through Fly org membership (SSH).
- **Revisit:** when a dashboard exists, use GitHub OAuth (user-to-server) and map users to installations via `GET /user/installations`.

## ADR-11 — Billing: manual invoices for pilots

- **Decision:**
  - Invoice manually (e.g. a Stripe invoice or a bank invoice).
  - Usage comes from `admin usage --month`.
  - No billing webhooks.
- **Alternative:** Paddle or Lemon Squeezy as merchant of record (VAT handling) once there are more than 5 customers or self-serve is needed.

## ADR-12 — Observability: structlog JSON + Sentry Developer (free)

- **Decision:**
  - Correlation IDs (`delivery_id` → `job_id` → `analysis_id`).
  - Per-stage timings stored with each analysis.
  - Sentry free plan (5k errors, 1 user [NEW-V]) with aggressive scrubbing.
- **Alternatives:** OpenTelemetry → Grafana Cloud [R-06], deferred until multiple services or volume justify it.

## ADR-13 — Attribution policy: deterministic rules with invariants INV-1…INV-5

- **Decision:** the rules and precedence of Plan §7.
- **Alternatives:**
  - LLM-first diagnosis.
  - A probabilistic model.

  Both were rejected: the training data does not exist, and false blame is the critical failure mode.
- **Consequence:** coverage is lower (more `UNATTRIBUTED`), traded for lower false blame. G-INT requires ≥50% coverage on real data.

---

## Rejected alternatives (summary)

| Rejected | Where proposed | Why |
|---|---|---|
| Redis/arq queue | R-06 | ADR-03 |
| R2 log storage | R-02, R-06 | ADR-04 |
| Next.js dashboard, OAuth | R-06 | ADR-07 |
| `pull_requests:write` and PR comments | R-06 | ADR-06 |
| Backfilling 50 runs on install | R-06 | On-demand history |
| Numeric confidence scores | R-02 | Not calibrated (Plan §8.7) |
| Patch generation, fix PRs, sandbox verification | R-02 (partly), R-05 E | Out of positioning; risk |
| Vercel, Upstash, Grafana Cloud | R-06 | No component needs them |

## Unresolved architecture questions

Tracked with decision dates in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md).

| ID | Question | Resolved in |
|---|---|---|
| U-1 | Can our App create a Check Run on a fork-PR head SHA in the base repo? | T2.07 |
| U-2 | Exact GitHub log section markers for runner header and step groups | T3.01, from ≥20 real logs |
| U-3 | Exact paths and parameters for the "list/redeliver app webhook deliveries" endpoints; GitHub-side delivery retention | T2.06 |
| U-4 | Whether the Check Runs "list for a ref" endpoint filters by `check_name` (used for idempotency) | T5.02 |
| U-5 | Practical `output.summary` size limit | T5.01 test with 70 KB |
| U-6 | asyncpg plus Neon pooled endpoint behavior | T1.04 |
| U-7 | Whether Haiku 5.5 supports structured outputs and low-effort settings as needed | T4B.01 |
