# Implementation Tasks

Date: 2026-10-15. These tasks implement [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md).

- Estimates are in developer-days (dd) for one developer and include writing the task's tests.
- **No task beyond Phase 0 starts until gate G-0 passes and the user approves the plan.**

## Definition of Done (every task)

1. Code merged to `main` via a PR with green CI: `ruff`, `mypy --strict`, pytest, `pip-audit`.
2. The tests listed for the task exist and pass. New rules include their positive *and* negative examples.
3. No secrets, raw logs or customer data are committed. Fixtures are redacted.
4. Docstrings and runbooks are updated where behavior changed.
5. The acceptance criteria are demonstrated (test output or a short note in the PR).

## Effort summary

| Phase | Tasks | dd | Gate at end |
|---|---|---|---|
| 0 Validation and prerequisites | T0.01–T0.07 | 8.5 | **G-0** |
| 1 Foundation | T1.01–T1.07 | 4.0 | — |
| 3A Log parsing (offline) | T3.01–T3.09 | 5.5 | — |
| 2 GitHub integration | T2.01–T2.05, T2.07 | 3.5 | — |
| 3B History and attribution | T3.10–T3.18 | 5.0 | — |
| 4A Diagnosis and evidence | T4.01–T4.03 | 1.25 | — |
| 5 Check Run delivery and benchmark | T5.01–T5.04 | 3.25 | **G-INT** |
| 6 Pilot hardening and deployment | T6.01–T6.12 | 9.0 | **G-PILOT** |
| 4B LLM (optional, parallel to 6) | T4B.01–T4B.05 | 4.0 | LLM eval gate |
| **Internal MVP (1–5)** | | **22.5** | |
| **Pilot without LLM (1–6)** | | **31.5** | |

**Critical path:** G-0 → T1.01 → T1.03 → T1.05 → T3.01 → T3.08 → T3.10 → T3.11 → T3.12 → T3.17 → T4.02 → T5.02 → T5.04 (G-INT) → T6.04 → T6.09 (14-day soak, calendar-bound) → T6.10 (first install).

**Flexible ordering:** with one developer, "parallel" means these can be interleaved in any order once their dependencies are met:

- Phase 2 ‖ Phase 3A;
- T5.01 ‖ T3.13–T3.16;
- T6.06–T6.08 ‖ T6.09 soak;
- all of 4B ‖ Phase 6.

---

## Phase 0 — Validation and prerequisites (no production code)

**Stopping point:** the G-0 decision memo (T0.07) is written. BUILD, NARROW, CHANGE or ABANDON.

### T0.01 Accounts and test org
- **Objective:** have authenticated GitHub access for the study.
- **Files:** none in the product repo. Use a local `.env` (git-ignored).
- **Depends on:** none.
- **Steps:**
  1. Create the org `tracewise-bench`.
  2. `gh auth login`.
  3. Create a fine-grained PAT, "public repositories (read-only)".
  4. Store it in the OS keychain or a local `.env` as `GITHUB_TOKEN_LAB`. Never paste it in chat.
- **Tests:** `gh api rate_limit` shows 5,000/h.
- **Acceptance:** an authenticated job-log download works on a public repo. Unauthenticated returns 403 [verified].
- **Effort:** 0.25.
- **Risks:** none.

### T0.02 `lab` CLI (throwaway-quality, but becomes the parser seed)
- **Objective:** collect failed runs plus logs from public repos for labeling.
- **Files:** `lab/collect.py`, `lab/label_template.csv` (in a scratch repo, `tracewise-lab`).
- **Depends on:** T0.01.
- **Steps:**
  1. Take a repo list as input (30–50 Python/TS repos from companies with 5–50 engineers, chosen via GitHub search plus judgment).
  2. For each repo, `GET /actions/runs?status=failure&branch=<default>&per_page=50`, and also sample PR runs.
  3. For each failed run, download the failed job logs and keep the failed-step section.
  4. Write the logs to `data/logs/<repo>/<run>/<job>.log`. These stay local and are never published.
  5. Export a CSV with these columns: repo, run, attempt, event, sha, last-green link, first ~20 error lines, and empty label columns.
- **Tests:** a manual spot check of 5 runs.
- **Acceptance:** ≥300 candidate failed runs collected, so that ≥200 can be labeled.
- **Effort:** 1.25.
- **Risks:**
  - Rate limits: 5,000/h is ample.
  - Logs older than 90 days have expired. Restrict to the last 60 days.

