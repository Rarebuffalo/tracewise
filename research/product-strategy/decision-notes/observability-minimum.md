# Observability minimum for self-hosted Tracewise

- **Date:** 2026-11-01
- **Status:** Proposal; nothing implemented. Read-only analysis of the working tree. No code, test or config was changed.
- **Scope:** what an operator can see today, the gaps, a minimum metrics interface that fits the current
  architecture (JSON logs + `python -m tracewise.ops`), candidate offline tasks, and alert routing for self-hosters.

## 1. What exists today (building blocks)

- **Structured events.** `observe.event()` emits one record with a stable dotted name (`observe.py:32,89-98`). Field
  names containing a denied word (token, secret, url, body, prompt, text, message, ...) are dropped (`observe.py:27-31,54-55`).
  Values must be scalars or short lists and are truncated to 200 chars and 20 items (`observe.py:33-34,58-86`). Correlation
  ids (`delivery_id, job_id, installation_id, repo_id, run_id, attempt`) are bound per context (`observe.py:25,43-51`).
  A failure to emit is counted in a process-local `dropped_events` and is never raised (`observe.py:36,97-98`).
- **Log hygiene.** Every record passes `SecretFilter`. It scrubs registered secrets, token shapes, URL queries, auth
  headers, bearer tokens and cookies (`logging.py:42-94`) at any nesting depth (`logging.py:84-94`). `JsonFormatter`
  writes one JSON line to stderr (`logging.py:97-112,118-127`). httpx, httpcore, urllib3 and alembic are held at
  WARNING (`logging.py:39,144-147`).
- **`ops report`** (system plane, aggregates only, no per-tenant breakdown by design: `ops.py:8-10`) covers the window
  [default 24 h] and reports:
  - analyses by status;
  - analyze jobs by status (jobs **created** in the window);
  - retried jobs;
  - end-to-end p50/p95 and the number within the 600 s deadline;
  - processing and model ms;
  - tokens, cost (priced/unpriced) and publications by `surface:state`.

  Sources: `ops.py:68-133`. Exit 0.
- **`ops alerts`** has one rule: `failure_rate = (dead + could_not_complete) / finished analyze jobs` over 1 h, with
  threshold 0.2 and min sample 10, both **provisional**. When it fires it logs `alert.failure_rate` and exits 2
  (`ops.py:36-49,136-175,216-218`). An unreachable database or the wrong role gives exit 1 and `ops.failed`
  (`ops.py:199-206`).
- **Probes.** `/healthz` (no DB) and `/readyz` (DB, role, schema) are in `web/health.py:14-42`. The staging Caddyfile
  proxies only `/webhooks/github /healthz /readyz` and answers 404 for everything else (`deploy/staging/Caddyfile:5-11`).
- **Scheduling.** Nothing is scheduled in code (`ops.py:5-6`, `recovery.py:408`). The staging README proposes cron,
  including `ops alerts` every 10 min (`deploy/staging/README.md:95-104`). Alert routing is open (`docs/OPERATIONS.md:12,181-187`).
- **Dependencies.** There is no metrics library: `pyproject.toml:6-18` lists alembic, fastapi, httpx, psycopg(-pool),
  pydantic(-settings), pyjwt, pyyaml, sqlalchemy and uvicorn. `prometheus_client` is absent.

## 2. Inventory against the requested signals

Legend: **L** = available from logs; **DB** = available from `ops report` or `ops alerts` today; **DB\*** = present in
tables but not surfaced by `ops`; **—** = not available.

