# Live validation runbook (prepared offline; nothing here has been run; each stage needs explicit approval)

This runbook adds test cards for what [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) (stages S0–S5) does not
cover. It covers the build that includes migrations 0012–0017: attempt fencing, publication reconciliation, tool-error
classes, source-unavailable outcomes, operator-authenticated requeue, usage breakdown, least-privilege grants, the
per-request attempt deadline (O-2), bound and size-capped provider continuation state (O-5), and the retention dry
run, audit and live-run exclusion.
Card ids are stable: refer to them in evidence and findings.

## 0. Rules for every card

- **Staging only** unless a card says "production". Staging means a disposable test organisation, a disposable
  repository (`tw-live`) containing only the fixture workflow, and a separate Tracewise App registration and database.
  No real customer repository is ever used.
- **No secrets in chat, tickets or evidence.** Credentials are created and kept by the owner in the deployment's secret
  store. Evidence is captured with the redacting log formatter; reviewers check every captured file for token shapes
  before sharing it (S5 grep).
- **Approval:** the owner approves each stage (G, W, L, I, P, R) by name before it starts. "Approved S0" does not
  approve anything here.
- **Stop at once if** any card's failure condition holds, any token-shaped string appears in logs, a second Tracewise
  object is created for one surface and run, or an analysis is published as complete when it was not. Then follow the
  card's rollback and the plan's "Rollback and stop conditions".
- **Fixture workflow** (`tw-live`, push and pull_request): one job that runs `pytest` against a deliberately failing
  test (the B-02 pricing defect), plus a manually triggered variant that prints only `exit 1` (no error line).

## 1. Prerequisites (all must hold before card G-1)

| # | Prerequisite | Checked by |
|---|---|---|
| PRE-1 | Database provisioned with `scripts/db/provision_roles.sql` (including `tracewise_operator`), migrated to `0017` as `tracewise_owner` **before** any worker starts | `python -m tracewise.db.migrate status`; `python -m tracewise.preflight` |
| PRE-2 | One personal operator login per person (`CREATE ROLE ops_<name> LOGIN ... IN ROLE tracewise_operator`), never a service role | `\du` reviewed by the owner |
| PRE-3 | Staging App registration with exactly: Actions read, Checks write, Contents read, Metadata read, Pull requests write; events `workflow_run`, `installation`, `installation_repositories` | screenshot of the App settings (no keys visible) |
| PRE-4 | Webhook secret, App private key and provider key in the secret store; `.env` references only | owner confirms |
| PRE-5 | Provider: `LLM_PROVIDER=fake` for stages G, W, L, P, R. A real provider only for stage I, and only after the owner approves that provider's data-handling gate (O-5 §12.3). DeepSeek is excluded | `python -m tracewise.preflight` output |
| PRE-6 | Offline gate on the exact commit to deploy: `make ci` exit 0 | CI log |
| PRE-7 | Log capture for web and worker; clock-synchronised hosts | `docker compose logs` works |