### T0.03 Label 200 failed runs
- **Objective:** measure gate G-2.
- **Files:** `data/labels.csv`, `docs/labeling-guide.md`.
- **Depends on:** T0.02.
- **Steps:**
  1. Write the labeling guide from Plan §7.0 definitions. Labels: `CHANGE_IN_RANGE`, `PRE_EXISTING`, `DEPENDENCY`, `ENVIRONMENT`, `FLAKY`, `CONFIG`, `UNKNOWN`, plus "would blaming the triggering push be wrong? Y/N/unknown".
  2. Label 200 runs, using run history and compare in the GitHub UI.
  3. Re-label a random 20% after 48 h and compute Cohen's κ.
  4. Mark 50% of the runs as a held-out set (used later in T6.12).
- **Tests:** κ computed.
- **Acceptance:** the G-2 metric is reported with a 95% CI (Wilson), plus a per-category distribution.
- **Effort:** 2.5.
- **Risks:**
  - Labeler bias, a single labeler.
  - Public-repo bias. Report both as limitations.

### T0.04 Build the 5 comparison benchmark cases in the test org
- **Objective:** inputs for G-5. These double as the first benchmark repos.
- **Files:** `bench/cases/B-02`, `B-05`, `B-07`, `B-09`, `B-15` (truth.yaml, template, workflow).
- **Depends on:** T0.01.
- **Steps:** follow TEST-AND-RELEASE-PLAN §2:
  1. Use the C0/C1/C2 commit pattern.
  2. For B-05, use a local or private index stub, or a GitHub-hosted package under our org.
  3. Push and record the run IDs.
- **Tests:** each case produces the intended red runs.
- **Acceptance:** `truth.yaml` is committed **before** any tool is run.
- **Effort:** 1.0.
- **Risks:** making B-05 deterministic. Mitigation: a version range plus a controlled package index.

### T0.05 GitHub-native comparison
- **Objective:** decide G-5.
- **Files:** `bench/results/<date>/native.md`.
- **Depends on:** T0.04, plus a Copilot Pro subscription (a user decision, OQ-03).
- **Steps:**
  1. For each case, record Copilot "Explain error" output on the C2 run (verbatim, local).
  2. Click "Fix with Copilot" and record what it changed.
  3. Optionally install the CI Doctor sample in the test org via `gh aw` and record the issue it creates.
  4. Grade each with the rubric in TEST-AND-RELEASE §4.
- **Tests:** none.
- **Acceptance:** a G-5 verdict with per-case evidence.
- **Effort:** 1.0.
- **Risks:**
  - Copilot output is non-deterministic. Run each case twice.
  - "Fix with Copilot" pushes commits to the *test* repo, which is acceptable there.

### T0.06 Interviews
- **Objective:** G-1, G-3, G-PAY signals.
- **Files:** `research/interviews/notes-<n>.md` (anonymized).
- **Depends on:** none (start immediately).
- **Steps:**
  1. Do outreach per R-07 §7 (60 messages).
  2. Run 12–15 calls with the R-07 §2.2 script.
  3. For mock A/B (Q10), use real public failures from T0.03 rendered as mock Check Runs.
- **Acceptance:** ≥12 completed interviews with coded answers for Q1–Q3, Q8, Q9 and Q11.
- **Effort:** 2.0 (spread over 1–2 calendar weeks).
- **Risks:** recruiting delays. These are the calendar critical path of Phase 0.

### T0.07 Gate memo
- **Objective:** decide BUILD, NARROW, CHANGE or ABANDON.
- **Files:** `research/G0-DECISION.md`.
- **Depends on:** T0.03, T0.05, T0.06.
- **Steps:** apply Plan §16 thresholds verbatim and list deviations.
- **Acceptance:** the user signs off.
- **Effort:** 0.5.

---

## Phase 1 — Foundation

**Stopping point:** `make up && make test` is green, and a job enqueued via SQL is processed by the worker with retries.

### T1.01 Repository scaffold and tooling
- **Files:** `pyproject.toml`, `uv.lock`, `Makefile`, `.pre-commit-config.yaml`, `src/tracewise/__init__.py`, `tests/`, `.gitignore`, `.env.example` (from the Resource Checklist §6).
- **Depends on:** G-0.
- **Steps:**
  1. `uv init`.
  2. Add dependencies (ADR-01).
  3. Configure `ruff` (line length 100, rules E,F,I,B,UP,S,ASYNC) and `mypy --strict` for `src`.
  4. Add a `pytest` config (asyncio mode auto).
  5. Add Makefile targets: `up`, `test`, `lint`, `type`, `migrate`, `bench`.
- **Tests:** an empty test passes. CI-equivalent `make lint type test` passes.
- **Acceptance:** a fresh clone runs `make test` in under 2 minutes.
- **Effort:** 0.5.

