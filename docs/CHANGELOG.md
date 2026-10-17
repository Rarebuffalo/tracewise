# Change Log

## 2026-10-18 (g): T-304 secure code context (no checkout)

### Code

| File | Content |
|---|---|
| `context/paths.py` | Validation of owner/repo, 40-hex SHAs and repo-relative paths (NFC, no control or format characters, no `..`, `.`, empty or `.git` segments, no backslashes, length cap). Lexical in-tree symlink resolution. |
| `context/source.py` | `CodeSource` model: tree entries (file/symlink/submodule), `read()` with statuses (`ok`, `not_found`, `too_large`, `binary`, `symlink_escapes`, `symlink_loop`, `submodule`, `is_directory`, `invalid_path`, `budget_exhausted`, `unavailable`). Symlinks ≤5 hops, inside the tree only. Per-file 1 MB cap; aggregate read budget; `skipped` map (`files_skipped`). `UnavailableSource`. |
| `context/gitfetch.py` | `GitFetcher` with a private bare repo and **no checkout**; fetch by SHA with `--depth=1` and a blob filter; token as a Basic header via `GIT_CONFIG_*` env; from-scratch env; protocol and redirect lock-down; timeout, transfer cap (polled, plus a final check) and output caps, with a process-group SIGKILL on breach or cancellation; reads under `GIT_NO_LAZY_FETCH=1` without credentials; cleanup in `finally`; `sweep_workspaces()`. `GitObjectSource`. |
| `context/contents_api.py` | `ContentsApiSource`: Trees API listing (truncation flagged), Contents API at `ref=<sha>` with blob-SHA and size checks, `git/blobs` for symlink targets; oversized files never requested |
| `context/provider.py` | `open_code_context()`: Git first, then the Contents API, then `UnavailableSource`. Caller exceptions propagate and the workspace is always removed. |
| `github/endpoints.py` | `get_tree` and `get_blob` added (GET, Contents read) |
| `github/client.py` | `RepoClient.full_name`, `git_fetch_token()` (analysis scope only), `invalidate_token()` |

### Tests (offline)

- **`tests/git_server.py`:** `git http-backend` behind a WSGI shim on 127.0.0.1, with a per-run token. It records the auth headers it receives and can inject faults (status, delay).
- **`tests/context/test_gitfetch.py` (21 tests):** exact commit; LFS pointer not smudged; submodule reported; no hooks dir and no checkout; planted hooks never run; large blob skipped **with no lazy network fetch**; binary skipped; symlink escape, loop and chain; 9 unsafe-path forms; token never in argv, on disk or in logs, and the header received on every pack request; wrong token; missing commit; missing repo; HTTP 500; timeout with no leftover process; transfer cap; cleanup on exception and on KeyboardInterrupt; input validation and fixed host; read budget; sweep; **AT-SEC-06** with a SIGKILLed child process.
- **`tests/context/test_contents_api.py` (8 tests):** exact-SHA reads; size cap without a request; symlinks; submodules; unsafe names; blob-SHA mismatch rejected; truncated tree; failover git → API; both failing → unavailable; git preferred with no API calls; caller errors propagate with cleanup; publish scope cannot fetch code; budget.
- **`tests/unit/test_github_client.py`:** a named regression test for the log-cap bug (the cap crossed inside a later chunk).

### Bug found and fixed

The transfer cap was checked only while git was running. A fast transfer finishing between two polls escaped it. A final check now runs after the process exits.

### Docs

- **ARCHITECTURE:** ADR-14 revised (no checkout); new §4.2; G-PLAT-9.
- **SPEC:** FS-CTX-1 and FS-CTX-5 wording (objects and tree-path confinement).
- **IMPLEMENTATION-PLAN:** layout and step 6.
- **TASKS:** T-304 marked done.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `uv run ruff format --check src tests scripts` | pass (76 files) |
| `uv run mypy` | no issues (45 files) |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **210 passed** in 96.9 s |
| `python3 -I scripts/check_docs.py` | PASS |
| Leftover temp repos, clusters, servers or processes | none |

### Acceptance tests

