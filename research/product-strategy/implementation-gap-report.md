# Implementation gap report (2026-10-30; updated 2026-11-01)

**Scope.** A consolidated, verified view of what Tracewise implements today, what was fixed during this review, and
what remains. It merges three independent read-only audits (implementation and developer experience; threat model;
Gemini contract) with the reproductions and fixes made afterwards. Baseline: HEAD `a738c61`, where `make ci` exited 0
with 1,559 passed. After the fixes below (uncommitted): `make ci` exited 0 with 1,592 passed, 0 skipped, 0 external
connection attempts, truth lock unchanged.

**Status vocabulary.** *Verified*: implemented, with passing tests that exercise it. *Partial*: implemented with a
known gap. *Missing*: not implemented. *Under-tested*: implemented, tests do not exercise the risky path. *Blocked*:
needs external configuration or an owner decision. *Unknown*: the evidence does not settle it.

This report does not replace [docs/PROJECT-HANDOFF.md](../../docs/PROJECT-HANDOFF.md) (the canonical project state) or
[docs/OWNER-DECISION-PACKET.md](../../docs/OWNER-DECISION-PACKET.md) (the decisions); it cites them.

## 0. Update 2026-11-01: verification of the 2026-10-30 batch, further fixes, status matrix

**Verification.** Every 2026-10-30 fix (§2) was re-read against its diff and regression test. All hold; edge cases
that remain are listed in §3a. The 2026-10-30 "final `make ci`" left no result. It was rerun on 2026-11-01 and failed
one test, `test_quota.py::test_last_months_analyses_do_not_count`. The test, not the product, was wrong: it computed
"last month" in the database session's time zone (IST), so in the first 5½ hours of each local month the rows still
fell inside the current UTC month (the quota correctly uses UTC). Fixed below (Q-1).

**Fixed on 2026-11-01** (each reproduced or reasoned from code first; regression tests added):

| ID | Defect | Fix | Regression tests |
|---|---|---|---|
| TK-1 | Expired installation tokens of repositories never asked for again stayed in the token cache and in the global log scrubber for the life of the worker | Each `TokenProvider.token()` call evicts expired entries of other keys (and unregisters them) | `test_expired_tokens_of_other_repositories_leave_the_cache_and_the_scrubber` |
| C-9b | Cause of C-9: recovery minted one App JWT (9-minute life) per pass and reused it for every redelivery POST | A fresh JWT per POST (signed locally); the C-9 401 handling remains for key faults | `test_each_redelivery_post_carries_a_freshly_minted_app_jwt` |
| I-7 | No `statement_timeout`/`lock_timeout` on runtime sessions | Every pool connection: 30 s statement, 10 s lock, set per session; both surface as `DatabaseUnavailable` (retryable) | `tests/db/test_session_timeouts.py` (both planes, held row lock, long statement, bounds) |
| C-7 | Signed log URLs obtained for all jobs up front, read one after another: a slow first log let later URLs expire | A URL older than 30 s is re-requested just before reading; nothing is downloaded twice | `test_a_signed_log_url_older_than_its_freshness_window_is_requested_again`, `test_fresh_signed_log_urls_are_not_requested_again` |
| C-3 (first half) | `grep` said "no matches" even when files were skipped for size, budget or read failure | The result counts files not searched | `test_grep_features_and_limits` |
| Q-1 | Time-zone-dependent quota test (above) | Test uses the UTC month boundary | `test_last_months_analyses_do_not_count` |
| W-1 | Two helper functions (`test_key`, `test_key_pem`) were collected as tests (pytest warnings) | Marked `__test__ = False` | warnings gone |
| MP-2 | Final step removed the tool declarations (prefix change; OpenAI G-7 undocumented) | Constant declarations; `tool_choice: "none"` / Gemini `NONE`; smoke harness aligned | `tests/investigate/test_codec_contract.py`, `test_pass_sends_exact_ids_and_reasoning_once_and_forbids_tools_on_the_final_step` |
| MP-3 | Usage had totals only | Validated cached-input and reasoning-output subsets from recorded fields | `test_*usage_breakdown*`, `test_an_impossible_usage_breakdown_fails_closed` |
| MP-4 | Refusal, truncation and outage were indistinguishable | `ProviderRefusal`, `ProviderTruncated` for documented reasons only; same outcome | `test_truncation_refusal_and_missing_usage_fail_closed_with_their_kind`, `test_the_http_provider_surfaces_the_kind_without_quoting_the_document` |