### T1.02 Config, observability and contracts
- **Files:** `config.py`, `obs.py`, `contracts.py`.
- **Depends on:** T1.01.
- **Steps:**
  1. `Settings` (pydantic-settings) with every variable in `.env.example`. Mark secrets `SecretStr`.
  2. structlog JSON with a contextvars correlation ID.
  3. Implement the §4.6.2 models.
- **Tests:**
  - Settings fail fast when a required variable is missing.
  - A log line includes the bound `delivery_id`.
  - Contract validation tests, e.g. a bad SHA pattern is rejected.
- **Acceptance:** `SecretStr` values never render in logs (test).
- **Effort:** 0.5.

### T1.03 Database models and migrations 0001–0003
- **Files:** `db/models.py`, `db/base.py`, `migrations/versions/0001_core.py`, `0002_runs_analysis.py`, `0003_usage_audit.py`, `alembic.ini`.
- **Depends on:** T1.01.
- **Steps:** implement Plan §4.5.3 exactly, including the unique constraints and indexes.
- **Tests:**
  - `alembic upgrade head` then `downgrade base` on Docker Postgres 16.
  - Unique-constraint tests: duplicate delivery, run attempt, signature.
- **Acceptance:** schema diff between models and migrations is empty (`alembic check`).
- **Effort:** 1.0.

### T1.04 Session and tenancy helpers; pooling check
- **Files:** `db/session.py`, `db/tenancy.py`, `db/repos/system.py`, `db/repos/tenant.py`.
- **Depends on:** T1.03.
- **Steps:**
  1. `async with tenant_tx(installation_id)` runs `BEGIN`, then `SELECT set_config('app.installation_id', :id, true)`, then yields.
  2. Every `TenantRepository` method requires the transaction object.
  3. `SystemRepository` covers `job`, `webhook_delivery`, `installation` and `audit_event`.
  4. Test asyncpg against a PgBouncer transaction-mode container (`statement_cache_size=0`).
- **Tests:**
  - The context is transaction-local: after commit, `current_setting` raises in a new transaction on the same pooled connection.
- **Acceptance:** tests pass. Neon compatibility is noted in the ADR (U-6).
- **Effort:** 0.5.

### T1.05 Job queue and worker
- **Files:** `jobs/queue.py`, `jobs/worker.py`, `cli.py` (`worker` command).
- **Depends on:** T1.04.
- **Steps:**
  1. `enqueue(tx, kind, dedupe_key, payload, run_after)` uses `ON CONFLICT DO NOTHING`.
  2. `claim()`:

     ```sql
     UPDATE job SET status='running', locked_by=:w, locked_until=now()+interval '5 min', attempts=attempts+1
     WHERE id = (SELECT id FROM job WHERE status='queued' AND run_after<=now()
                 ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 1)
     RETURNING *
     ```

  3. A reaper re-queues `running` jobs whose `locked_until < now()`.
  4. Backoff schedule: 30 s, 2 m, 10 m, 30 m, 2 h. At `max_attempts`, set `failed` (dead letter).
  5. Per-handler timeout of 180 s.
  6. `LISTEN job_new` plus a 2 s poll fallback.
  7. Graceful SIGTERM.
  8. A per-(repo, lane) advisory lock helper: `pg_try_advisory_xact_lock(hashtext(lane_key))`. If not acquired, re-queue with +15 s.
- **Tests:**
  - Two workers never claim the same job.
  - A crashed job (simulated by killing the task) is reclaimed after lease expiry.
  - Backoff timing.
  - Dead-letter after 5 attempts.
  - Dedupe.
- **Acceptance:** all tests pass under 20 concurrent claims.
- **Effort:** 1.0.
- **Risks:** subtle async cancellation bugs. Mitigation: explicit tests.

### T1.06 Web skeleton
- **Files:** `api/app.py`, `api/health.py`, `api/static/privacy.html` (placeholder).
- **Depends on:** T1.02, T1.03.
- **Steps:**
  1. `/healthz` returns the version.
  2. `/readyz` checks the DB and that the Alembic revision is at head.
  3. Request-ID middleware.
- **Tests:** `/readyz` returns 503 when the DB is down.
- **Effort:** 0.25.

### T1.07 CI and local stack
- **Files:** `.github/workflows/ci.yml`, `docker-compose.yml`, `Dockerfile`.
- **Depends on:** T1.01.
- **Steps:**
  1. CI with a Postgres 16 service, running lint, type, tests and `pip-audit`.
  2. A multi-stage Dockerfile (uv, non-root user).
  3. Compose with Postgres and PgBouncer (transaction mode, for T1.04).
- **Acceptance:** the CI run is green, and `docker build` produces an image under 300 MB.
- **Effort:** 0.25.

---

## Phase 3A — Log parsing and fingerprints (offline)

