# Data inventory (T-1001 support; Phase 23)

This inventory was derived from the code and schema at the Phase 23 commit, **not** from the intended architecture. Every row names the implementation that supports it. Retention marked *(D-12)* is the current code's interpretation and is **pending your approval**.

## 1. What enters the system

| Category | Source | Purpose | Where it lives | Retention | Evidence |
|---|---|---|---|---|---|
| Webhook deliveries (`workflow_run`, `installation`, `installation_repositories`, others ignored) | GitHub, HMAC-signed | Start analyses; track installation scope | **Body never stored.** Only the delivery id, event, action, installation id, outcome and job id go to `webhook_delivery`. | 14 days | `web/webhooks.py`, `web/ingest.py`; `test_webhook.py` |
| Installation and repository identity: ids, account login, `owner/repo` name, enabled and removed flags | Webhook payloads | Scope checks, tenant key | `installation`, `repository` | Until tenant purge (7 days after uninstall), then a tombstone row: id, status, timestamps; `account_login` cleared *(D-12)* | `web/lifecycle.py`, `db/repositories.py`; `test_lifecycle.py`, `test_retention.py` |
| Workflow-run metadata: run id, attempt, workflow id, head SHA, head branch, event, conclusion, head repo id | Webhook or recovery sweep | Dedupe, analysis | `workflow_run` | 365 days once unreferenced *(D-12)* | `db/repositories.py::insert_workflow_run` |
| **Job logs** | GitHub Actions logs API (302 to a signed blob URL) | Error extraction | **Memory only.** Streamed with a cap (`LOG_MAX_BYTES_PER_JOB`, default 2 MB); sanitised and redacted line by line. | Not persisted, except redacted excerpts (below) | `github/client.py`, `prepass/sanitize.py`; `test_retention.py::test_at_sec_12_*` |
| **Source code** | `git fetch --depth=1 --filter=blob:limit=1m` into a private 0700 workspace, or the contents API as a fallback | Code context for the investigator and the validator | Temporary workspace, removed after the job; stale workspaces swept at worker start and after 30 min | Not persisted, except the redacted snippet and replacement (below) | `context/gitfetch.py` (`sweep_workspaces`), `context/provider.py`; `test_gitfetch.py` |
| Trigger diff (patches of the changed files) | GitHub compare and commit APIs | Attribution relevance; `get_diff` tool | Memory only | Not persisted, apart from changed-file paths inside `diagnosis.attribution` | `context/trigger.py` |

## 2. What is persisted (PostgreSQL)

| Table / field | Content | Bounds and redaction | Retention | Evidence |
|---|---|---|---|---|
| `analysis.diagnosis` (JSONB) | The validated diagnosis (`contracts.Diagnosis`). It contains the items listed below. | Each item has its own cap; everything that originates in logs, source or the model is redacted | Whole document set to NULL after **90 days** *(D-12 interpretation of "excerpts")*; row deleted after 180 days | `investigate/validate.py`, `contracts.py`; `test_retention.py` |
| ↳ `primary_errors[].excerpt` | Log excerpt, ≤3 errors | ≤2048 chars each, redacted | as above | `validate.py` (`redact(text)[:2048]`); AT-SEC-12 test |
| ↳ `problem_snippet` | **Source lines** at the validated location, copied by the system | ≤15 lines and ≤4000 chars; **redacted since Phase 23 (P-1)** | as above | `validate.py`; `test_validate.py::test_stored_snippet_and_replacement_are_redacted` |
| ↳ `fix.replacement.new_text` | Model-proposed replacement code | ≤20 lines; dangerous commands removed; **redacted since P-1** | as above | `validate.py::_fix` |
| ↳ `root_cause`, `why`, `fix.description`, `next_steps`, `files_examined[].verdict` | Model text | 300, 800, 600, 3×160 and 140 chars; URLs removed; unverified paths masked; redacted | as above | `validate.py::_Text.clean` |
| ↳ `files_examined`, `problem_location`, `failed`, `run`, `attribution` | Paths, line ranges, step names, ids, SHAs | Repository-relative paths validated | as above | `contracts.py` |
| `analysis` other columns | Status, category, confidence, provider, model, tokens, cost, latency, stage timings, publish result | Numbers and identifiers | 180 days | migrations 0001 and 0007 |
| `publication` | Surface, target key, GitHub object id, state, content **digest** (not content), missing permission | No report text stored | Deleted with its analysis (180 days) | migrations 0001 and 0002 |
| `failure_signature` | Fingerprint, normalised message | ≤300 chars, redacted | 365 days after last seen | `db/repositories.py::record_signature` |
| `job` | Payload (ids only), status, attempts, `last_error`, result (outcome, PR candidates) | `last_error` ≤500 chars, redacted | Terminal jobs: 365 days; non-terminal: never by age *(D-12)* | `jobs/queue.py`; `test_observability.py::test_failure_in_each_stage_*` |
| `usage_event`, `audit_event` | Kind and quantity; actor, action, content-free detail | Identifiers only | 365 days; audit rows kept through a tenant purge *(D-12)* | `db/repositories.py` |
| `recovery_checkpoint`, `redelivery_request` | Cursors; delivery GUIDs, attempts | System data | Redelivery rows 365 days | migration 0004 |

## 3. What leaves the system

| Destination | What | Notes |
|---|---|---|
| GitHub: commit comment, PR comment, Check Run in **your** repository | The rendered report: excerpts, snippet, location, fix, next steps | Redacted at render time. **Stored by GitHub under your repository's control. The Tracewise purge does not delete it.** |
| Model provider (**not enabled**; only the offline `fake` exists) | The system prompt; redacted log excerpts and pre-pass summary; the trigger diff; **tool results: source-file windows (≤250 lines, ≤8000 chars per call), grep lines, directory listings** | Tool results and the diff are **not** redacted before sending (P-2, review item). The provider's own retention and training terms are unknown until the contract is recorded (MODEL-ADAPTER C-8). |
| Operational logs (stderr JSON) | Event names, ids (delivery, job, installation, repo, run), outcomes, counts, timings, error **types** | No content fields (deny-list); scrubbing of secrets, URL queries, auth and cookie values (ARCHITECTURE §4.8) |

## 4. Never stored (as verified)

| Item | Verification |
|---|---|
| Webhook request bodies | Schema has no column for them; `test_webhook.py` |
| Full job logs | AT-SEC-12 test: after 20 real-pipeline analyses, no raw-log needle appears in any table |
| Full source files | AT-SEC-12 test: the source file is absent, and at most 3 cited lines appear |
| Installation tokens, the App private key, the webhook secret, database URLs | Tokens are memory-only (`github/auth.py`); secrets are `SecretStr` and scrubbed from logs; `test_github_auth.py`, `test_logging.py` |

**Caveat:** "never stored" does **not** mean "no source or log text is stored". Redacted excerpts and snippets are stored for up to 90 days (§2).