### 0a. Implementation status matrix (code → gap → change → dependencies → tests → acceptance)

**Completed and verified (offline):** webhook HMAC and size caps; idempotent ingest (delivery, run, job in one
transaction); durable queue with leases, reaper, bounded concurrency; recovery of missed deliveries and runs; job and
log retrieval with redirect allowlist, port pinning and freshness re-request; deterministic pre-pass; bounded
read-only investigation (4 tools, deadline per dispatch); evidence validation with H-1 claim stripping;
code-computed confidence; report rendering with a bounded size; Check Run and comment publication with reconcile; RLS
tenant plane; token scoping and lifecycle; log and provider-view redaction (pattern-based); database session bounds;
provider-neutral codec contract for the OpenAI and Gemini codecs.

| Area | Existing implementation | Remaining gap | Required change | Dependencies | Tests | Acceptance |
|---|---|---|---|---|---|---|
| **Implemented, not verified live** | | | | | | |
| GitHub delivery path | S0 observed with the fake provider; S1 step 1 only | S1 steps 2–4, S2, S3 (G-PLAT-5, -8, -10, -11) | None in code; run the gates | Owner: test org, approvals | LIVE-VALIDATION-PLAN | Gates pass and are recorded |
| OpenAI and Gemini codecs | Offline contract tests; benchmark-only | Real response shapes (G-4…G-8; NG-1…) | Fix only what the smoke shows | Owner: A-1…A-7, keys, spend | Smoke harness | Smoke `pass`; then T-605 benchmark |
| **Partially implemented** | | | | | | |
| Attempt deadline (C-4) | **Done 2026-11-01b** (§0c): one `AttemptDeadline` from the job deadline less a 60 s publication reserve | Reserve and minimum are defaults, not owner-set (O-2) | Owner may change `PUBLISH_RESERVE_S` / `MIN_INVESTIGATION_S` | O-2 (values only) | `tests/context/test_attempt_deadline.py`, worker test | No stage gets a fresh full timeout |
| Read budget (C-3, second half) | **Done 2026-11-01b** (§0c): separate validation reserve inside the global totals | — | — | — | `tests/context/test_read_budgets.py` | Validation never starved by tools |
| Multi-provider step 1 | Replay on tool-call turns only | Every assistant turn (incl. repair) with codec-owned replay | Generalise `SignedTurn`; loop keeps replay on all turns | Owner: O-5 replay exception | Contract suite: replay on text and repair turns | Anthropic/DeepSeek codecs possible |
| Multi-provider step 4b | **Done 2026-11-01b**: `CodecCapabilities` (none mode, replay scope, usage breakdown) checked when a provider is built | Output-cap semantics descriptive only | Token-based output budget | Step 1 | Contract suite | A codec needing replay on every turn is refused at construction |
| Usage persistence | In memory (result) | Operations record has totals only | Migration adding breakdown columns | Owner review of migration | Migration and ops tests | `ops report` shows cached and reasoning tokens |
| Observability | JSON logs, `ops report`, `ops alerts` | No metrics exporter or alert routing | Exporter and routing | Owner: host (T-1002/1003) | Soak | Alerts reach a channel |
| **Not implemented** | | | | | | |
| Anthropic, DeepSeek codecs | Contracts recorded (2026-11-01) | No codec | Codec per recorded contract; join contract suite | Step 1 (O-5); DeepSeek data-location review | Contract suite + codec tests | Offline contract passes; smoke authorised separately |
| Dead-job re-run (I-6) | None | Operator re-queue with audit | Command + audit event | Owner policy | DB tests | One audited re-run |
| Tool-call GitHub errors (I-3) | Abort into job retry | Policy | Map in `ToolBox.call` | Owner policy | Tool fault tests | Behaviour pinned |
| BYOK (tenant provider keys) | None; one operator key file per process | Storage, encryption, rotation, per-tenant limits | Design first (key custody, KMS or envelope encryption, rotation, audit) | Owner: custody model, threat review | Design review, then migrations and tests | No plaintext key at rest or in logs; per-tenant limits enforced |
| Dashboard / web UI for runs | None (the product surface is the Check Run and comment; `web/` is the project website) | Not an MVP need | None now | Product decision | — | — |
| Flaky-test, history, recurring failures | Lane history computed, not surfaced | Surface after a real model is live | Roadmap 3.5 | Real-model data | — | — |
| **Blocked by external setup or approval** | | | | | | |
| Real-model diagnosis | Fake provider only in the product | Activation | Preflight + `LLM_PROVIDER` enablement | Owner: A-1…A-7, T-605 | Benchmark targets AT-DX-15 | Targets met on the benchmark |
| Grants and retention (D-11, D-12) | **No revoke migration exists** (correction 2026-11-01b: earlier text said "prepared"; only a proposal in OWNER-DECISION-PACKET) | Write, review and apply | Migration revoking to per-role minimum | Owner | Privilege matrix | Matrix updated |
| "For AI agents" block (O-1), replay exception (O-5) | — | Policy | Render filter; DATA-INVENTORY entry | Owner | Render tests | Policy reflected |
| Scheduling (recovery, retention, alerts) | Commands exist | No schedule installed | Host cron/timers | Owner: host | — | Schedules run |