**Stopping point:** every golden log from T0.02/T0.03 (≥60 selected) yields the expected primary error and fingerprint.

### T3.01 Log model and step splitter
- **Files:** `engine/logs/model.py`, `engine/logs/splitter.py`.
- **Depends on:** T1.02, and T0.02 data.
- **Steps:**
  1. Parse the timestamp prefix and `##[group]`, `##[endgroup]`, `##[error]`, `##[warning]` markers.
  2. Produce `Step(name, start_line, end_line)`.
  3. Map steps to API `steps[]` by order.
  4. Extract the "Set up job" section.
  5. **Confirm the marker formats on ≥20 real logs** (U-2) and document them in the module docstring.
- **Tests:** 10 golden logs with expected step boundaries.
- **Acceptance:** 100% on the goldens.
- **Effort:** 0.75.
- **Risks:** format differences across runner OSes. Include one Windows and one macOS log.

### T3.02 Normalizer and redactor
- **Files:** `engine/logs/normalize.py`, `engine/logs/redact.py`.
- **Depends on:** T3.01.
- **Steps:** implement the Plan §7.2 normalization and the §9 T3 redaction patterns, including an entropy check.
- **Tests:**
  - A corpus of 50 secrets is fully masked.
  - 20 benign high-entropy-looking strings are evaluated (accept some over-redaction).
  - Normalization is idempotent.
- **Acceptance:** zero secret leaks on the corpus.
- **Effort:** 0.75.

### T3.03 Python parsers: `pytest`, `py_traceback`
- **Files:** `engine/parsers/base.py`, `pytest.py`, `py_traceback.py`; fixtures under `tests/fixtures/logs/pytest/`.
- **Depends on:** T3.02.
- **Steps:**
  1. Define the `Parser` protocol (`name`, `match(step_text)`, `extract(...) -> list[NormalizedFailure]`).
  2. Extract the test ID, exception type, repo-local frames vs `site-packages/<pkg>` frames, collection errors and grouped failures.
- **Tests:** ≥12 goldens, including a collection error, assertion, ImportError, xdist output and `-q` output.
- **Acceptance:** goldens pass. A negative fixture (log containing "FAILED" in an echo line) gives no false parse.
- **Effort:** 0.75.

### T3.04 TypeScript parsers: `tsc`, `jest_vitest`
- **Files:** `tsc.py`, `jest_vitest.py` plus fixtures.
- **Depends on:** T3.02.
- **Steps:** both tsc formats; jest `●` blocks, `FAIL` lines and snapshot failures; vitest `FAIL … >`. Extract module paths from TS2305/TS2307 messages.
- **Tests:** ≥10 goldens.
- **Effort:** 0.75.

### T3.05 Lint parser
- **Files:** `lint.py`.
- **Depends on:** T3.02.
- **Steps:** handle ruff, mypy and eslint formats; one fingerprint per (tool, rule, path).
- **Tests:** ≥6 goldens.
- **Effort:** 0.25.

### T3.06 Dependency parsers: `py_deps`, `node_deps`
- **Files:** `py_deps.py`, `node_deps.py`.
- **Depends on:** T3.02.
- **Steps:**
  1. Resolver errors.
  2. A resolved-versions map from `Successfully installed …` and uv `+ pkg==ver`. Record cache hits as "versions unknown".
  3. npm/pnpm/yarn resolver error codes.
- **Tests:** ≥8 goldens, including a log with no version output (expect `versions_unknown`).
- **Effort:** 0.75.

### T3.07 Infra, config, runner header and generic parsers
- **Files:** `infra.py`, `config.py`, `runner_header.py`, `generic.py`.
- **Depends on:** T3.02.
- **Steps:** implement the patterns in Plan §7.1. The runner header yields `{image, version}`.
- **Tests:** ≥10 goldens, including a timeout cancel, exit 137, `ECONNRESET`, `KeyError` on environ vs a plain dict (negative), and a missing runner header.
- **Effort:** 0.5.

### T3.08 Primary selection, cascades and fingerprinting
- **Files:** `engine/primary.py`, `engine/fingerprint.py`.
- **Depends on:** T3.03–T3.07.
- **Steps:**
  1. Ordering rules from §7.1 step 5 and the cross-job collapse.
  2. Class-specific fingerprint keys (§7.2).
- **Tests:**
  - B-12-style cascade fixture: 1 primary, the rest downstream.
  - Fingerprint stability across 2 runs of the same failure with different timings and values.
  - Different tests give different fingerprints.
- **Acceptance:** goldens pass.
- **Effort:** 0.5.