| Signal | Status | Evidence |
|---|---|---|
| Webhook acceptance/rejection | **L** for every path: `webhook.too_large`, `.not_configured`, `.signature_rejected`, `.bad_headers`, `.payload_rejected{reason}`, `.db_unavailable`, `.ingested{outcome,job_id}`, `.recorded`, `.lifecycle`, `.ping`. **DB\***: `webhook_delivery.outcome`/`received_at` exist only for deliveries that passed the signature check and the headers check. Signature, size, header and 503 failures are never persisted. `ops` does not read `webhook_delivery`. | `web/webhooks.py:75-131,143`; `migrations/0001_initial.py:37-46`; `0003_lifecycle_outcomes.py:20-22` |
| Queue depth and age | **—** in `ops`. `ops report` counts jobs *created in the window* by status (`ops.py:79-86`), so an old stuck job is invisible. **DB\***: `queue.counts()` exists but nothing calls it (`jobs/queue.py:276-277`). There is no oldest-ready age. | `jobs/queue.py:161-168` (`run_after` ordering) |
| Processing duration | **DB**: e2e, processing and model p50/p95 (`ops.py:91-122`). **L**: `job.processed{duration_ms}` (`jobs/worker.py:85`), `analysis.finished{stage_ms}` (`handlers/analyze.py:372`). | |
| Investigation timeout rate | **L** only: the `"investigation finished"` line with `outcome` ∈ `provider_timeout`/`budget_exhausted` (`investigate/loop.py:187-188,207-208,217-218`). This line has no `event` name (plain `log.info` with `extra`). **DB\***: `analysis.diagnosis->>'inconclusive_reason'`, until the 90-day nulling. Jobs past the 10-min deadline that never ran are set to `dead` **silently** (no event) at claim time. | `jobs/queue.py:157-160`; `contracts.py:292` |
| Provider errors (incl. `ProviderRefusal`, `ProviderTruncated`) | The kinds exist (`investigate/provider.py:80-93`). All of them collapse to `provider_failed` (`loop.py:219-222`). The kind is only in an unnamed log line, `"provider step failed" {kind}` (`loop.py:221`). Unexpected adapter exceptions are logged without a kind (`loop.py:223-227`). **DB**: they surface only as `could_not_complete` after the final retry (`handlers/analyze.py:68,330-333`) and count toward the failure rate. **L**: `analysis.diagnosed{inconclusive_reason}` (`analyze.py:314-329`) and `job.retry_scheduled{error_type=RetryableError}` (`jobs/worker.py:124-130`). The refusal/truncation split is **not** persisted. | |
| GitHub API failures and rate limits | **L**: a `"github call"` line for each response (`endpoint, status, request_id, ratelimit_remaining`). It has no `event` name (`github/client.py:372-384`). Inline rate-limit waits and transport-error retries emit nothing distinct (`client.py:255-262,282-288`). A long wait raises `GitHubRetryable` and shows up as `job.retry_scheduled{error_type}`. **DB\***: bounded and redacted `job.last_error` text (`jobs/queue.py:213`). Recovery: `stopped="rate_limited"` in the summary and in `recovery.pass_finished` (`recovery.py:320-324,396-405`). | |
| DB pool saturation | **—**. Pools are `max_size=10, timeout=3 s` (`db/session.py:29-56`), web 1 pool (`web/asgi.py:49`), worker 2 pools (`worker.py:97-98`). `PoolTimeout` and `OperationalError` both become `DatabaseUnavailable` (`session.py:75-78`). Events carry only `error_type`, so saturation looks the same as an outage (`webhook.db_unavailable`, `worker.db_unavailable`, `job.record_failed`). `psycopg_pool` exposes `get_stats()`, which nothing calls. | `.venv/.../psycopg_pool/base.py:154` |
| Recovery attempts | **L**: `recovery.redelivery_requested{status}`, `.run_ingested{outcome}`, `.repo_failed`, `.locked`, `.pass_finished{scanned, redelivered, enqueued, errors, stopped, completed,...}`, `.failed` (`recovery.py:89,98,257-265,327-348,379-405,441`). The JSON summary goes to stdout and the exit code is 1 when the pass is incomplete (`recovery.py:444-445`). **DB\***: `redelivery_request.attempts/last_status`, `recovery_checkpoint.updated_at` (`0004_recovery.py:21-34`). The high-water mark moves only on a complete pass that saw at least one delivery (`recovery.py:270-275`), so its age is **not** a reliable "last success" signal. | |
| Invalid evidence / incomplete reports | **L**: `analysis.diagnosed{evidence_status, abstained, validation_flags, validation_flag_count}` (`analyze.py:314-329`), `publication.result{surface,state}` (`analyze.py:384`), `publication.permission_refused` (`github/publish.py:223`), `analysis.ops_record_failed` (`analyze.py:430`). **DB**: `analyses.without_ops_record`, `publications{surface:state}` incl. `failed`/`unpublished_permission` (`ops.py:106-119,132`; `0002_publication_state.py:28`). Validation flags are not aggregated. | |
| Per-tenant usage | **DB\*** per installation: `count_monthly_analyses()` for quota (`db/repositories.py:232-244`). `usage_event` exists but `add_usage()` has no caller (`repositories.py:500-504`; grep). **L**: `analysis.quota_exceeded{quota, used}` (`analyze.py:267`). `ops` deliberately omits per-tenant data (`ops.py:8-9`). | |
| Secret-safe structured logs | **Yes**: deny-list, truncation, scrubber and quieted URL loggers (above). Residual risk: redaction is pattern-based (`docs/DATA-INVENTORY.md:67`). Three hot lines bypass `event()` and have no stable `event` key: loop.py:188, loop.py:221, client.py:374. They are still scrubbed by the filter, but the field deny-list is not applied to them. | |