| Test | Status |
|---|---|
| AT-CTX-01 | **Passed** (UNIT, local fixture repo). The LIVE half is gated (G-PLAT-9). |
| AT-CTX-02 | **Partial:** skipping and listing pass. "The analysis still completes" needs the pipeline (T-402+). |
| AT-SEC-06 | **Passed** (SIGKILLed process, then the sweep) |
| AT-SEC-09 | **Partial:** symlink refusal passes. "Instructions ignored" needs the investigator (T-402/T-403). |

### Open risk

The token is readable by the same OS user through `/proc/<pid>/environ` while a fetch runs (ARCHITECTURE §4.2).

## 2026-10-18 (f): T-303 PR association

### Code

| File | Content |
|---|---|
| `src/tracewise/github/pulls.py` | `associate_pr`. Calls `/commits/{sha}/pulls` first, then, for forks only, `/pulls?state=open&head=owner:branch`. Keeps open PRs into this repository whose `head.sha` equals the run's SHA; with several matches, the lowest PR number. No match means a push (commit comment). Never reads `workflow_run.pull_requests`. |
| `src/tracewise/github/client.py`, `endpoints.py`, `auth.py` | `SCOPES` moved to `endpoints.py`. `RepoClient` now refuses endpoints outside its token scope **before** minting or sending anything. |

### Tests

`tests/unit/test_github_pulls.py` (10 tests):

- same-repo PR;
- fork PR via the `head=` filter;
- fork with no match is treated as a push;
- the **real recorded** pallets/flask response (closed, merged PR) is not associated; the same data marked open is;
- stale head, closed and other-base PRs are ignored;
- lowest number wins;
- no `head=` lookup for same-repo runs;
- the analysis scope cannot list pulls.

A further test in `test_github_client.py` covers scope enforcement in both directions, with no requests made.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `ruff format --check` | pass (66 files) |
| `uv run mypy` | no issues in 40 files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **180 passed** in 81.2 s |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance-test status

| Test | Status |
|---|---|
| AT-PUB-09 | REPLAY **association half passed**. "→ PR comment on #n" needs the publisher (T-502). |
| AT-PUB-10 | REPLAY **association half passed**. The LIVE half (G-PLAT-4, real fork behaviour) is gated. |

## 2026-10-18 (e): T-301 GitHub App auth, T-302 REST client

### Code

| File | Content |
|---|---|
| `src/tracewise/github/endpoints.py` | Registry of the 16 callable endpoints, each with its authorising permission. `APP_PERMISSIONS` lists the five in FS-INS-2. Per-purpose scopes: `ANALYSIS_SCOPE` (read only) and `PUBLISH_SCOPE`. |
| `src/tracewise/github/auth.py` | `AppCredentials` (RS256 App JWT, 9 min; key hidden). `TokenProvider` mints repository-scoped, purpose-scoped installation tokens; checks the grant and fails closed on over-broad grants; keeps them in memory per (installation, repo, scope); refreshes 5 min before expiry; supports invalidate and drop-installation; registers tokens with the log scrubber. |
| `src/tracewise/github/client.py` | `GitHubHTTP`: registry-only calls; rate-limit handling (`retry-after`, `x-ratelimit-reset`, ≥60 s secondary; inline ≤10 s, otherwise deferred to the queue); 5xx and transport retries; error taxonomy; JSON cap; API-host-only pagination with a page cap; safe log redirect (https, allowlisted host, no credentials, **no Authorization header**, streamed, 512 MB cap). `RepoClient`: bound to one repository, re-mints once on 401, encoded path parameters, contents-path guard, `list_jobs`, `failed_jobs`, `job_log_lines`. |
| `src/tracewise/github/errors.py` | Errors mapped onto queue semantics: `GitHubRetryable`, `PermissionDenied`, `NotFound`, `Gone`, `InstallationUnavailable`, `TokenScopeError`, `UnsafeRedirect`, `ResponseTooLarge` |
| `pyproject.toml`, `uv.lock` | `httpx` moved to runtime; `pyjwt[crypto]` added |

### Tests and fixtures

| File | Content |
|---|---|
| `tests/github_fake.py` | In-process fake GitHub on `httpx.MockTransport`. The RSA key is generated in memory per session; no key file exists. |
| `tests/fixtures/github/recorded/` | Two **real anonymous** responses copied unchanged from the public evidence folder (provenance in `tests/fixtures/github/README.md`). All other responses are **synthetic**, shaped after the GitHub docs. |
| `tests/unit/test_github_auth.py` | 16 tests |
| `tests/unit/test_github_client.py` | 25 tests |
| `tests/db/test_github_worker.py` | 1 test |