### T3.09 Golden fixture harness
- **Files:** `tests/fixtures/logs/**/*.expected.json`, `tests/unit/test_goldens.py`, `cli.py` (`lab extract` subcommand).
- **Depends on:** T3.08.
- **Steps:**
  1. Select ≥60 redacted logs from the T0.03 data, covering all parser families.
  2. Write the expected JSON by hand, **not** from parser output.
  3. Add a parametrized test.
- **Acceptance:** ≥95% of goldens pass, and every failure is documented as a known gap.
- **Effort:** 0.5.

---

## Phase 2 — GitHub integration

**Stopping point:** a red run in the test org produces a `job` row within 1 s, and the worker downloads its failed-job logs with a scoped installation token.

### T2.01 Register `tracewise-dev` GitHub App
- **Files:** none (manual). Record the App ID and slug in `docs/github-apps.md`; no secrets there.
- **Depends on:** T0.01.
- **Steps:** follow Resource Checklist §3. Exactly 4 permissions and the `workflow_run` event. "Only on this account". Install on `tracewise-bench`.
- **Acceptance:** `GET /app` with the App JWT shows the expected permissions.
- **Effort:** 0.25.

### T2.02 App JWT and installation tokens
- **Files:** `github/auth.py`.
- **Depends on:** T1.02, T2.01.
- **Steps:** implement Plan §4.4.6, with scoped token requests, a cache, and refresh on 401.
- **Tests:**
  - JWT claims (`iat` −60 s, `exp` ≤ 10 min).
  - The token request body includes `repository_ids` and `permissions` (T6 security).
  - Cache expiry.
- **Effort:** 0.5.

### T2.03 REST client
- **Files:** `github/client.py`, `github/ratelimit.py`.
- **Depends on:** T2.02.
- **Steps:**
  1. httpx `AsyncClient` with timeouts (10 s connect, 30 s read).
  2. Pagination via `Link`.
  3. Primary and secondary rate-limit handling per §4.4.8, raising `RescheduleJob(run_after)` on primary exhaustion.
  4. 5xx retry.
  5. `download_job_log(job_id)`: get the 302, then stream from `Location` within 60 s, with the byte cap and section-filter callback.
  6. A concurrency semaphore of 8.
- **Tests (respx):**
  - 302 flow.
  - Expired redirect → retry once.
  - `x-ratelimit-remaining=0` → `RescheduleJob`.
  - 403 with `retry-after`.
  - Pagination across 3 pages.
  - 50 MB cap.
- **Effort:** 1.0.

### T2.04 Webhook endpoint
- **Files:** `api/webhooks.py`, `github/webhook_verify.py`, `github/payloads.py`.
- **Depends on:** T1.05, T1.06.
- **Steps:** implement §4.4.4 exactly, including dual-secret verification, the 25 MB cap and one transaction.
- **Tests:**
  - Valid → 202 plus job row.
  - Bad signature → 401.
  - Body tampered → 401.
  - Duplicate delivery → 200 `duplicate`.
  - Non-completed action → `ignored`.
  - DB down → 503.
  - p99 < 1 s at 50 rps (simple load test).
- **Acceptance:** FR-001 to FR-003 and NFR-001.
- **Effort:** 0.75.

### T2.05 Installation lifecycle handlers
- **Files:** `jobs/handlers/installation_event.py`.
- **Depends on:** T2.04.
- **Steps:** implement the §4.4.5 table, including the lazy upsert for unknown installations.
- **Tests:** a test for each action; suspended installations skip analysis.
- **Effort:** 0.5.

### T2.07 Dev tunnel, E2E smoke test and fork-PR check
- **Files:** `docs/dev-setup.md`, `tests/e2e/test_smoke.py` (marked `e2e`, opt-in).
- **Depends on:** T2.03–T2.05.
- **Steps:**
  1. Set up a smee.io channel or `cloudflared` tunnel.
  2. Push a failing commit to the test repo and assert the job row plus log download.
  3. Open a PR from a fork account against the test repo and record whether a Check Run can be created on the head SHA (U-1). Use a temporary test via a script.
- **Acceptance:** the E2E test passes, and U-1 is answered in ADR-06.
- **Effort:** 0.5.

---

## Phase 3B — History and attribution

**Stopping point:** `tracewise analyze` on recorded fixtures of B-01 to B-10 produces the expected category for both C1 and C2 runs.

### T3.10 RunSource interface, GitHub and fixture sources, recorder
- **Files:** `engine/history/source.py`, `github_source.py`, `fixture_source.py`, `cli.py` (`lab record` subcommand).
- **Depends on:** T2.03, T3.08.
- **Steps:**
  1. The protocol: `list_lane_runs`, `jobs_for_attempt`, `job_log_sections`, `compare`, `file_at`.
  2. A recorder that saves GitHub responses (redacted) to `tests/fixtures/github/<scenario>/`.
