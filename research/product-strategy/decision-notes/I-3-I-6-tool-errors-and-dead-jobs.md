# I-3 tool-call error policy and I-6 dead-job re-runs

- **Date:** 2026-11-01
- **Status:** Proposal for owner decision; nothing implemented
- **Sources:** `implementation-gap-report.md` §0a and §3 (rows I-3, I-6); `docs/internal/OWNER-DECISION-PACKET.md` §4a
  (the "re-enqueueing runs lost during a credential fault" follow-up).
- **Caveat:** citations are against the working tree at the time of reading. Several cited files have uncommitted
  changes (for example `jobs/handlers/analyze.py` gained `AttemptDeadline` while this note was being written), so
  line numbers may drift.

## Part 1: I-3, errors during tool calls

### Current behaviour

How a tool call runs: `loop.investigate` checks the call (`investigate/loop.py:134-162`), then dispatches it with
`ev.tools.call` (`loop.py:255`). `ToolBox.call` catches only `TypeError` (`context/tools.py:86-89`). Each tool reads
through `CodeSource.read` (`context/source.py:132-173`). The Git source changes every blob failure into `None`
(`context/gitfetch.py:406-410`), so GitHub errors in the middle of a tool call happen **only on the Contents API
fallback** (`context/provider.py:47-57`). `ContentsApiSource._read_blob` catches only `NotFound`, `Gone` and
`PermissionDenied` (`context/contents_api.py:47-55`).