### Bug found by the tests and fixed

A log chunk crossing the download cap was discarded whole, losing complete lines that fit. The client now keeps everything up to the cap.

### Docs

- **ARCHITECTURE:** §4.1 (GitHub credentials and calls); G-PLAT-8 (the log-redirect host allowlist is an unverified assumption).
- **IMPLEMENTATION-PLAN:** package layout.
- **TASKS:** T-301 and T-302 marked done.

### Validation (actually run, in `~/tracewise`)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts` | All checks passed |
| `uv run ruff format --check src tests scripts` | 64 files already formatted |
| `uv run mypy` (strict) | no issues in 39 source files |
| `uv run pytest -o addopts="--strict-markers" -p no:warnings` (all, slow included) | **169 passed** in 80.9 s |
| `python3 -I scripts/check_docs.py` | PASS |
| Secret scan of the staged diff | No private keys, PATs or API keys outside the redaction code and tests |

### Acceptance-test status (honest scope)

| Test | Status |
|---|---|
| AT-SEC-01 | **Passed (static):** every registered endpoint is covered by the five permissions; no contents, workflow or issues writes; no HTTP import or API host outside the client. Whether GitHub's real permission checks agree (e.g. a commit comment with Contents read) is **G-PLAT, LIVE**. |
| AT-SEC-05 | **Passed (fixture level):** tokens are never logged (not emitted, and scrubbed if they were) and never reused across installations, repos or scopes |
| AT-LOG-01 | **Partial:** the token request is scoped, only failed jobs are selected, and the redirect is followed within one call (fake transport). The pipeline wiring that downloads only failed jobs' logs is T-701-era handler work. |
| AT-LOG-03 | **Partial:** the client raises `NotFound`, `Gone` or `PermissionDenied`. The `logs_unavailable` / `permission_denied` report is T-503. |
| AT-REL-02 | **Partial:** the rate limit reschedules ≥60 s through the real queue, and the next attempt survives a 502. "No duplicate publish" needs T-502. |
| AT-SEC-03 | Not claimed. The client binding prevents cross-repo paths, but the RLS half is T-705. |

**Not tested anywhere:** real GitHub behaviour. No network calls were made.

## 2026-10-18 (d): T-106 webhook endpoint

### Code