- **Tests:** a fixture replay yields the same objects as a live call (recorded once against a public repo).
- **Effort:** 0.75.

### T3.11 Lane and last-green finder
- **Files:** `engine/history/lane.py`, `baseline.py`.
- **Depends on:** T3.10.
- **Steps:** implement §7.0 lane keys and §7.3 `last_green` with ancestry, lookback and job-level green.
- **Tests:**
  - Linear history.
  - Force-push (diverged) → `non_linear`.
  - Job renamed → none.
  - Lookback exhausted → none.
  - PR lane vs base lane.
- **Effort:** 0.75.

### T3.12 First-bad finder and pre-existing rules
- **Files:** `engine/history/first_bad.py`, `engine/rules/preexisting.py`.
- **Depends on:** T3.11.
- **Steps:**
  1. Scan intermediate failed runs: stored signatures first, then ≤5 log downloads, with a truncation flag.
  2. Rules R-PRE-01 and R-PRE-02.
- **Tests:**
  - B-02 C2 → PRE_EXISTING with FB = C1's run.
  - B-02 C1 → not pre-existing.
  - Truncated scan → partial.
  - PR with the base failing with the same F → R-PRE-02.
  - Base failing with a different F → no fire.
- **Effort:** 0.75.

### T3.13 Change-set analysis and direct links
- **Files:** `engine/changes.py`, `engine/rules/code_change.py`.
- **Depends on:** T3.12.
- **Steps:**
  1. Classify changed files (§7.4).
  2. Links L1–L5 (§7.8). L5 parses Python and TS import statements of the failing test file (fetched via `contents/{path}?ref=`), one level deep only.
  3. Merge-commit handling.
  4. Truncation (>250 commits or >300 files).
  5. Rules R-CODE-01 and R-CODE-02.
- **Tests:**
  - B-01 positive (L1).
  - Docs-only commit never a suspect.
  - 40-commit unrelated range → R-CODE-02 with no SHA.
  - Truncated compare → no file claims.
  - L4 deleted module.
  - L5: the B-02 test imports `coffee_shop.pricing`, which is changed in C1 → linked.
  - L5 negative: an import of an *unchanged* module → no link.
- **Effort:** 0.75. (L5 adds risk; if it slips, ship L1–L4 and accept lower coverage.)

### T3.14 Dependency rule (R-DEP-01)
- **Files:** `engine/rules/dependency.py`.
- **Depends on:** T3.06, T3.13.
- **Steps:** implement the 3 conditions, the partial case and the module-to-package mapping table (a top-200 PyPI map plus "same name" fallback).
- **Tests:**
  - The B-05 positive.
  - The three negatives from §7.5.
  - Cache hit (no versions) → partial at most.
- **Effort:** 0.5.

### T3.15 Environment rule (R-ENV-01)
- **Files:** `engine/rules/environment.py`.
- **Depends on:** T3.07, T3.13.
- **Steps:** implement §7.6.
- **Tests:** strong positive; context-only case; same-version negative.
- **Effort:** 0.25.

### T3.16 Flaky and configuration rules
- **Files:** `engine/rules/flaky.py`, `engine/rules/config.py`.
- **Depends on:** T3.12.
- **Steps:** implement R-FLAKY-01/02/03 and R-CFG-01 (§7.7).
- **Tests:** every row of the §7.7 table, positive and negative. A fork PR with a missing secret.
- **Effort:** 0.5.

### T3.17 Verdict and ranking
- **Files:** `engine/verdict.py`.
- **Depends on:** T3.12–T3.16.
- **Steps:** implement the precedence (§7.9), `MULTIPLE` across primaries, conflicts → `MULTIPLE`/abstain, title templates (§2.4) and bands.
- **Tests:**
  - A table-driven test of ≥25 synthetic candidate combinations.
  - The INV-1 to INV-4 property tests: no SHA named without a link; FLAKY strong overrides; PRE suppresses blame of the triggering commit.
- **Effort:** 0.5.

### T3.18 CLI `analyze`
- **Files:** `cli.py`.
- **Depends on:** T3.17.
- **Steps:** `tracewise analyze OWNER/REPO --run ID [--attempt N] [--json]`, using the PAT (lab) or App credentials.
- **Tests:** CLI output equals the worker output on a fixture (FR-016).
- **Effort:** 0.25.

---

## Phase 4A — Diagnosis and evidence

**Stopping point:** every published claim on all fixtures is validated, and mutation tests prove the validator rejects fabricated claims.