### 0d. Batch of 2026-11-01 (third session): attempt fencing, read-error classes, dead-job re-run

| ID | Status | Change | Tests |
|---|---|---|---|
| D-1 | **Fixed** (reproduced first) | Analysis, quota-notice, publication-state and ops-record writes verify ownership with `tracewise_job_owned` (migration 0012) inside their transaction, `FOR SHARE` until commit | `tests/db/test_attempt_fencing.py` (scenarios A, F, fence lock and tenant tests) |
| D-2 | **Fixed** (reproduced first) | `complete`, `fail`, `heartbeat`, `cancel_running` conditional on worker **and** attempt | scenarios B, C, D (incl. a reused worker id), E |
| D-A | **Fixed** | Per-file permanent errors → `unavailable`; `PermanentError` publishes the could-not-complete notice (not for credential faults) | `test_contents_api.py` (422, invalid JSON, token scope), `test_d_a_*` |
| D-B | **Fixed** | Transient reads retried in place (deadline-bounded); validation outage → `ValidationUnavailable` → retry, never a verdict | `test_read_budgets.py` (in-place retry, persistent outage), `test_d_b_*`, `test_contents_api.py` (retry, deadline) |
| I-3 | **Implemented** at the source boundary; `source_unavailable` outcome added (fourth batch): transient tree listing or transient tool reads behind an inconclusive result → retried, then "could not complete" | — | `tests/context/test_tool_errors.py` (source-unavailable cases), `tests/db/test_recovery_semantics.py` |
| I-6 | **Implemented**: `ops requeue`. Fifth batch: authenticated operator identity (database login), atomic in `tracewise_requeue` (0013), owner-only limit (2, provisional) | — | `tests/db/test_requeue.py` |
| D-11 | **Implemented** (fifth batch, migration 0015, option C) | Credential provisioning remains a deployment step | `test_privilege_matrix.py`, `test_least_privilege.py`, `test_rls.py` |
| Usage persistence | **Implemented** (fifth batch, migration 0014): NULL-aware breakdown and `usage_source` | — | `tests/db/test_usage_persistence.py`, `test_codec_contract.py` |
| O-2 per-request deadline | **Implemented** (sixth batch) | 600 s / 60 s / 3 attempts await owner confirmation | `tests/unit/test_github_deadline.py`, `test_analyze_worker.py::test_o2_*`, `test_publication_reconcile.py` |
| O-5 engine gaps | **Implemented** (sixth batch): binding, caps, masking, every-turn replay | Policy approval and provider data gates | `tests/investigate/test_replay.py` |
| D-12 purge | Dry run, per-run audit, live-run exclusion (0017); schedule documented, not enabled | Owner: enable the schedule; diagnosis period stays 90 d (D-12a) | `tests/db/test_retention.py` |
| F1 / D-14 publication recovery | **Implemented** (seventh batch): resumable publication; notice never overwrites a recorded analysis | Exactly-once remains impossible (documented) | `tests/db/test_publication_recovery.py`, `test_publication_reconcile.py` |
| G-PLAT-11 | **Fixed offline** (per-surface tokens) | Live S2 confirms GitHub's refusal response | `test_github_contracts.py::test_g_plat_11_*` |
| Registry/auth error lines in the pre-pass | **Fixed** (eighth batch): Docker-CLI `denied:`/`unauthorized:` lines; benchmark unchanged | — | `tests/unit/test_prepass_heldout_containers_auth.py` |
| OpenAI in the product | **Refused by design** (`providers.py`) | Owner approval (decision note `provider-data-approval-openai.md`) + small enabling change | `test_process_entrypoints.py` |
| D-C | **Fixed** (fourth batch) | Arguments bound before execution; categorised tool errors; defects raise `ToolInternalError` (never shown to the model as invalid arguments, never a diagnosis) | `tests/context/test_tool_errors.py`, `tests/db/test_recovery_semantics.py` |
| Stale publication (commit comment, digest cache) | **Fixed where GitHub permits** (fourth batch) | PR comment and Check Run reconciled on every later generation; commit comment cannot be edited (Contents write not requested): `superseded`, disclosed on the Check Run | `tests/db/test_publication_reconcile.py` |