## 2. GitHub App installation and tokens (stage G)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| G-1 | PRE-1–PRE-4; the App's five permissions | installation only; no write, no provider | Install the App on `tw-live` only ("Only select repositories") | `installation.created` ingested; `installation` row `active`; `repository` row for `tw-live` only | event lines `webhook.ingested`; `SELECT id, status FROM installation` | any other repository appears in scope | uninstall the App |
| G-2 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w | Check Run + commit comment (fake provider) | Trigger one failing push run | tokens are minted for the analysis and the publish scope, each restricted to `tw-live`; `github/auth.py` refuses a token whose `repositories` list is missing or different (G-PLAT-13). No event is logged per mint: the evidence is the job outcome | job `succeeded`; no `TokenScopeError` in `job.failed` | `TokenScopeError`, or a token response listing other repositories | — |
| G-3 | G-2 done; one hour later | Check Run update (fake provider) | Re-run the analysis more than an hour after G-2 (past the token lifetime) | a fresh token is minted; no 401 reaches the job | job `succeeded` | job `dead` on 401 | — |
| G-4 | an EMU test org (owner's) | Check Run (fake provider) | Managed-user (EMU) organisation, only if the owner has one | owner names (`_` suffix) accepted by `paths.py`; publication works | job `succeeded` | `invalid_path` on the repository name | uninstall |

## 3. Webhook intake (stage W)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| W-1 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w | Check Run (fake provider) | Normal `workflow_run.completed` (failure) | 202 `enqueued`; one job | `webhook.ingested` outcome | 5xx, or two jobs | — |
| W-2 | W-1 | none (dedupe) | Redeliver W-1 from the App's "Recent deliveries" | `duplicate_delivery`; no new job | delivery outcome | a second job | — |
| W-3 | W-1 | none (dedupe) | Re-run the same workflow attempt (new delivery, same run attempt) | `duplicate_run` | outcome | a second analysis of the same attempt | — |
| W-4 | operator host with network access to the webhook URL | none | Send a request with a wrong signature (`curl` from the operator host with a bogus header) | 401; nothing stored | web log `webhook.signature_rejected` | any row written | — |
| W-5 | W-1 | none expected | Out of order: redeliver an older `in_progress` after `completed` | ignored or no-op; the completed analysis stands | outcome | the job is cancelled or duplicated | — |
| W-6 | App JWT (recovery reads deliveries) | redelivery request to GitHub; Check Run | Stop web for 10 min during a failing run, start it, run `python -m tracewise.recovery both` | missed delivery redelivered or the run swept, exactly once | `recovery.*` events | the run is never analysed, or analysed twice | — |

## 4. Workflow log retrieval (stage L)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| L-1 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w | Check Run (fake provider) | Failing run with a pytest traceback | log downloaded via the redirect; analysis anchored on the error line | `analysis.diagnosed` (`evidence_status ok`) | `logs_unavailable` | — |
| L-2 | shell on the worker host | Check Run (fake provider) | Expired signed URL: pause the worker (SIGSTOP) for 2 min after it has opened the log, then resume | the log is re-requested (no read from a stale URL) or the job retries | job result | a 403 on the blob ends the job `dead` | resume the worker |
| L-3 | fixture variant printing 200 MB | Check Run (fake provider) | Large log (the fixture prints 200 MB) | download capped; the log is flagged truncated; analysis says so | `limits.log_truncated` true | the worker exceeds its memory limit, or the cap is silent | delete the run |
| L-4 | repository admin (delete logs in the UI) | Check Run (fake provider) | Delete the run's logs in the GitHub UI, then re-run the analysis via redelivery | `logs_unavailable` (metadata only) | outcome | a guessed cause | — |
| L-5 | installation admin (change permissions) | Check Run naming the permission | Remove Actions read from the installation | `permission_denied`; Check Run names the permission | publication state | retries or `dead` without a notice | restore and re-approve the permission |
| L-6 | none (observed only) | none beyond the run's own | Rate limit: not provoked deliberately. Observe only if it occurs | waits ≤ the inline maximum, otherwise `GitHubRetryable` with `retry_after` | `job.failed` with `retry_after_s` | a busy loop of requests | — |
| L-7 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w; DB access as owner (staging) | Check Run only (notice) | Work deadline (O-2): set one queued job's `deadline_at` to now + 40 s (owner SQL, staging), then let the worker claim it | no GitHub read starts (the job list is never requested); a "could not complete" notice is published within the reserve; job `succeeded` / `could_not_complete`, not retried | `analysis.deadline_exhausted` event; the worker's request log (the client logs every GitHub request it sends) shows no `list_jobs_for_attempt` for that job | any work request after the deadline; a retry; no notice | none |

## 5. Investigation with a real provider (stage I; separate approval per provider)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| I-1 | PRE-5 approved for this provider; key in the secret store | **none** (no model call) | Preflight with the provider key present | provider selected and authenticated without a model call | `python -m tracewise.preflight` | a call is made, or the key appears in output | — |
| I-2 | I-1 | **provider call** (redacted excerpts and code go to the provider); Check Run + comment | B-02 failing run | bounded tool use (≤12 calls, ≤120 s); validated location `coffee_shop/pricing.py:41` | `analysis.diagnosed` (tool_calls, tokens); analysis row usage columns | an unvalidated location published | — |
| I-3 | I-2 | provider call | Usage | `tokens_in/out` equal the provider dashboard's figures for that request; `cached_input_tokens`/`reasoning_output_tokens` are numbers or NULL, never invented; `usage_source = provider` | `SELECT tokens_in, tokens_out, cached_input_tokens, reasoning_output_tokens, usage_source FROM analysis` | NULL totals, or a subset larger than its total | — |
| I-4 | owner rotates the key in the store | provider call attempt (rejected); Check Run notice | Invalid provider key (rotate it in the store to a revoked one) | `provider_failed` → retry → "could not complete" (Check Run only) | job and Check Run | a diagnosis; the key in any log | restore the key |
| I-5 | I-2 | provider call; Check Run | Deadline: set `INVESTIGATION_TIMEOUT_S=5` | `budget_exhausted` (inconclusive) or `attempt_deadline_exhausted`; never a guessed diagnosis | outcome | the attempt runs past the job deadline by more than the publication reserve | restore the setting |
| I-6 | I-1 | **no** provider call; Check Run + commit comment | "exit 1" only variant | `inconclusive` / `no_error_line` with **no** provider call; `usage_source` NULL or `no_call` | analysis row | tokens spent | — |
| I-7 | I-2 | provider call | Continuation state: run I-2 with a reasoning model and capture all logs | no reasoning or signature text in any log, event, report or database row; `investigation.replay_refused` absent (or, if a cap is hit, the result is inconclusive `provider_failed`) | grep of captured logs and `SELECT diagnosis FROM analysis` for the provider's item ids or `encrypted_content` | any continuation-state text outside memory | — |

## 6. Publication (stage P)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| P-1 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w | commit comment + Check Run | Push failure | one commit comment (G-PLAT-5: accepted with Contents read) and one neutral Check Run | GitHub ids in `publication` | a second comment; a non-neutral conclusion | delete the test branch |
| P-2 | P-1 | Check Run update | Re-run the workflow attempt twice | Check Run updated in place; commit comment count stays 1 | object ids unchanged | new objects | — |
| P-3 | PRE-1–PRE-7; Actions r, Checks w, Contents r, Metadata r, PR w; a PR on `tw-live` | PR comment + Check Run | PR failure on `tw-live` | one PR comment, edited in place on re-run; no commit comment | ids | duplicates | close the PR |
| P-4 | shell on the worker host | Check Run (adopted) | Kill the worker (SIGKILL) right after `publication.attempted` for the Check Run, then let the lease expire | the next attempt finds the Check Run by `external_id`, adopts and rewrites it (`adopted` or `reconciled`); `job.claimed{takeover: true}` | events; one Check Run | a second Check Run | — |
| P-5 | shell on the worker host | commit comment (adopted) + Check Run | As P-4, but on the commit comment create | next attempt adopts it; if its text differs: `superseded`, and the Check Run summary begins with the superseded notice | `publication.superseded_retained`; Check Run summary | a second commit comment; a stale comment with no notice | — |
| P-6 | P-1 | none (read only) | Read-after-write: inspect the commit comment body GitHub returns for P-1 | the body matches the rendered text (CRLF and trailing whitespace aside), so `superseded` is not raised falsely | compare the `publication.content_digest` and a recomputed digest | a false `superseded` on an unchanged report | — |
| P-7 | installation admin | Check Run + commit comment | Decline Pull requests write and run a PR failure | per-surface tokens (G-PLAT-11): PR comment `unpublished_permission`; the commit comment (D-4 fallback) and the Check Run are published; the Check Run names the permission. Record GitHub's actual mint response (422 or a reduced grant) | publication states; the mint response status (logs) | any other surface blocked; silent omission | restore the permission |
| P-8 | DB access as owner (staging) | possibly none (that is the test) | Publication deadline (O-2): pause the worker (SIGSTOP) after `analysis.diagnosed` until the job deadline has passed, then resume | writes that cannot start are `publication.not_started` (nothing sent, row unpublished); a write cut mid-flight is `publication.outcome_uncertain`; the next attempt (if any) reconciles; never `published` without GitHub's answer | events; `publication.state` | a row marked published without a GitHub id; a duplicate object | resume the worker |

## 7. Recovery (stage R)

| Card | Needs (prerequisites; App permissions) | Live effect (GitHub write? provider call?) | Action | Expected | Evidence | Fail if | Cleanup / rollback |
|---|---|---|---|---|---|---|---|
| R-1 | shell on the worker host | Check Run (fake provider) | Worker crash mid-investigation (SIGKILL) | lease expires (≤120 s); reclaimed as attempt 2; one analysis | `queue.lease_expired`; `job.claimed{takeover}` | the job stuck `running` | — |
| R-2 | two workers; shell on both hosts | Check Run (fake provider) | Two workers; freeze worker A (SIGSTOP) for longer than the lease while it investigates; let B finish; resume A | A's writes refused: `job.stale_attempt_rejected` then `job.stale_attempt_stopped`; B's analysis and publications stand | events; analysis root cause is B's | A overwrites anything, or A's publication is recorded | resume or stop A |
| R-3 | fake provider set to fail | Check Run notice | Retry exhaustion: make the provider fail every attempt | three attempts, then "could not complete"; job `succeeded` with that outcome (or `dead` for a permanent error, with the notice) | job row; Check Run | an inconclusive *completed* analysis | — |
| R-8 | shell on the worker host; a run that reaches publication (I-6 log variant) | commit comment + Check Run (resumed) | Publication interrupted after diagnosis (F1): SIGKILL the worker right after its first `publication.attempted` event; let the lease expire (≤120 s). A Checks-only network fault cannot be injected on staging, since every API shares one host; the transient-failure variant is covered offline (`tests/db/test_publication_recovery.py`) | attempt 1 persisted the analysis; attempt 2 logs `analysis.publication_resumed`, makes no log download and no model call, and publishes the same report; `ops report` `publication_incomplete` returns to 0 | events; `publish_result` before and after; GitHub objects (one Check Run, one comment) | a second investigation; a duplicate object; the diagnosis replaced by a notice | — |
| R-4 | PRE-2 (personal operator login); a dead job | Check Run when the re-run completes | Requeue a dead job as an operator: `python -m tracewise.ops requeue --job-id N --reason transient_outage --dry-run`, then without `--dry-run` (`DATABASE_URL_OPERATOR` = the operator's own login) | dry run writes nothing; the real one creates one linked job; `audit_event.actor = operator:ops_<name>`, with `max_reruns` | command JSON; `SELECT actor, detail FROM audit_event` | an actor other than the login; a requeue with the system URL succeeds | — |
| R-5 | R-4 | none | Requeue with the system-plane URL, and with `--operator someone_else` | `not_authorised`; `operator_mismatch`; nothing written | command JSON | any write | — |
| R-6 | a running job | none extra | Duplicate webhook during a running job | `duplicate_delivery`; the running job is unaffected | outcomes | a second job | — |
| R-7 | staging DB with aged test data | none (database only) | Retention on staging: `docker compose --profile jobs run --rm retention --dry-run`, review, then the same without `--dry-run` | dry run changes nothing and reports counts; the real run deletes exactly those counts, writes one `retention.run` audit row, skips runs with live jobs (0017), exit 0 or 3 | both JSON outputs; `SELECT detail FROM audit_event WHERE action = 'retention.run'` | dry run changes anything; counts differ; a live run's data deleted | restore the staging DB from its pre-test dump if needed |

## 8. Production (only after every staging card passed and the owner approves production)

Production checks are **observational**. Install on one owner-chosen repository, then watch the first ten real
failures. No fault injection: no SIGKILL, no permission changes, no key rotation tests.
- **Expected:** G-1, G-2, W-1, L-1, P-1 or P-3, and I-3 behaviour.
- **Daily evidence:** `python -m tracewise.ops report` and `alerts`.
- **Rollback:**
  1. Uninstall the App (stops all intake).
  2. Stop the workers.
  3. Downgrade migrations only together with the matching build (`require_schema_at` refuses mismatches).
  4. Delete Tracewise comments only manually and only if the owner asks.

## 9. After each stage

Record the result of each card (pass, fail, not run, with the reason) in GITHUB-CONTRACT-AUDIT.md. Then:
- uninstall the App from `tw-live` if the stage is the last of the day;
- run the S5 log grep for token shapes;
- the owner rotates any credential that appeared anywhere it should not.