## 3. Gaps (ordered by operational risk)

1. **No backlog visibility.** No queue depth, no oldest-ready age, and no "running with an expired lease" count. If the
   worker is down, nothing fires: the failure rate needs *finished* jobs (`ops.py:147-151`), so a dead worker reads as
   `insufficient_data`.
2. **Silent deadline drops.** Never-started jobs past the deadline become `dead` with no event (`queue.py:157-160`).
   They do count in the failure rate.
3. **DB saturation is indistinguishable from an outage**, and there are no pool stats.
4. **Provider error kind is lost.** A refusal, a truncation and an outage all read as `provider_failed`. A spike of
   refusals or truncations, which points to a prompt or output-cap problem, cannot be told from a provider outage.
5. **Webhook rejections are log-only.** A spike in signature failures (wrong secret after rotation, or probing) has no
   DB counter. This is deliberate: unauthenticated requests should not cause DB writes.
6. **Recovery freshness** depends on cron exit codes. There is no durable "last completed pass" timestamp.
7. **Rate limiting** is visible only as `ratelimit_remaining` on unnamed lines and as retry error types.
8. `observe.dropped_events` is never reported. `usage_event` is never written.

## 4. Minimum metrics interface (proposal)

**Principle.** Derive counters and gauges from Postgres in `ops report` and `ops alerts` (stateless, multi-process
correct, survives restarts, no new dependency, system plane only). Add a few named log events for what the DB cannot
see. Labels are fixed enums only: no repo names, no log text, no `last_error` text, no prompts, no provider
reasoning or replay state. `installation_id` is used only where noted.

### 4.1 DB-derived (new `ops report` sections; ✱ = also an `ops alerts` rule)

| Metric | Type | Labels | Source | Alert proposal (rationale) |
|---|---|---|---|---|
| `queue_depth` | gauge | `status` ∈ queued, retry_wait, running | `queue.counts()`, now-based, not windowed | — (context) |
| `queue_oldest_ready_age_s` ✱ | gauge | — | `now() - min(run_after)` where status ∈ (queued, retry_wait) and `run_after <= now()` | **> 600 s** warn. Equals `JOB_DEADLINE_S` (`queue.py:35`). Past it, unstarted jobs are dropped. |
| `jobs_lease_expired_unreaped` ✱ | gauge | — | running and `locked_until < now()` (only reaped at the next claim, `queue.py:124-145,154`) | **> 0 at two consecutive checks** (≥10 min apart) = no live worker is claiming. Critical. |
| `jobs_dead` ✱ | counter/window | `reason_class` ∈ permanent, attempts_exhausted, deadline_exceeded, lease_expired, other | `job` dead, `finished_at` in window; the class comes from the fixed `last_error` prefixes (`queue.py:131,158,224`). The text itself is never emitted. | **> 0 in 1 h** warn while pilot volume is low. Each dead job is a run the user got no answer for. |
| `failure_rate` ✱ (exists) | ratio | — | `ops.py:136-175` | Keep 0.2 / n≥10 / 1 h, provisional. |
| `webhook_deliveries` | counter/window | `outcome` (the 8 CHECK values) | `webhook_delivery.received_at` | Informational. Optionally warn when `rejected` ≥ 5 in 1 h (payload-schema drift). |
| `investigation_outcomes` | counter/window | `inconclusive_reason` (fixed codes, `contracts.py:292`) | `analysis.diagnosis->>'inconclusive_reason'` (null after 90 d; fine for 1–24 h windows) | ✱ `provider_timeout`+`provider_failed`+`budget_exhausted` ≥ **30 %** of investigated analyses, n ≥ 5, 1 h. Points to a provider outage or a budget misfit. |
| `validation_flags` | counter/window | `flag` (fixed code pattern, `contracts.py:293`), top 20 | the same JSON | Informational (quality drift). |
| `recovery_last_completed_age_s` ✱ | gauge | `kind` ∈ deliveries, sweep | **needs** a new checkpoint key written on every completed pass (task T3) | **> 2× cadence + 5 min** (deliveries > 35 min, sweep > 2 h 05 m) ≈ "incomplete twice in a row". |
| `analyses_month_by_installation` | gauge | `installation_id` (opt-in flag only) | `count_monthly_analyses` | — Quota nearing (≥ 90 %) is informational. **Owner decision:** `ops.py:8-9` currently forbids a per-tenant breakdown. |
| `database_reachable` ✱ | state | — | `ops` exit 1 with `database_unavailable` (`ops.py:203-206`) | Any occurrence is critical. Route the cron exit code, not a metric. |