Remaining boundary (documented, not a defect): a GitHub request in flight at the instant of takeover can be applied;
it is never recorded and the next owner adopts it (the write-once commit comment keeps the stale text).

### 0c. Batch of 2026-11-01 (second session): C-3, C-4, edge cases, capabilities, decision notes

| ID | Change | Tests |
|---|---|---|
| C-3 | `Limits.validation_reads` (64) and `validation_read_bytes` (4 MiB) are carved out of the unchanged global totals (4,000 reads, 24 MiB): tools draw on the rest, the validator only on its reserve. Same path, link and size rules for both (one `read(path, purpose=…)`). Budget denials are recorded in `files_skipped`; validator reads are cached per path; an exhausted reserve gives `location_validation_budget_exhausted` and the `validation_budget_exhausted` flag instead of the misleading `location_unreadable`. Reproduced first: 12 greps could ask for 4,800 reads and 96 MiB, draining the shared budget so a correct location came back unreadable. | `tests/context/test_read_budgets.py` (14) |
| C-4 | `analysis/attempt.py`: one `AttemptDeadline` per attempt = job `deadline_at` − 60 s publication reserve, converted once to the monotonic clock, immutable. Log streams stop at it (marked truncated, stream closed); jobs not reached are `jobs_not_downloaded`; the git fetch timeout is capped by it (skipped below 1 s); the investigation's timeout is min(configured, remaining) and it is not started below 10 s (`attempt_deadline_exhausted`, no provider spend). Validation and rendering are local and size-bounded; publication keeps the reserve and is not cut mid-POST. `Evidence.deadline_exhausted` makes a cut collection visible as truncated logs. | `tests/context/test_attempt_deadline.py` (8), `test_collect.py::test_c4_*`, `test_analyze_worker.py::test_c4_*` |
| 4A | H-1 now also removes a causal sentence that opens with a bare pronoun (it/this/that/these/those/they, not "this test/file/function…") directly after a sentence naming the push, commit, PR or change. Remaining limitation: a reference that comes *after* the causal sentence ("It caused X. The commit is abc.") is kept, as stripping it would also remove legitimate code descriptions. | `test_h1_a_causal_claim_split_*` (4), `test_h1_unrelated_causal_sentences_are_kept` (4) |
| 4B | Owner names: GitHub's documented Enterprise Managed User form `<name>_<shortcode>` (shortcode 3-8 alphanumerics, 39 characters in total) is accepted, in one shared pattern for webhook contracts and git/contents path checks. Basis: GitHub docs (username considerations for external authentication; abilities of managed user accounts: an app requesting no organization permissions can be installed on a repository the user administers; Tracewise's permissions are repository-only). GHE.com data-residency hosts (30-character limit) are out of scope: the API host is fixed to api.github.com. | `test_standard_and_enterprise_managed_owner_names_are_accepted` (7), `test_malformed_owner_names_and_references_are_refused` (14) |
| 4C | A token grant that omits `repositories` is now refused. The REST reference marks it optional without saying when it is present, and no live response is recorded; G-PLAT-13 added to the live plan (first token mint in S1). **Risk:** if GitHub omits it, every mint fails visibly. | `test_a_grant_that_omits_its_repositories_is_refused`, extended malformed cases |
| Step 4b | `CodecCapabilities` on each codec; `require_engine_support` refuses, at provider construction, a codec without a "none" mode or needing replay on every assistant turn (Anthropic A-38, DeepSeek D-27) until design step 1 exists. | `test_every_codec_declares_*`, `test_a_codec_the_engine_cannot_run_*` |
| Docs | `Message.replay` comment, `provider_view` docstring and DATA-INVENTORY claimed replay is redacted / never repository content; corrected (pending O-5). | — |