| File | Content |
|---|---|
| `web/webhooks.py` | `POST /webhooks/github`. Checks run in this order, and nothing is parsed before the signature passes: declared length >25 MB → 413 without reading; streamed body capped at 25 MB → 413; no secret configured → 503 (fail closed); HMAC-SHA256 constant-time → 401; delivery and event headers validated → 400; JSON and schema → 400, recorded as `rejected`; DB unavailable → 503 with nothing persisted. Responses: 202 `enqueued`, 200 for duplicates and ignored deliveries, 200 `pong`. Blocking DB work runs in the threadpool. |
| `web/ingest.py` | One transaction holds the delivery row (deduped on `X-GitHub-Delivery`), the installation and repository upserts, the run row and the job (deduped on `(repo, run, attempt)`). Non-analysed conclusions and actions are recorded as `ignored`. |
| `web/health.py`, `web/app.py` | `/healthz`, `/readyz` (DB ping, returns 503 when the DB is down). App factory with no docs or OpenAPI endpoints. |

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check`, `ruff format --check`, `uv run mypy` (strict, 35 files) | pass |
| `uv run pytest` (all, slow included) | **127 passed** in 79 s |
| End-to-end concurrency test | 5 consecutive runs, all passed |
| Disposable clusters | No leftover clusters or processes after the run |
| `python3 -I scripts/check_docs.py` | PASS |

### Acceptance-test status after T-106

| Test | Status |
|---|---|
| AT-EVT-01, AT-EVT-02 | **Passed** (REPLAY, synthetic payloads) |
| AT-EVT-05 | **Passed**: 100 deliveries with the worker stopped, each <1 s; delivery and job joined 1:1; a mid-transaction DB failure rolls everything back, and the redelivery succeeds |
| AT-EVT-06 | **Passed**: same delivery ×3 (sequential and 24 concurrent requests); a new delivery for the same run; `in_progress` after `completed`; a re-run attempt enqueues a new job |
| AT-SEC-02 | **Passed**: missing, invalid, wrong-algorithm, wrong-secret and tampered signatures → 401 with no rows; >25 MB → 413 (declared and streamed) |
| AT-EVT-03 | **Partial**: `timed_out` enqueues a job. "The report mentions the timeout" needs T-501. |
| AT-REL-04 | **Partial**: 50 deliveries from one installation through the webhook and 6 real workers peaked at ≤2 concurrent, and the other installation finished in less than half the backlog time. The handler is a stub until the analysis pipeline exists. |
| AT-EVT-04 | LIVE (G-PLAT-1); gated |

**Note:** Starlette warns that its test client should move from `httpx` to `httpx2`. This is a test-only dependency; it will be revisited when the dependency is bumped.

## 2026-10-18 (c): T-104 schema and repositories, T-105 job queue and worker

### Code

| File | Content |
|---|---|
| `db/migrations/versions/0001_initial.py` | The 10 tables from ARCHITECTURE §3, CHECK constraints for every state column, a write-once trigger for published commit comments, runtime-role grants (DML only; `audit_event` append-only) |
| `db/migrate.py`, `db/migrations/env.py`, `db/urls.py` | Programmatic Alembic upgrade and downgrade, run with the owner role |
| `db/session.py` | Pool for the runtime role. `transaction()` maps pool timeouts and connection failures to `DatabaseUnavailable`, with no URL in the message. |
| `db/repositories.py` | Deliveries, installations and repos, runs, analyses, publications (reserve/lock, write-once, upsert), signatures (counted once per run, redacted), usage, audit. Errors are stored redacted and capped at 500 chars. |
| `jobs/queue.py` | Explicit state machine. Enqueue deduped on `dedupe_key`. Serialised claims with `SKIP LOCKED`, ≤2 running per installation, one running job per run. Lease, heartbeat and reaping. Backoff of 30 s and 120 s (±20%, ≥ `retry-after`). `RetryableError` vs `PermanentError`. 10-minute deadline from the first claim. Every transition out of `running` is fenced on `locked_by`. |
| `jobs/worker.py` | Claim, handle, then complete or fail. A heartbeat thread runs alongside; a lost lease raises before side effects. When the DB fails while recording an outcome, the job is retried after lease expiry (handlers must be idempotent). `run_forever` backs off exponentially while the DB is down. |
| `contracts.py` | `workflow_id` and `head_repo_id` added to the job payload; `WorkflowRunEvent.dedupe_key` |
| `tests/pg.py`, `tests/db/` | **Disposable Postgres:** `initdb` into a private 0700 temp dir, Unix socket only, removed after the session. System Postgres, its configuration and user data are not touched. |

### Docs

- **D-1, D-2, D-3** clarified as requested ([DECISIONS.md](DECISIONS.md)). D-1 is now a provisional hypothesis, with its denominator and method in [VALIDATION-PLAN.md](VALIDATION-PLAN.md) §3.
- **ARCHITECTURE §3:** the job state machine and `target_key`.
- **Package layout:** the `db/` file names.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check`, `ruff format --check`, `uv run mypy` (strict, 31 files) | pass |
| `uv run pytest -m "not slow"` | **82 passed** (45 earlier + 37 new DB tests) |
| Timing-sensitive DB tests (concurrency, heartbeat, lost lease, DB down) | 10 consecutive runs, all passed |
| `python3 -I scripts/check_docs.py` | PASS |

**The DB tests cover:**

- **Migrations and roles:** down/up/down; runtime role refused DDL and audit edits.
- **Constraints:** CHECK violations.
- **Delivery and run idempotency.**
- **Publications:** commit comment write-once; PR comment and Check Run upsert.
- **Signatures:** counting.
- **Queue state machine:** every transition, retries, `retry-after`, attempts exhausted, permanent errors, the deadline, lease expiry fencing, cancel, and a rollback mid-claim.
- **Caps and concurrency:** the per-installation cap with 50 jobs from one installation; one running job per run; 8 concurrent workers × 50 jobs with no double claim and the cap never exceeded.
- **Worker:** handler outcomes; heartbeat; lost lease; DB down at claim (no URL leaked); DB failure on complete or fail, leading to a safe re-run.

### Coverage gaps (not claimed as passed)