### T4.01 Evidence catalog and diagnosis assembly
- **Files:** `engine/evidence/catalog.py`, `engine/diagnosis.py`.
- **Depends on:** T3.17.
- **Steps:**
  1. Build `E1..En` from rule inputs (log locators, compare data, version maps, attempts).
  2. Generate claims from templates per rule, plus unknowns and next actions (a static table per category).
- **Tests:** snapshot tests per category.
- **Effort:** 0.5.

### T4.02 Evidence validator
- **Files:** `engine/evidence/validator.py`.
- **Depends on:** T4.01.
- **Steps:** implement §8.6, including the token check for SHAs, paths, packages and versions in claim text.
- **Tests:** mutation tests that alter:
  - a log line;
  - an unknown SHA;
  - a version not in evidence;
  - a claim with registry-only evidence.

  Each must be rejected. If the root claim is invalid → `UNATTRIBUTED`.
- **Acceptance:** 100% mutation rejection.
- **Effort:** 0.5.

### T4.03 Persistence of analyses
- **Files:** `jobs/handlers/analyze_run.py`, `db/repos/tenant.py`.
- **Depends on:** T4.02, T1.04.
- **Steps:**
  1. The full handler: fetch, engine, validate.
  2. Persist the `workflow_run`, `analysis`, `failure_signature` upsert, occurrences, evidence, candidates and usage rows in one tenant transaction.
  3. Record per-stage timings.
- **Tests:**
  - Integration on fixtures.
  - Re-running the same job yields no duplicate rows.
- **Effort:** 0.25.

---

## Phase 5 — Check Run delivery and the internal-MVP benchmark

**Stopping point:** G-INT is measured (TEST-AND-RELEASE §6).

### T5.01 Renderer and sanitizer
- **Files:** `publish/render.py`, `publish/sanitize.py`.
- **Depends on:** T4.01.
- **Steps:**
  1. Title (≤70 chars).
  2. Summary sections: Verdict, Evidence, What we could not determine, Next steps, Outcome, plus "For AI agents" (code categories only).
  3. Escaping per §9 T7.
  4. Size caps: summary 8 KB, text 32 KB.
  5. Test a 70 KB summary against the dev App to learn the real limit (U-5).
- **Tests:** snapshot tests per category; XSS/markdown/mention fixtures.
- **Effort:** 0.75.

### T5.02 Publisher and idempotency
- **Files:** `publish/checks.py`.
- **Depends on:** T5.01, T2.03.
- **Steps:**
  1. Create or update per §4.4.10.
  2. Before create, look up `analysis.check_run_id`, then list check runs for the ref by name and match `external_id` (U-4).
  3. Refuse a SHA ≠ `job.head_sha`.
- **Tests:**
  - Crash after create but before persist → a retry produces no duplicate (fixture).
  - A new attempt updates the existing run.
- **Acceptance:** FR-012.
- **Effort:** 0.5.

### T5.03 Outcome tracker
- **Files:** `jobs/handlers/record_outcome.py`.
- **Depends on:** T5.02.
- **Steps:**
  1. On a completed run in a lane with an open analysis, compute the outcome (§7.13).
  2. PATCH the Check Run.
  3. Close the analysis after `resolved` or 14 days.
- **Tests:** all four outcomes, plus rerun-on-same-SHA → `resolved_on_rerun`.
- **Effort:** 0.5.

### T5.04 Build the remaining benchmark cases and run G-INT (synthetic)
- **Files:** `bench/cases/B-01…B-16`, `bench/scripts/run.py`, `bench/results/<date>/`.
- **Depends on:** T5.03, T0.04.
- **Steps:**
  1. Build the 11 remaining cases.
  2. Install `tracewise-dev` on the test org.
  3. Run all cases (C1 and C2).
  4. Score with `bench/scripts/score.py` against `truth.yaml`.
  5. Record latency and API calls.
- **Acceptance:** results are recorded, whether the gate passes or fails. Failures produce fix tasks.
- **Effort:** 1.5.

---

## Phase 6 — Pilot hardening and deployment

**Stopping point:** G-PILOT passes, and the first partner installation is live.