**Defects reported by the 2026-11-01 audits, not fixed (policy needed; see decision notes):**

- **D-A (confirmed, I-3; fixed 2026-11-01, §0d):** a permanent GitHub error other than 404/410/403 during a contents-API tool or validator read (422, other 4xx, invalid JSON, oversized response) ends the job `dead` with no notice to the user.
- **D-B (confirmed, I-3; fixed 2026-11-01, §0d):** a transient error during a validator read discards a finished model answer and repeats the whole investigation (model spend repeats).
- **D-1 (suspected, I-6; fixed 2026-11-01, §0d):** persistence and publication are fenced only by a worker-local lease flag; a worker whose lease was reaped and re-claimed can still persist and publish for a short window (longer while its heartbeat hits database errors).
- **D-2 (suspected, I-6; fixed 2026-11-01, §0d):** `complete`/`fail`/`heartbeat` check `locked_by` only, not the attempt; worker ids are not enforced unique.
- `usage_event` and `failure_signature` are never written (`add_usage`, `record_signature` have no callers).

Decision notes (proposals, nothing implemented): [I-3 and I-6](decision-notes/I-3-I-6-tool-errors-and-dead-jobs.md),
[D-11, D-12 and usage persistence](decision-notes/D-11-D-12-usage-persistence.md),
[O-5 reasoning-state replay](decision-notes/O-5-reasoning-state-replay.md),
[minimum observability](decision-notes/observability-minimum.md).

### 0b. Remaining edge cases in the verified fixes

- **H-1 (C-1):** *(4A, mostly closed 2026-11-01b; see §0c)* claims split across sentences ("Commit abc. It caused the failure.") separate the trigger reference
  from the causal verb, so the second sentence is not stripped. A sentence-level heuristic cannot catch pronoun
  references; the confidence rules and the evidence check still apply.