| Test | Status |
|---|---|
| AT-EVT-05, AT-EVT-06 | Need the webhook endpoint (T-106) |
| AT-REL-04 | Queue level only (cap of 2 per installation, other installations progress). The end-to-end check through webhook and worker is still open. |
| AT-PUB-01, AT-PUB-02 | Only the storage half (write-once and upsert keys). Publishing is T-502. |

## 2026-10-18 (b): offline implementation, Phases 0–2

**Tasks done:** T-001, T-002, T-101…T-103, T-201…T-206 (12.0 of 30.0 offline-core dd, as estimated). No network calls, no credentials, no LLM.

### Code

| Area | Files | Notes |
|---|---|---|
| Scaffold (T-101) | `pyproject.toml`, `uv.lock`, `Makefile`, `.env.example` | uv, ruff, mypy `--strict`, pytest. `.env.example` holds placeholders only. Runtime deps: pydantic, pydantic-settings. |
| Settings, logging (T-102) | `src/tracewise/config.py`, `logging.py` | `SecretStr` everywhere. `LLM_PROVIDER=fake` by default; `openai` refuses to start without a local key. JSON logs with a correlation ID. A filter scrubs registered secrets, token shapes and URL credentials from messages, extras and tracebacks. |
| Contracts (T-103) | `src/tracewise/contracts.py` | Webhook subset, `AnalysisJob` (IDs only), Diagnosis v2 with schema-level rules. |
| Pre-pass (T-201…T-206) | `src/tracewise/prepass/` | Steps come from the jobs API; runner timestamps slice the log. Sanitise, then redact. pytest, traceback, ruff, mypy, tsc, jest, vitest and eslint extractors, plus a generic fallback. Ranking, cascades, siblings and fingerprints. Streaming retention ≤2 MB. |

### Spec change (contract)

- Diagnosis v2 `primary_error` + top-level `siblings` became **`primary_errors[]` (1–3)**, each with its own `siblings`.
- **Reason:** FS-DX-2 and AT-DX-16 require ≤3 independent primaries, which the single-object contract could not express. Validator rule 1 already said "each".
- SPEC §3.1 and §3.2 were updated.

### Fixtures

| Kind | Files |
|---|---|
| **Real tool output** | `pytest_b02.out` (B-02 replica, defect at `pricing.py:41`), `ruff_b10.out`, `ruff_full_b10.out`, `mypy_b10.out`, `traceback.out`. All regenerable offline with `scripts/gen_python_fixtures.py`; host paths are rewritten to runner paths. |
| **Hand-written** (`*.handwritten.out`) | tsc, jest, vitest, eslint, from the documented formats. Real TypeScript tool runs need npm downloads; they belong to the benchmark harness (T-601). |

### Bugs found by the tests and fixed

- The tsc regex missed the colon in `file(3,10): error`.
- The error-window detector missed exception names such as `AssertionError`. A 200 MB log dropped its only error.
- The generic extractor took 3.3 s per 50 MB; a prefilter brought it to 1.4 s.

### Validation (actually run)

| Command | Result |
|---|---|
| `uv run ruff check src tests scripts`, `ruff format --check` | pass |
| `uv run mypy` (strict, 21 files) | pass |
| `uv run pytest -m "not slow"` | **45 passed** |
| `uv run pytest -m slow` | **10 passed**. AT-LOG-04: 200 MB log in ≈50 s, peak RSS < 300 MB. AT-SEC-15: 50 MB per extractor in ≤2 s. |
| `python3 -I scripts/check_docs.py` | PASS |

### Coverage of the acceptance tests touched (honest scope)

| Test | Covered now | Still needs |
|---|---|---|
| AT-LOG-02, AT-LOG-04, AT-LOG-05, AT-LOG-06, AT-SEC-15 | Full | — |
| AT-DX-02, AT-DX-03, AT-DX-07, AT-DX-16 | Pre-pass level | The end-to-end BENCH runs (T-601+) |
| AT-SEC-04 | Redaction | The storage, fake-provider-capture and report assertions (T-104, T-401, T-501) |
| AT-SEC-05 | Logging | Per-installation token scope (T-301) |
| AT-SEC-11 | Step attribution | The "no drift claim above `low`" part (T-306) |
| AT-DX-12 | Schema (band + ≥1 basis) | The corroboration rule (T-404) |

## 2026-10-18: canonical documentation set, archive cleanup, git initialisation