| ID | Objective | Files | Depends on | Key steps | Tests | dd |
|---|---|---|---|---|---|---|
| T6.01 | RLS (migration `0004_rls`) | `migrations/0004_rls.py`, `db/tenancy.py` | T4.03 | Roles `tw_owner` and `tw_app`; ENABLE + FORCE; policies; grants | Cross-tenant suite (TEST-AND-RELEASE §5); missing context errors; pooled reuse | 0.75 |
| T6.02 | Retention sweep and purge | `handlers/retention_sweep.py`, `purge_installation.py`, `cli.py admin` | T6.01 | Plan §4.5.6–4.5.7; self-scheduling daily job | Time-travel tests; zero rows after purge; audit tombstone present | 0.75 |
| T6.03 | Delivery reconciliation | `handlers/reconcile_deliveries.py` | T2.03 | Verify endpoint paths (U-3); a 15-min schedule; redeliver failed and unknown GUIDs ≤72 h | respx tests; manual test by stopping staging web for 5 min | 0.5 |
| T6.04 | Staging and production infrastructure | `fly.toml`, `docs/deploy.md`, `.github/workflows/deploy.yml` | T5.04 | Fly apps (web and worker process groups); Neon projects; `release_command`; secrets via `fly secrets`; GitHub Actions deploy on tag | `/readyz` green; rollback drill performed once | 1.0 |
| T6.05 | Sentry, scrubbing, usage and cost accounting, budget alert | `obs.py`, `handlers/*` | T6.04 | `before_send` scrubber; `usage_event`; `admin usage`; daily totals log; `LLM_DAILY_BUDGET_USD` | Scrubber test (no secrets or bodies) | 0.5 |
| T6.06 | Security test suite | `tests/security/*` | T6.01, T5.02 | Implement tests for T1–T13 (TEST-AND-RELEASE §5) | All green | 1.5 |
| T6.07 | Privacy notice, pilot terms template, install page | `api/static/*`, `docs/pilot-terms.md` | — | Data inventory, retention, sub-processors (Fly, Neon, Sentry, Anthropic if enabled), deletion contact | Review against §4.5.6 | 0.5 |
| T6.08 | Runbooks | `docs/runbooks/*.md` | T6.04 | The 7 incidents in Plan §13.3 | Tabletop each once on staging | 0.5 |
| T6.09 | 14-day staging soak | — | T6.04–T6.06 | Install staging on our own active repos; daily review of every verdict | Zero duplicate Check Runs; zero unhandled job failures; zero cross-tenant failures | 1.0 effort (14 days calendar) |
| T6.10 | Production App and first partner onboarding | `docs/github-apps.md` | T6.09, G-PAY | Register `tracewise` ("Any account"); send the install link; partner kickoff | Partner's first analysis observed | 0.5 |
| T6.11 | Registry context client (optional) | `registry/pypi.py`, `npm.py` | T3.14 | `published_at` lookup; 2 s timeout; context-only rendering | Malicious-metadata fixture (T8) | 0.5 |
| T6.12 | Real-data held-out evaluation (G-INT real) | `bench/real/` | T5.04, T0.03 | Run `tracewise analyze` on the 100 held-out labeled runs; score | Report false blame, accuracy and coverage with CIs | 1.0 |

---

## Phase 4B — LLM adjudicator (optional; only after T5.04, parallel to Phase 6)

| ID | Objective | Depends on | Key steps | Tests / acceptance | dd |
|---|---|---|---|---|---|
| T4B.01 | LLM client plus structured-output smoke test | T4.02 | Anthropic SDK; `output_config.format` with schema v1; low effort; refusal handling; verify Haiku 5.5 and Sonnet 5.5 support (U-7) | One live call per model on fixture evidence (≈$0.05 total) | 0.5 |
| T4B.02 | Prompt v1, adjudicator and budget guard | T4B.01 | Implement Plan §8.1–8.5; candidates and evidence by ID; repair once; fall back to deterministic | Schema-violation and unknown-ID outputs are discarded | 1.0 |
| T4B.03 | Eval harness | T4B.02, T6.12 data | Dev/test split; metrics: false blame Δ, `MULTIPLE` resolution, cost, latency | Deterministic replay with recorded LLM responses for CI | 1.0 |
| T4B.04 | Run the eval and choose a model | T4B.03 | Haiku 5.5 vs Sonnet 5.5 (Opus only if both fail) | Decision recorded in ADR-08; `LLM_ENABLED` default set | 1.0 |
| T4B.05 | Prompt-injection tests | T4B.02 | The §9 T2 fixtures | All pass | 0.5 |

---

## Scenario mapping (from the G-0 date)

| Week | Planned | Cumulative dd |
|---|---|---|
| 1 | T1.01–T1.07, T3.01–T3.02 | 5.5 |
| 2 | T3.03–T3.09, T2.01–T2.02 | 10.25 |
| 3 | T2.03–T2.07, T3.10–T3.13 | 16.0 |
| 4 | T3.14–T3.18, T4.01–T4.03, T5.01–T5.02 | 20.5 |
| 5 | T5.03–T5.04 (**G-INT**), T6.01–T6.04 | 25.5 |
| 6 | T6.05–T6.08, T6.12, T6.11; soak starts | 30.0 |
| 7–8 | Soak completes (T6.09), T6.10 first partner; optional 4B | 31.5 (+4) |