- **Repository names (M-9):** *(4B, closed 2026-11-01b)* the shared pattern rejects owner names with `_` (GitHub Enterprise managed-user
  accounts, e.g. `name_shortcode`). Such payloads are refused as `invalid_payload`. Owner decision whether to support
  them.
- **Token grants (T-1):** *(4C, now refused 2026-11-01b)* a grant whose `repositories` field is absent is still accepted; GitHub's documented response
  includes it when `repository_ids` is requested. Tightening needs one observed live response first.
- **Scope failure after mint:** a token minted but refused by `_verify_scope` stays registered with the scrubber (it is
  live for an hour); bounded by the number of such failures, never cached or used.
- **Workspace root (C-8):** the check is on the root only; the root's parent must itself be trusted (the default is
  the system temporary directory, sticky on Linux).
- **Third-party warning:** Starlette's `TestClient` deprecation warning remains; fixing it would add a dependency.

## 1. Capability status

| Capability | Status | Evidence |
|---|---|---|
| Webhook receipt, HMAC on the raw body, size caps | Verified (offline); partly observed live in S0 | `src/tracewise/web/webhooks.py`; `tests/db/test_webhook.py` (`test_sec02_*`, `test_declared_length_refused_before_reading`) |
| Durable queue: delivery, run and job in one transaction; dedupe; leases; reaper | Verified | `web/ingest.py`, `jobs/queue.py`; `tests/db/test_queue.py`, `test_webhook.py::test_evt05_*` |
| Recovery of missed deliveries and runs | Verified offline; live S1 steps 2 to 4 not run | `recovery.py`; `tests/db/test_recovery*.py` |
| Re-running a job that ended `dead` | **Missing** (dedupe key blocks re-ingest; no operator command) | `queue.py` dedupe; OWNER-DECISION-PACKET §4a follow-up |
| GitHub jobs and log retrieval (caps, redirect allowlist, pagination host lock) | Verified offline; log hosts not confirmed live (G-PLAT-8) | `github/client.py`; `tests/unit/test_github_client.py` |
| Deterministic pre-pass | Verified | `prepass/`; `tests/unit/test_primary.py`, `test_extractors.py`, `bench verify` |
| Investigation loop and budgets | Verified with scripted providers; **no real model** | `investigate/loop.py`; `tests/investigate/test_loop.py` |
| Read-only tool allowlist (`read_file`, `grep`, `list_dir`, `get_diff`) | Verified | `context/tools.py`; `test_tools.py::test_only_read_only_tools_exist` |
| Evidence validation and code-computed confidence | Verified offline; real-model quality unknown | `investigate/validate.py`, `confidence.py`; `tests/investigate/test_validate.py` |
| Report rendering, Check Run and comment publication with reconcile | Verified offline; partly observed live | `report/render.py`, `github/publish.py`; `tests/db/test_analyze_worker.py` |
| Tenant isolation (RLS, tenant plane) | Verified offline; `tracewise_app` holds excess grants (D-11) | `db/migrations/versions/0005_rls.py`; `tests/db/test_rls.py` |
| Secret redaction (logs, provider view, reports) | Verified, pattern-based only (P-4) | `prepass/sanitize.py`, `logging.py`; `tests/unit/test_logging.py` |
| Provider selection | Verified: product runs the fake only; `openai` refused; Gemini benchmark-only | `investigate/providers.py`; `tests/investigate/test_providers.py` |
| Real-model diagnosis | **Blocked** (owner approvals A-1 to A-7, T-605) | SMOKE-RUNBOOK §1 |
| Observability: JSON logs, `ops report`, `ops alerts` | Partial: no metrics exporter, no alert routing, cost NULL without prices | `ops.py`, `observe.py` |
| Scheduling of recovery, retention and alerts | Blocked (host) | deploy/staging/README.md step 11 |
| Live GitHub gates S0 to S5 | Partial: S0 observed with the fake provider; S1 step 1 only | LIVE-VALIDATION-PLAN.md |
| Flaky-test detection, failure history, dedupe of recurring failures | Missing (lane history computed but not surfaced, ADR-13) | `analysis/lane.py`; competitor-landscape §7 |