### 4.2 Log events (process-local facts the DB cannot hold)

| Event | Fields (all pass `sanitize`) | Why |
|---|---|---|
| `investigation.provider_failed` | `kind` ∈ ProviderError, ProviderRefusal, ProviderTruncated, ProviderTimeout, unexpected; `provider`, `model` | Restores the kind split. Replaces the unnamed lines at loop.py:221,226. |
| `investigation.finished` | `outcome, tool_calls, rejected` | Gives loop.py:188 a stable name. |
| `github.rate_limited` | `endpoint` (fixed endpoint name), `status`, `wait_s`, `inline` (bool), `secondary` (bool) | Emitted at `client.py:282-288`. `endpoint` is a code constant, not a URL. |
| `github.call` | the existing fields | Rename the unnamed client.py:374 line. Keep it at INFO (or DEBUG if volume hurts). |
| `queue.deadline_dropped` | `count` | Emitted from the claim-time UPDATE (`queue.py:157-160`) when its rowcount > 0. |
| `db.pool_stats` | the `get_stats()` integers (`pool_size, pool_available, requests_waiting, requests_errors, requests_num`) and `pool` ∈ web, worker_system, worker_tenant | Every 5 min, plus once whenever a `PoolTimeout` occurs. Ints only, never the URL (`session.py:1`). |
| `*.db_unavailable` | add `cause` ∈ pool_timeout, operational | Separates saturation from an outage. Already distinguishable from the exception message at `session.py:76,78`. |

Log-derived alert (for self-hosters who have log tooling): `webhook.signature_rejected` **≥ 20 in 10 min** warns of a
secret mismatch after rotation, or of probing. Any `webhook.not_configured` is critical.

### 4.3 `/metrics` endpoint: **rejected for now**

- **Exposure.** The web process holds the system-plane BYPASSRLS role (`deploy/staging/README.md:87`; `web/asgi.py:49`).
  A scrape-triggered cross-tenant query on the public ingress process adds an unauthenticated surface and DB load.
  It would also need its own auth, or an allowlist plus a Caddy exclusion. Caddy hides it today
  (`Caddyfile:5-11`), but self-hosters who run without Caddy would not get that protection.
- **Topology.** The worker has no HTTP server, so in-process counters would need a second endpoint or a push gateway.
  Process-local counters reset on restart and do not sum across replicas. The DB already holds the truth.
- **Dependency.** `prometheus_client` is not present (`pyproject.toml:6-18`). It is not justified at pilot scale.
- **Optional later path, with no dependency:** `ops report --format openmetrics`, writing the §4.1 gauges as a textfile
  for node_exporter's textfile collector from cron. Prometheus users get scrapeable data without a new listener.

## 5. Candidate small offline tasks (not implemented)