**Decisions applied:** Q1–Q6 (user, 2026-10-18), plus defaults D-1…D-3 ([DECISIONS.md](DECISIONS.md)). The plan of changes was written first: [DOC-CHANGE-PLAN.md](DOC-CHANGE-PLAN.md).

### Created (canonical, `docs/`)

| File | Content |
|---|---|
| `SPEC.md` | 63 requirements, 44 of them P0. New since S3: FS-PUB-7 (API PR association, fork-aware), FS-EVT-5(b) (failed-run sweep), FS-CTX-5/6, FS-DX-9, FS-SEC-5 rewritten (no credentials in benchmark tooling), provider interface with OpenAI first |
| `ACCEPTANCE-TESTS.md` | 90 tests. REAL-SET and project-token options removed. Real-accuracy gates removed. Synthetic **targets** labelled as targets. |
| `BENCHMARK.md` | B-01…B-17 consolidated from doc 04, the TEST-AND-RELEASE amendments, the S4 review and S3's B-17. Tracks A–F; public-metadata cases P-01…P-03; grading. |
| `ARCHITECTURE.md` | ADR-01…18. ADR-06 (three surfaces) and ADR-08 (AI on by default, OpenAI first) supersede the S1 ADRs. Python-only implementation (D-2). |
| `IMPLEMENTATION-PLAN.md` | Gates A–E, layout, flow, configuration (no personal tokens) |
| `TASKS.md` | 48 tasks with traceability and a bottom-up estimate |
| `VALIDATION-PLAN.md` | G-0 without credentials; G-2 as a metadata-only lower bound |
| `DECISIONS.md`, `README.md`, `CHANGELOG.md` | — |
| `scripts/check_docs.py` | Consistency checker (T-002) |

### Moved (archived, content unchanged: SHA-256 verified before and after)

| Destination | Files |
|---|---|
| `research/archive/2026-10-15-s1-research/` | 01, 02, 03, 04, 05, 06, 07, 08, EXECUTIVE-SUMMARY, PLAN-REVIEW |
| `research/archive/2026-10-15-s1-plan/` | IMPLEMENTATION-PLAN, IMPLEMENTATION-TASKS, ARCHITECTURE-DECISIONS, DECISION-REGISTER, TEST-AND-RELEASE-PLAN, RESOURCE-AND-SETUP-CHECKLIST, OPEN-QUESTIONS |
| `research/archive/2026-10-17-s2-audit-quarantined/` | S2 FINAL-REVERSE-ENGINEERING-AUDIT, VERIFIED-FEATURE-SPEC, TRACEWISE-PARITY-ACCEPTANCE-TESTS |

Doc 04 was moved only **after** the checker verified all 16 cases and their ground-truth phrases in `docs/BENCHMARK.md`.

### Unchanged

- `research/final-evidence-review/**`
- `research/final-audit-public/**`
- `research/final-audit/**`, including the quarantined evidence, untouched
- `research/REPOSITORY-AUDIT-2026-10-18.md`

**Deleted:** nothing.

### References

- **Active documents** were fixed to the new paths.
- **Dated records** were not edited. Their references resolve through the path map in `research/README.md`.

### Git

- `git init` on branch `main`, **no remote**.
- `.gitignore` excludes virtualenvs and caches, `.env*` (except `.env.example`), `*.pem`, `*.key`, and `research/final-audit/evidence/` (D-3).

**Pre-staging scan:**

- No secret patterns found. Matches of `sk-…` were inside "flask-…" file names: false positives.
- No credential-like file names.
- The name of the unintended `gh` account appears, as text only, in dated provenance records. It is not a secret; review it before ever adding a remote.

### Validation (actually run)

Command: `python3 -I scripts/check_docs.py`

| Check | Result |
|---|---|
| Links and paths in active docs | **0 missing** |
| Traceability: 63 requirements, 48 tasks, 90 tests | Every FS has ≥1 task and ≥1 test; every referenced task or test exists; every test is referenced |
| Banned instructions in active docs | **0 hits** (`gh auth login`, `gh run list`, personal tokens, the unintended account, REAL-SET, unmeasured latency claims) |
| Doc 04 B-01…B-16 consolidation | **16/16 verified** |
| Overall | **PASS** |

**No product tests exist or were run** as part of this documentation change.