## 2. Defects fixed during this review (all reproduced first; regression tests added)

| ID | Defect | Fix | Regression tests |
|---|---|---|---|
| G-D1 | Gemini tool schemas sent under `parameters` (OpenAPI subset, no `additionalProperties`); every live request with tools would likely be refused | JSON Schema now sent in `parametersJsonSchema` (official reference, research record Addendum C) | `test_encode_maps_system_user_tools_and_limits`, `test_the_final_tool_free_step_also_uses_json_schema_declarations` |
| G-D2 | Gemini replay check failed when the investigator's provider-view redaction changed secret-shaped tool arguments (`grep password=\w+`) | Signed arguments compared as-is or after the same deterministic `redact` | `test_secret_shaped_arguments_survive_the_provider_view_redaction` |
| G-D3 | A rejected call to an undeclared tool broke the tool-free final step | Only known declarations kept; none invented | `test_a_rejected_call_to_an_undeclared_tool_does_not_break_the_final_step` |
| G-D4, G-D5 | A failed Gemini encode changed codec state (decode binding, conversation epoch) | State committed only after a successful encode | `test_a_failed_encode_changes_no_codec_state` |
| G-D6 | A Gemini model turn without `role` was accepted and replayed without one | `role: model` required | `test_a_model_turn_must_carry_the_model_role` |
| G-U | Gemini `toolUsePromptTokenCount` was ignored | Counted as input | `test_tool_use_prompt_tokens_count_as_input` |
| C-1 | H-1 causal-claim stripping bypassed by any dotted token (`pricing.py`): the claim was published unchanged | Sentences now end only at a terminator followed by whitespace or end of text | `test_h1_causal_claims_are_removed_even_when_they_contain_a_dotted_token` |
| C-2 | Delimiter neutralisation left `<<`/`>>` in runs of three or more | Every character of a run separated | `test_delimiter_neutralisation_leaves_no_double_angle_bracket` |
| C-5 | A batch of up to 12 tool calls could run past the investigation deadline | Deadline checked before each dispatch | `test_a_tool_batch_cannot_run_past_the_investigation_deadline` |
| C-6 | Every App JWT was registered with the log scrubber and never removed (unbounded growth, rising per-line cost) | JWTs no longer registered; the token pattern already redacts every JWT shape | `test_app_jwts_are_scrubbed_by_pattern_and_never_accumulate_in_the_scrubber` |
| C-8 | Git workspace root trusted without an ownership check (multi-user hosts) | Root must be a non-symlink directory owned by the worker's uid with mode 0700; otherwise the contents-API fallback is used | `test_a_workspace_root_that_is_not_private_is_refused_before_any_git` |
| C-9 | A redelivery POST answered 401 (expired JWT in a long pass) counted against the delivery's attempt cap | Mapped to `AppAuthenticationFailed`; the pass stops without recording an attempt | `test_app_post_maps_a_refused_jwt_to_app_authentication_failed`, `test_a_refused_app_jwt_stops_the_redelivery_pass_without_recording_an_attempt` |
| T-1 | A non-list `repositories` in a token grant raised `AttributeError` instead of a scope error | Shape checked; `TokenScopeError` | `test_malformed_repositories_in_a_grant_fail_closed` |
| T-2 | Log redirect port not checked | Port must be 443 (or absent) | `test_unsafe_log_redirects_refused_and_not_fetched` (two new cases) |
| M-9 | `workflow_run` repository names were not shape-checked | Shared `owner/repo` pattern (same as lifecycle events) | `test_workflow_run_repository_names_are_shape_checked` |
| R-1 | `REPORT_MAX_CHARS` had no upper bound (GitHub comments allow about 65,536 characters) | Bounded at 60,000 | `test_report_cap_has_an_upper_bound` |