| # | Task | Tests (offline, disposable DB / fakes) |
|---|---|---|
| T1 | `ops report` adds `queue: {depth_by_status, oldest_ready_age_s, lease_expired_unreaped, dead_by_reason_class (window)}` using now-based queries. `ops alerts` adds rules `queue_age` (>600 s) and `worker_absent` (unreaped > 0), and keeps exit 2 if any rule fires. The JSON becomes a list of rule results. | Seed jobs with backdated `run_after`/`locked_until`. Assert the gauges, the null on an empty queue, the firing and exit code, and that no `last_error` text appears in the output. |
| T2 | Provider-kind event: `investigation.provider_failed{kind}`, `investigation.finished` named via `event()`. | `test_loop`: fake providers raise each kind. Assert the event and kind, that the outcome is unchanged (`provider_failed`), and that no message text is logged. |
| T3 | `recovery_checkpoint` key `<kind>:last_completed` set at `_done(completed=True)`. `ops report` shows the age; an alert rule `recovery_stale`. | Complete, incomplete and locked passes (fake GitHub). The key advances only on a complete pass, including one with zero deliveries. |
| T4 | `queue.deadline_dropped{count}` event. | Claim with backdated `deadline_at`. Assert one event with the count. |
| T5 | `db.pool_stats` periodic event in the worker loop and the web lifespan; a `cause` field on `*.db_unavailable`. | Pool with `max_size=1` held open → PoolTimeout → `cause=pool_timeout`. The stats event holds ints only. |
| T6 | `github.rate_limited` event, and rename the "github call" line. | `tests/github_fake.py` 429/`x-ratelimit-remaining:0` → an event with `inline` true/false. |
| T7 | `ops report` sections `webhook_deliveries{outcome}` and `investigation_outcomes{inconclusive_reason}`. | Seeded rows. Codes only; no repo names. |
| T8 | Report `observe.dropped_events` in `worker.stopped`. | Unit test. |

All tasks respect `sanitize` and the system/tenant plane split. None adds a dependency or a network listener.

## 6. Alert routing for self-hosters

- **Mechanism already designed:** cron runs `docker compose --profile jobs run --rm ops alerts` every 10 min
  (`deploy/staging/README.md:101`). Exit codes are 0 ok, 2 firing, 1 DB unavailable or wrong role (`ops.py:199-218`).
  Recovery exits 1 when incomplete, and retention exits 3 when there is more to purge (`docs/OPERATIONS.md:157-175`).
- **Option A (zero code):** set cron `MAILTO=` and wrap the command so that only exit ≠ 0 prints, e.g.
  `ops alerts > /tmp/out || cat /tmp/out`. Cron then mails the JSON. It needs a local MTA on the host.
- **Option B (zero code):** a wrapper script posts the JSON to an operator-chosen webhook (Slack, Discord, ntfy,
  Alertmanager `/api/v2/alerts`) on exit 2 or 1. The URL lives in a host-only `chmod 600` file. It is never logged
  (the scrubber would cut query tokens anyway, `logging.py:179`).
- **Option C:** external uptime monitor on `https://<host>/readyz` (already public via Caddy). It covers web and DB
  reachability, independent of cron.
- **Option D (later):** the textfile/OpenMetrics output (§4.3) into an existing Prometheus/Alertmanager.
- **Dead-man's switch.** If cron itself stops, nothing alerts. Pair any option with a heartbeat ping
  (healthchecks-style) on successful `ops alerts` runs.

**Needs owner/host decisions (T-1002 / T-1003):**
1. The destination channel and on-call recipient.
2. Whether a third-party alerting SaaS may receive alert JSON. The JSON holds counts only; confirm against
   DATA-INVENTORY §3.
3. Final thresholds after the soak: 0.2 is provisional (`ops.py:44`), and the §4.1 values are proposals for T-1003 to
   measure p95 against.
4. Whether `ops` may show per-installation counts.
5. Cron cadence (the README suggests deliveries every 15 min, runs hourly, alerts every 10 min).
6. Log shipping and retention beyond Docker's 3×10 MB json-file (`compose.yaml:12-18`). Log-derived alerts in §4.2 need it.
7. Whether a `/metrics` listener is ever acceptable on the web host.