| Error class | What happens today (with citations) | What the model sees | Loop | Evidence and confidence | Job |
|---|---|---|---|---|---|
| **Transient**: 429 or secondary limit over the 10 s inline wait; 5xx or transport error after 3 inline GET retries | The client raises `GitHubRetryable` (`github/client.py:288-299`). It passes through `_read_blob`, `source.read`, `ToolBox` (`tools.py:106` read_file, `tools.py:180` grep, where one grep can make up to 400 reads, `tools.py:33`), the loop (`loop.py:255`, no handler) and `diagnose` (`analysis/diagnose.py:40`), and is caught by `_handle` (`analyze.py:193-204`) | Nothing. The conversation is thrown away. The assistant turn appended at `loop.py:238` never gets its tool results, but it never reaches a provider again | Investigation aborted | Lost: no analysis row is written, because `_persist` runs only at `analyze.py:345` | `queue.fail` puts the job in `retry_wait` with backoff and honours `retry_after` (`queue.py:214-223`). On the final attempt, `could_not_complete` is published if no analysis was recorded (`analyze.py:197-203`). **A retry repeats log collection and the whole model investigation** (`analyze.py:306-313`), up to `max_attempts=3` (`queue.py:111`). Tokens from the failed attempt are recorded nowhere |
| Same transient error during **validator** reads after the model has answered | `finalize` reads with `purpose="validation"` (`investigate/validate.py:141`). There is no handler | n/a | n/a | **The model's completed answer is thrown away** | Retry, as above |
| **404 / 410 / non-rate-limit 403** on a file or symlink blob; blob SHA or size mismatch; bad encoding | `_read_blob` returns `None` (`contents_api.py:53-54`, `_decode` at `:58-69`), which becomes `ReadStatus.unavailable` and is recorded in `skipped` (`source.py:167-169`) | `"<path>: unavailable"` inside the data delimiter (`tools.py:107-108`, `loop.py:258`). A 404, a missing `contents` permission and a SHA mismatch look identical | Continues. A step in which every call fails counts as unproductive; 3 such steps end with `unproductive` (`loop.py:257-262`) | Never in `files_examined` (`tools.py:94-99`). Listed in `files_skipped` (`validate.py:330`) | No retry |
| **Other permanent GitHub errors** on a read: 422 or other 4xx (`client.py:333-346`), invalid JSON (`client.py:355`), `ResponseTooLarge` (`client.py:306,311`), `TokenScopeError`, `UnsafeRedirect` | Not caught in `_read_blob` or `ToolBox`. `_handle` re-raises `PermanentError` (`analyze.py:205-206`) **before** the notice branch at `:207-216` | Nothing | Aborted | Lost | `dead`, reason "permanent" (`queue.py:224-230`). **No notice to the user** (see defect D-A) |
| **Token revoked mid-run** (401) | `_with_reauth` mints a new token (`client.py:445-462`). A mint that gets 404 or 403 becomes `InstallationUnavailable` (`client.py:124-127`). A 401 after a successful re-mint also becomes `InstallationUnavailable` (`:462`). A mint 401 becomes `AppAuthenticationFailed` | Nothing | Aborted | Lost | `InstallationUnavailable` leads to `JobCancelled("cancelled_uninstalled")` (`analyze.py:186-187`): no notice, no retry. `AppAuthenticationFailed` ends the job `dead` (`errors.py:40-45`) |
| Mint refused with **422** (for example, the repository was removed from the installation's selection) | Re-raised as `PermissionDenied` with status 422 (`client.py:124-125`). `_read_blob` catches it (`contents_api.py:53`) | `"<path>: unavailable"` | Continues | Every later read fails without explanation, then `_recheck` may cancel (`analyze.py:315`) | Depends on `_recheck` |
| **Invalid arguments** (bad JSON, extra or missing keys, wrong types, over 1024 characters) | `validate_call` (`loop.py:134-162`) | `"REJECTED: <reason>"`, not wrapped in the delimiter (`loop.py:245-247`) | Continues. Counts as a call (`loop.py:243`) and never as productive | Never evidence | n/a |
| Argument values the tool refuses (start < 1, pattern length, glob) | `tools.py:104-105`, `:164-167` | `invalid_args` text, wrapped | Continues | n/a | n/a |
| A `TypeError` raised **inside** a handler | Reported as `"invalid arguments"` (`tools.py:88-89`) | Misleading text | Continues | n/a | Hides an internal fault (suspected masking) |
| **Unknown tool name** | `loop.py:136-137`. `ToolBox`'s own guard (`tools.py:82-84`) cannot be reached from the loop | `"REJECTED: unknown tool '<name[:40]>'"` | Continues | n/a | n/a |
| **Deadline reached while a tool is running** | The deadline is checked before each call (`loop.py:241`), at the start of each iteration (`:207`) and after each provider step (`:232`). A tool that is running is never interrupted. Only grep's subprocess has a time limit (5 s, `tools.py:35,201`). Each HTTP read can take up to 30 s with up to 3 retries. `diagnose` caps only the investigation's timeout at what remains of the attempt (`diagnose.py:36-39`) | The result of a call that overran is still added. The next check returns | `budget_exhausted` | Becomes `inconclusive` (`validate.py:353-354`), low confidence (`confidence.py:11-16`) | Succeeds with a report |
| **Missing file or directory** | `not_found` / `is_directory` (`source.py:144-145`). For list_dir: `tools.py:141-142` | `"<path>: not_found"` | Continues | Not evidence | n/a |
| **Partial reads**: too large, binary, budget used up | `source.py:160-173`. Budget exhaustion is recorded in `skipped` (`:163-166`) | `"<path>: too_large"` and similar | Continues | `files_skipped`. If the validator's reserve runs out, flag `validation_budget_exhausted` (`validate.py:142-143`) | n/a |
| read_file cut at the output limit | `ok=True`, header says `(output limit reached …)`, and the recorded range is exactly the lines sent (`tools.py:120-134`) | Truthful header | Continues | Range is correct. An **empty file** is `ok` but never recorded as examined (`tools.py:110-111`) | n/a |
| grep partial or timed out | Partial: `ok=True` with notes on truncation, file cap and unsearched files (`tools.py:216-225`). Timeout: `ok=False` with status `timeout` (`:206-207`) | Notes or `"grep timed out"` | Continues | n/a | n/a |

Other facts that matter for any policy:

1. The model only ever sees `res.content`. `ok` and `status` are never sent to it (`loop.py:258`), so it can tell an
   error from file content only by reading the text.
2. Failed results are cached in `seen` (`loop.py:256`). After a transient failure, an identical call gets
   `DUPLICATE` and is not run again.
3. `usage.tool_calls` includes rejected and duplicate calls (`loop.py:243`, `validate.py:339`).

### Defects found (Part 1)

- **D-A (CONFIRMED, silent failure).** During a tool or validator read on the Contents API source, a permanent GitHub
  error that is not 404, 410 or 403 ends the job `dead` and the user sees nothing. Path: `contents_api.py:53`
  (not caught) → `tools.py:86-89` (only `TypeError` is caught) → `loop.py:255` → `analyze.py:205-206` (re-raised
  before the notice branch at `:207-216`) → `queue.py:214,224-230`. Model spend is lost and not recorded.
- **D-B (CONFIRMED, wasted spend).** A transient error during a *validation* read (`validate.py:141`) throws away an
  answer the model has already given, and the retry runs the whole investigation again (`analyze.py:306-313`).
- **D-C (SUSPECTED, masking).** `except TypeError` (`tools.py:88`) reports a real bug inside a handler as "invalid
  arguments".

### Options

- **A. Keep today's behaviour.** Any GitHub error that escapes a tool aborts into a job retry, or ends the job `dead`.
  Cost: repeated model spend, silent dead jobs (D-A), lost answers (D-B).
- **B. Classify errors at the source/ToolBox boundary (recommended).** Add `ReadStatus` values `transient`,
  `forbidden` and `source_error`. Errors that affect one file go back to the model. A circuit breaker stops a
  degraded investigation honestly. Errors that affect the whole source still stop it.
- **C. Return every error to the model and never retry the job.** Simplest, but a GitHub outage then produces
  low-value `inconclusive` reports, which are wrongly counted as completed analyses (`repositories.py:232`).
- **D. B plus extra retries inside the tool.** The client already retries 3 times inline (`client.py:57-58`). More
  retries would mostly burn the deadline. Not recommended.

### Recommended policy (option B)

"Safe tool error" means the call fails, the model is told so in a fixed, code-written sentence, and the
investigation continues. "Investigation failed" means the loop stops with a named outcome that the handler maps to
a job decision. Nothing is silently suppressed: every class either leaves a model-visible line plus a
`files_skipped` entry, or produces a named outcome plus an event.

| Class | Tool result to the model (fixed text, wrapped in the delimiter, prefixed `ERROR <status>:`) | Investigation | Job | Rationale |
|---|---|---|---|---|
| Transient (`GitHubRetryable`) on the 1st and 2nd occurrence | `ERROR transient: <path> could not be read (GitHub temporarily unavailable). This says nothing about whether the file exists.` **Not cached in `seen`.** | Continues | — | One rate-limited file should not throw away the spend so far |
| Transient, 3rd occurrence, or `retry_after` longer than the remaining time | (last result as above) | Stops. New outcome `source_unavailable` | Treated like `PROVIDER_FAILURES` (`analyze.py:333-334`): retry while attempts remain, otherwise publish `could_not_complete` | Honest; avoids an `inconclusive` report caused by an outage |
| Transient during a validator read | n/a | Answer kept. Flag `validation_source_unavailable`. Location unverified, so the result is `inconclusive` or low confidence, never `high` | Succeeds | Keeps spend; never presents an unverified location as verified |
| 404, 410, SHA mismatch | `ERROR not_found: <path>` / `ERROR unavailable: <path>` | Continues | — | Expected per file |
| 403 (not a rate limit) on a blob | `ERROR forbidden: <path> (missing Contents read)` | Continues. Missing permission added to the report's publication notes | — | Today this looks the same as "unavailable" |
| Other per-read permanent error (422, other 4xx, invalid JSON, `ResponseTooLarge`) | `ERROR source_error: <path>` and an event `tool.source_error` | Continues | — | Fixes D-A; one bad file must not kill the job |
| Errors on the whole source: `InstallationUnavailable`, `AppAuthenticationFailed`, `TokenScopeError`, `UnsafeRedirect` | none | Propagates (unchanged) | Unchanged: `cancelled_uninstalled` or `dead` | Not a tool error: no token, or unsafe |
| Invalid arguments, unknown tool | Unchanged `REJECTED: …` | Continues | — | Already correct |
| Internal exception in a handler (D-C) | `ERROR internal: tool failed` and an ERROR event | Stops. Outcome `tool_failed`, treated like a provider failure | Retry, then `could_not_complete` | A code bug must be visible, not shown to the model as its own mistake |
| Deadline reached mid-tool | Pass the deadline into `ToolBox`/source. Grep stops scanning and returns partial results with the note `(stopped at the time limit; N files not searched)` | `budget_exhausted` (unchanged) | Succeeds, `inconclusive` | Bounds the 400-read grep |
| Missing file, too large, binary, budget used up, partial grep | Unchanged text with the `ERROR <status>:` prefix (partial grep stays `ok`, with notes) | Continues | — | Prefix removes any doubt about error vs data |

Invariants to keep: `files_examined` only from successful `read_file` calls; the tool-call id is echoed for every
call, including errors (`loop.py:259`); no new model-visible text carries GitHub messages (fixed strings only).

### Tests required (Part 1)

- `tests/context/test_contents_api.py::test_read_blob_retryable_maps_to_transient_status`: `ReadStatus.transient`,
  nothing raised, no `skipped` entry that claims the file is absent.
- `…::test_read_blob_422_invalid_json_too_large_map_to_source_error` (parametrised); `…::test_read_blob_403_maps_to_forbidden`.
- `…::test_installation_unavailable_and_app_auth_still_propagate`.
- `tests/context/test_tools.py::test_read_file_transient_result_text_is_fixed_and_prefixed`;
  `::test_grep_stops_at_deadline_and_reports_unsearched`; `::test_handler_typeerror_is_internal_not_invalid_args`.
- `tests/investigate/test_loop.py::test_transient_tool_error_not_cached_retry_executes`;
  `::test_third_transient_error_ends_source_unavailable`; `::test_tool_error_result_keeps_tool_call_id`;
  `::test_rejected_unknown_tool_counts_call_and_continues` (pins current behaviour).
- `tests/investigate/test_validate.py::test_validation_transient_read_keeps_answer_flags_and_caps_confidence`
  (band ≠ high).
- `tests/db/test_analyze_worker.py::test_source_unavailable_retries_then_could_not_complete`;
  `::test_tool_permanent_error_no_longer_dead_silently` (D-A regression: job `succeeded`, report published);
  `::test_forbidden_blob_named_in_publication_notes`.

## Part 2: I-6, re-running dead jobs

### Current behaviour

- **Ways a job becomes dead.** (1) `fail()` with a `PermanentError` (`queue.py:214,224-230`). (2) A retryable error
  with no attempts left, or with backoff that would pass the deadline (`queue.py:216-217,224`). (3) The reaper: an
  expired lease on the last attempt or past the deadline, `last_error='lease expired'` (`queue.py:127-133`); the
  handler never runs, so **no notice**. (4) Queued or retry_wait with `attempts=0` past the deadline
  (`queue.py:157-160`). (5) Claimed after the deadline: a notice, then a `PermanentError` (`analyze.py:170-179`).
  (6) No handler for the job kind (`jobs/worker.py:92-93`).
- **Abandoned leases.** Lease is 120 s (`queue.py:33`). The heartbeat runs every `lease_s/3` (`jobs/worker.py:60`) and
  extends the lease only if `locked_by` matches and `locked_until >= now()` (`queue.py:184-191`). Expired leases are
  reaped only inside `claim` (`queue.py:154`), under one advisory lock (`:153`).
- **Attempts** are incremented at claim (`queue.py:174`); `max_attempts` defaults to 3 (`queue.py:111`,
  `0001_initial.py:78`). The deadline is set once, at the first claim: 600 s (`queue.py:176`, `:35`).
- **Duplicate prevention.** `dedupe_key` is UNIQUE (`0001_initial.py:73`) and set to
  `analyze:<repo>:<run>:<attempt>` (`contracts.py:85-88`). Enqueue uses `ON CONFLICT DO NOTHING` (`queue.py:115-121`).
  The claim uses `FOR UPDATE SKIP LOCKED` and allows at most one running job per `run_key` (`queue.py:161-168`).
- **Consequence for re-runs.** A dead job blocks its run attempt for good. Webhook redelivery and the recovery sweep
  both go through `ingest_workflow_run` (`recovery.py:378`), which returns `duplicate_run` (`ingest.py:69-79`). The
  ops CLI has only `report` and `alerts` (`ops.py:190`). The only remedy today is a GitHub workflow re-run, which
  creates a new `run_attempt` and therefore a new key.
- **Stale-worker fencing (database).** `complete`, `fail` and `cancel_running` check `status='running' AND
  locked_by=<worker_id>` (`queue.py:198,208,265`). They do not check `attempts` or `locked_until`. A worker that is
  re-claimed elsewhere gets `completion_ignored` (`jobs/worker.py:115`). The worker id is
  `hostname[:40]-pid` by default and can be overridden with `--worker-id` (`worker.py:137`); uniqueness is not enforced.
- **Stale-worker fencing (side effects).** `JobContext.check` reads a flag local to the process (`jobs/worker.py:34-37`).
  The flag is set only when a heartbeat UPDATE matches no row (`:140`). A `DatabaseUnavailable` in the heartbeat
  leaves it clear (`:142-143`). The publisher checks it before each GitHub write (`publish.py:117,146,152,180,186`);
  `_persist` follows the check at `analyze.py:314`.
- **Partial results on retry.** One analysis per `run_pk`, written with an upsert in which the last writer wins.
  Tokens and cost are overwritten (`repositories.py:368-371`). Publication rows are locked `FOR UPDATE` across the
  GitHub call and reconciled before create (`publish.py:8-21,202-211`). The commit comment is write-once
  (`publish.py:109-110`). The stale guard compares the GitHub `(run_id, attempt)`, not the job attempt
  (`publish.py:214-216`). Notices are suppressed once any analysis is recorded (`analyze.py:197,210`,
  `repositories.py:295-303`).
- **Quota.** Counts analysis rows in this UTC month with status diagnosed, inconclusive or could_not_complete and a
  diagnosis (`repositories.py:232-244`). A retry of a run that has already been counted skips the gate
  (`analyze.py:238-239`). So a re-run never counts twice, but **model spend repeats** and only the last attempt's
  tokens survive. `add_usage` (`repositories.py:500`) has no callers.
- **Retention.** Terminal jobs are purged 365 days after `finished_at`. Audit events are kept for their own 365 days.
  A tenant purge waits for non-terminal jobs (`0008_retention_purge.py:19-23,101-105,120-124`). The alert counts
  `dead` by `finished_at` (`ops.py:147-149`), so changing a dead row in place would rewrite failure history.

### Defects found (Part 2)

- **D-1 (SUSPECTED, medium): side effects are fenced only by a local flag.** Sequence: worker A's lease expires.
  Worker B's `claim` reaps the job and claims it again (`queue.py:154,124-133,173-179`). A still passes `ctx.check()`
  until its next heartbeat (up to about 40 s), or without limit while A's heartbeat transactions keep failing
  (`jobs/worker.py:142-143`). In that window A can `_persist` (`analyze.py:345`) and publish
  (`publish.py:117,146,152,180,186`) at the same time as B. Publication rows serialise the two workers but cannot
  tell them apart (`publish.py:214-216`), so the last writer wins on the PR comment and Check Run, while the
  write-once commit comment keeps the first writer's diagnosis. The two surfaces can disagree, and model spend is
  doubled. Only A's `complete` is fenced (`queue.py:198`). Possible fix (not done): inside the persist and publication
  transactions, check `job.id`, `locked_by`, `attempts = <claimed attempts>` and `locked_until > now()` with
  `FOR SHARE`.
- **D-2 (SUSPECTED, low): the fencing token is only the worker id.** Neither `attempts` nor `locked_until` is checked
  (`queue.py:184-201,204-210,260-268`), and the id is not unique (`worker.py:137`). Two processes with the same
  `--worker-id`, or containers with a pinned hostname and PID 1, can extend, complete or fail each other's claims.
- **D-3 (CONFIRMED, behaviour gap):** a dead job is final and nothing can recover it (see above). This is I-6 itself.
  Dead jobs from the reaper also never notify the user (`queue.py:127-131`).

### Options

- **A. No re-run (today).** The operator asks users to re-run the workflow in GitHub. Rejected: this is impossible for
  the credential-fault follow-up in §4a.
- **B. Reset the dead row in place** (`status='queued', attempts=0, deadline_at=NULL`). Simple, but it destroys the
  dead history and the alert input (`ops.py:147-149`), and there is no natural way to bound it.
- **C. Insert a new job row linked to the dead one (recommended).**
- **D. Bulk requeue by filter** (for example `--last-error-prefix AppAuthenticationFailed --since …`): option C applied
  to a list, with `--max`. Recommended as a later step.

### Recommendation (option C)

`python -m tracewise.ops requeue --job-id N --reason <code> --operator <name> [--dry-run]`. It runs on the system
plane (`require_system_plane`, as `ops.py:197` does) and is a single transaction that takes the claim advisory lock.

1. **Conditions.** The job is `dead` and its kind is `analyze`. The payload still validates. The installation is
   `active` and the repository is enabled and in scope (the same rules as `_check_scope`, `analyze.py:112-120`). No
   queued, running or retry_wait job exists for the `run_key`. `reason` comes from a fixed list:
   `credential_fault_fixed`, `github_outage`, `provider_outage`, `bug_fixed`, `lease_lost`, `other`. Refused when
   `last_error` shows a data fault (invalid payload, installation or repository mismatch). `--dry-run` prints the
   dead job's class (permanent, attempts, deadline, lease) and any existing analysis and publications.
2. **Bound.** At most **2** manual re-runs per (repo, run, attempt). The new row uses
   `dedupe_key = analyze:<repo>:<run>:<attempt>:rerun:<k>` with k ∈ {1,2}; the UNIQUE constraint enforces the bound
   and rejects concurrent duplicate requests. Copy the payload and `run_key`. New `attempts=0`, `deadline_at` NULL
   (a fresh 10-minute deadline at claim), `max_attempts=3`.
3. **Idempotency.** Rely on the `run_pk` upsert and publication reconcile. Document that an existing commit comment
   is never replaced. Recommend fixing D-1 first, or in the same change.
4. **Audit.** `repo.audit(conn, "operator:<name>", "job.requeued", installation_id, dead_job_id=…, new_job_id=…,
   reason=…, rerun_index=k)` (`repositories.py:507-512`), content-free, plus an `ops.requeue` event. The dead row is
   not changed.
5. **Quota and billing.** No bypass of the quota. A re-run of a run that has already been counted is free on the
   counter (`analyze.py:238-239`). Otherwise it counts once, when it completes. Model spend is real: record
   per-attempt tokens through `add_usage` (`usage_event`) so overwritten tokens are not lost.
6. **Retention.** The new row follows the 365-day job rule. The audit event outlives the job row. Re-runs are refused
   for installations with status deleted or suspended (so a tenant purge is never blocked).

### Tests required (Part 2), in a new `tests/db/test_requeue.py`

- `test_requeue_dead_job_inserts_linked_row_and_audits`: new row queued with the `:rerun:1` key, dead row
  unchanged, one `audit_event`.
- `test_requeue_refuses_non_dead_and_non_analyze`; `test_requeue_refuses_inactive_installation_or_disabled_repo`;
  `test_requeue_refuses_data_fault_last_error`.
- `test_requeue_bounded_to_two_per_run_attempt` (the third attempt is refused);
  `test_concurrent_requeue_only_one_wins`.
- `test_requeue_refused_while_run_key_has_live_job`.
- `test_rerun_of_counted_run_not_double_counted_in_quota`; `test_rerun_of_uncounted_run_respects_quota_gate`.
- `test_rerun_reconciles_existing_check_run_and_pr_comment` and `test_rerun_never_replaces_commit_comment`.
- `test_failure_rate_history_unchanged_after_requeue` (`ops.failure_rate`).
- For D-1 and D-2 (`tests/db/test_queue.py`): `test_stale_worker_cannot_persist_or_publish_after_reclaim` (the flag
  is not set while B holds the lease, so a DB-level fence is required);
  `test_complete_rejected_for_previous_attempt_same_worker_id`.

## Owner questions

1. I-3: approve option B? Transient threshold of 2 tool errors before `source_unavailable`?
2. I-3: should `source_unavailable` retry the job (and repeat model spend), or publish `inconclusive` right away?
3. I-3: should a 403 on blobs be named as a missing permission in the report?
4. I-6: approve option C, with a bound of 2 re-runs and `max_attempts=3` for each re-run?
5. I-6: may an operator re-run bypass the monthly quota (proposed: no)?
6. I-6: fix D-1 (DB-level fence) before or together with the re-run command? Enforce unique worker ids (D-2)?
7. I-6: should the reaper's final-attempt `dead` (no notice today) get a `could_not_complete` notice?
8. I-6: add bulk requeue (option D) now for the credential-fault follow-up, or later?