## 3. Confirmed gaps not fixed (with reason)

| ID | Gap | Why not fixed now | Next step |
|---|---|---|---|
| C-4 | The 10-minute job deadline is not enforced inside an attempt (log downloads alone allow 5 × 300 s) | Splitting the budget across download, fetch and investigation is an owner choice (O-2) | Decide the split; then thread one attempt deadline through collection (M) |
| C-3 | **First half fixed 2026-11-01** (grep counts files not searched). Remaining: all reads (including the validator's) share one budget | Changes tool output the model sees; should be measured with a real model | Add skipped-file counts to grep output; cache validator reads (S) |
| C-7 | **Fixed 2026-11-01** (§0). Signed log URLs were opened up front and read later | Expiry behaviour unverified live | Open each stream just before reading (S) |
| I-3 | Tool calls over the contents API can raise rate-limit or 5xx errors that abort the analysis into a job retry | Whether to retry the job or continue with a failed tool result is a policy choice | Decide; map GitHub errors in `ToolBox.call` (S) |
| I-7 | **Fixed 2026-11-01** (§0): 30 s statement and 10 s lock timeouts. The publisher still holds a row lock across GitHub calls (by design; waiters now give up after 10 s) | Needs values chosen against real latency | Set conservative session timeouts with tests (S) |
| I-5 | Reconcile authorship fallback (`bot_login`) never wired; adoption relies on `performed_via_github_app.id` (G-PLAT-10, not captured live) | Wiring needs a startup `GET /app` (a live call) | Capture G-PLAT-10 in S1; then wire (S) |
| I-6 | Jobs that ended `dead` cannot be re-run | Policy follow-up recorded in the owner packet | Operator re-queue command with an audit trail (M) |
| O-1 | The "For AI agents" block republishes untrusted command text (fork PR authors control `run:`) | Owner policy | Omit for forks, warn, or filter (S) |
| O-5 | `Message.replay` reaches the provider unredacted (OpenAI reasoning items, Gemini signed turns) | Owner policy; required by the provider contracts | Record the accepted exception in DATA-INVENTORY (S) |
| D-11 | `tracewise_app` holds excess grants (more than the four tables first named: see decision note) | Owner approval; **the revoke migration has not been written** (correction 2026-11-01b) | Write the migration (option C in the decision note), then apply (S) |

## 4. Documentation and code mismatches found

Fixed in this review: CONFIGURATION (`REPORT_MAX_CHARS` range), MODEL-ADAPTER §3b (Gemini declarations, replay
binding, usage). Still to correct (documentation only): fake-provider outcome wording in OPERATIONS §8a and
PROJECT-HANDOFF §B; "not executed" headers in LIVE-VALIDATION-PLAN and SELF-HOSTING §3a; the `compose.local.yaml`
header (webhooks can reach it through a tunnel); `LLM_MODEL` listed as used by the worker (it is not read); Node is
required by `make check`/`make ci`; `make ci` does not run `web-e2e`; README says there is no frontend (`web/` exists);
`.env.example` pairs `TW_ENV=local` with the fake provider and settings never load `.env`; ARCHITECTURE §4.1/§4.3 and
DATA-INVENTORY describe the replay channel and network modules as they were before the model adapters; PROJECT-HANDOFF
§C/§E cite HEAD `1b62ab0`.

## 5. Developer-experience minimum

The smallest changes for a new developer: state that Node 20+ is needed for `make check`; set `TW_ENV=test` next to
`LLM_PROVIDER=fake` in `.env.example` and say settings come only from the process environment; add a throwaway App
key step to DEVELOPMENT §4.5; refresh PROJECT-HANDOFF to the current HEAD.
