# Security audit: 2026-10-19 (Phase 5)

Offline audit. No URL was fetched, no AWS or GitHub endpoint was contacted, and no secret value is reproduced here. Evidence comes from local commands on the repository and from a disposable Postgres cluster.

## 1. Pre-signed URLs in `research/final-audit-public/evidence/marketplace.html`

The file was inspected with a script that prints only structure: host, parameter names, counts, the key-ID prefix, a hash prefix and timestamps.

| Question | Verified answer |
|---|---|
| What is it? | A saved copy of a public GitHub Marketplace page, as served to an anonymous visitor. It contains 3 occurrences (2 distinct) of S3 SigV4 pre-signed URLs on `marketplace-screenshots.githubusercontent.com`, GitHub's screenshot proxy. |
| Material present | One `X-Amz-Credential` access key ID (prefix `AKIA`, a long-term key ID, belonging to GitHub's infrastructure, not to this project), `X-Amz-Signature`, `X-Amz-Date`, `X-Amz-Expires`, `X-Amz-SignedHeaders`, and a `jwt` parameter. **No** `X-Amz-Security-Token` and no secret access key. A key ID is an identifier, not a secret. The signature is a capability for the one object. |
| Expiry | Signed 2026-10-17T16:38:14Z with `X-Amz-Expires=300`, so it expired at 2026-10-17T16:43:14Z. The embedded JWT's `nbf`/`exp` give the same 5-minute window. |
| Current validity | **Not verifiable offline.** It could only be confirmed by fetching the URL, which was deliberately not done. S3 enforces `X-Amz-Expires` server-side, so the URLs should now be refused, but this is not proven. Even within its window, a URL granted read access only to a public screenshot. |
| Tracked / history | Tracked in the current tree. Added in `9c4fdd7` (2026-10-18), and that is the only commit that touches the key ID (`git log --all -S`). The repository has **no remote**, so it was never pushed by this project. |
| Elsewhere | Same key ID (matched by SHA-256 prefix `f1287e2b02f2`): no other tracked file. AWS signing parameters (`X-Amz-Signature`, `X-Amz-Credential`, `AWSAccessKeyId`, `X-Amz-Security-Token`): no other tracked file, and none in untracked or ignored files outside `.venv`. The quarantined directory was not read. |

**Severity: low.** The URLs are third-party, short-lived, read-only, already expired by their own terms, and only point at a public image. **Recommendation, for your review:**

- Before this repository is ever pushed, replace the query strings in that file with `?<redacted>`. This is a content edit to the evidence file, which needs your approval because the file is evidence.
- History rewrite: not recommended. There is no remote, and the material is not ours.
- Credential rotation: not applicable to us (GitHub's key), and nothing for us to rotate.

No change was made to the file.

## 2. Database boundaries (T-705 follow-up)

### Verified from code and migrations

| Item | Finding | Evidence |
|---|---|---|
| Planes | Tenant plane (`tracewise_app`, RLS): the analyze handler's `_load`, `_recheck` and `_persist`, and `Publisher._row`. Every one of those transactions passes `tenant=job.installation_id`, after `_load` checks that the payload installation equals the job row's. System plane (`tracewise_system`): web intake (`ingest`, `lifecycle`, `/readyz`), the worker's claim, heartbeat and finish, and `recovery`. | `grep transaction(` over `src/` (19 call sites); tests `test_rls.py`, `test_analyze_worker.py::test_t705_*` |
| Is cross-tenant access needed? | Yes for the queue claim (it orders all ready jobs and enforces a per-installation cap) and for recovery (it lists deliveries for the whole App and sweeps every installation). Intake records a delivery before any installation is validated, including `ping`, which has no installation. Intake could in principle run per tenant after the HMAC check; that was not changed. | `jobs/queue.py::claim`, `recovery.py`, `web/webhooks.py` |
| SQL construction | No dynamic SQL in runtime code. All values are bound parameters. The migrations use `format('%I', …)` only over constant arrays. | `grep` for f-string, `.format` and concatenated SQL in `src/` |
| Tenant context | `set_config(..., true)` is transaction-local, and non-positive or non-int ids are rejected. The context does not survive COMMIT or ROLLBACK on a reused pooled connection. | `test_rls.py` (10 tests) |
| Untrusted identifiers | Webhook ids are validated by Pydantic (positive ints, `owner/repo`), and only after the HMAC check. The sweep checks each run's own `repository.id`. | `contracts.py`, `web/lifecycle.py`, `recovery.py::_ingest_run` |
| Config separation | `DATABASE_URL` and `DATABASE_URL_SYSTEM` are separate `SecretStr` settings, and both are fed to the log redaction filter. | `config.py` |

### Defects found and fixed

| ID | Severity | Defect | Fix | Regression test |
|---|---|---|---|---|
| SA-1 | Medium | Both runtime roles had INSERT/UPDATE on `alembic_version`, because 0001's grant on ALL TABLES included it and 0005 copied it. Runtime code could change the recorded revision, so a later upgrade could skip or re-run migrations, RLS included. | Migration `0006` revokes INSERT, UPDATE, DELETE and TRUNCATE. SELECT is kept. Reversible. | `test_db_security.py::test_runtime_roles_cannot_write_migration_state_or_create_objects`, `::test_migration_0006_roundtrip` |
| SA-2 | Medium (configuration) | If `DATABASE_URL` were configured with the system or owner role, every tenant query would still work, but RLS would silently not apply. | `require_tenant_plane()` (in `db/session.py`) runs when `make_analyze_handler` is called. It raises `WrongDatabaseRole` for a superuser, a BYPASSRLS role or a table owner. The message gives the role name only, never the URL. | `test_db_security.py::test_tenant_plane_refuses_a_pool_that_bypasses_rls[system, owner]`, `::test_analyze_handler_cannot_be_built_on_the_system_pool` |
| SA-4 | **High** (found during T-706) | `httpx` logs every request URL at INFO (`HTTP Request: GET <url>`). That includes the 302 log-download URL with its signature query (`?sig=…`) and repository paths. `configure()` left the library at the root level (INFO), so in production signed log URLs would have been written to the logs. Earlier tests checked only for tokens. | `configure()` sets `httpx`, `httpcore` and `urllib3` to WARNING, and `SecretFilter.scrub` redacts every URL query string. | `tests/db/test_observability.py::test_no_secret_url_log_or_source_content_in_any_line`, which a mutation check showed fails when both fixes are disabled; `tests/unit/test_logging.py::test_url_query_strings_are_redacted_and_request_url_loggers_quieted` |
| SA-5 | **Medium** (Phase 11 audit) | `tracewise_purge()` is SECURITY DEFINER with `search_path = pg_catalog, public`. With `pg_temp` unlisted, PostgreSQL resolves the **caller's temporary tables first**. The system role (which has TEMP through PUBLIC) could create temporary `installation` and `job` tables and make the owner-privileged purge delete an **active** tenant's real rows. This was demonstrated before the fix. | Migration `0009` sets `search_path = pg_catalog, public, pg_temp`. Recommended deployment hardening, not done: revoke TEMP on the database from PUBLIC. | `test_retention.py::test_definer_function_ignores_caller_temp_tables`, `test_db_security.py::test_every_security_definer_function_pins_pg_temp_last_and_is_not_public`, `::test_migration_0009_roundtrip` |
| SA-6 | Low (Phase 11 audit) | `SecretFilter` scrubbed only top-level string fields, while `observe` allows flat dicts and lists. Nested strings (stage maps, flag lists, recovery `skipped` and `errors`) bypassed redaction. | Recursive scrubbing (values and keys, depth-capped) | `test_logging.py::test_nested_fields_are_scrubbed_at_any_depth` |
| SA-7 | Medium (Phase 11 audit) | None of the `python -m tracewise.{recovery,ops,retention}` entry points configured logging. INFO events were lost, and WARNING and above went through Python's last-resort handler **without** the secret filter or the quieted `httpx` loggers. An unreachable database ended in an unhandled traceback. | `logging.configure_cli()` runs in each entry point. Each CLI catches `DatabaseUnavailable`, emits `*.failed` and exits 1 with a JSON error. | `tests/db/test_cli_entrypoints.py` (5, real subprocesses) |
| SA-8 | Medium (Phase 14) | The log scrubber missed:<br>• percent-encoded URLs (`https%3A%2F%2F…%3Fsig%3D…`)<br>• `Authorization: Bearer/token …` header values, including in repr'd dicts<br>• bare `bearer <opaque>`<br>• `Cookie` and `Set-Cookie` headers<br>• bare `X-Amz-Signature=`, `sig=` and `token=` parameters in schemeless text | Five additional patterns in `SecretFilter.scrub`; benign metric text is unchanged | `test_logging.py::test_phase14_redaction_bypass_shapes` (10 shapes), `::test_redaction_keeps_benign_metric_text` |
| P-1 | **Medium** (Phase 23 privacy audit) | `problem_snippet` (up to 15 source lines and 4000 chars, copied by the system) and the model's `fix.replacement.new_text` were persisted in `analysis.diagnosis` **unredacted**; only the rendered GitHub report was redacted. A credential on the cited lines would have stayed in the database for 90 days, contrary to FS-SEC-3 ("redacted excerpts"). | Both are redacted at validation time, so the stored and rendered text match | `test_validate.py::test_stored_snippet_and_replacement_are_redacted` (failed before the fix) |
| SA-3 | Low (future change) | Nothing stopped a future migration from adding a tenant table without RLS. | A structural guard over a freshly migrated database: every table with `installation_id` must have RLS and `tenant_isolation`, and every other table must be on a reviewed allowlist. The system role must be able to SELECT every table. | `test_db_security.py::test_every_tenant_table_has_rls_and_the_policy_and_every_other_table_is_declared`. A mutation check showed that adding an unprotected tenant table, or an undeclared table, fails it. |

### Verified limitations (not defects; documented)

- RLS is not a defence against arbitrary SQL running as `tracewise_app`: that role can call `set_config` with any installation id. It protects against forgotten filters and wrong ids, not against code execution in the service.
- The system role bypasses RLS by design. A bug in system-plane code is therefore not contained by RLS. It is contained by the application checks (`ingest_scope`, D-9) and by GitHub token scoping.
- Unique constraints reveal that a key exists in another tenant. All such keys embed tenant-specific GitHub ids.
- `tracewise_app` keeps 0001's DELETE grant on `job`, `webhook_delivery`, `usage_event` and `failure_signature`, which the tenant plane never uses. RLS limits these to the tenant's own rows. Narrowing them further is recommended, but it changes the D-11 role model, so it is **left for review**.

### Not verifiable offline

- Real role provisioning, credential storage and network separation between the two URLs (deployment).
- Behaviour under a managed Postgres provider, which may restrict BYPASSRLS or `set_config` for custom GUCs.

## 3. Commands run

| Command | Result |
|---|---|
| Structure-only URL scan (scratch script) | Results in §1; no values printed |
| `git log --all -S <key id>`, `git grep` over AWS signing parameters | One file, one commit |
| Grant dump on a freshly migrated disposable cluster | SA-1 found |
| `pytest tests/db/test_db_security.py tests/db/test_rls.py tests/db/test_schema_repositories.py` | All pass |
| Full suite plus `make check` | See the CHANGELOG entry for this audit |

## 4. Phase 21 re-audit (2026-10-19, after the runnable runtime and model adapter core)

| Check | Result |
|---|---|
| SECURITY DEFINER purge: `search_path = pg_catalog, public, pg_temp`; guard over every definer function; EXECUTE only for the owner and the system role | Pass (`test_db_security.py`, `test_fresh_install.py`, `test_retention.py::test_definer_function_ignores_caller_temp_tables`) |
| Role template hardening (no TEMP, no CREATE for PUBLIC); fresh install; full downgrade and upgrade with an identical catalogue | Pass (`test_fresh_install.py`) |
| Tenant role cannot bypass RLS. The system role is confined: the worker refuses a non-BYPASSRLS system URL, and the web process and worker refuse wrong roles. | Pass (`test_rls.py`, `test_process_entrypoints.py`) |
| Scrubbing: nested fields, encoded URLs, Authorization, Bearer, cookies, signature parameters | Pass (`test_logging.py`) |
| No secret in errors from startup, worker, provider, recovery and purge | Pass (`test_process_entrypoints.py`, `test_http_adapter.py`, `test_cli_entrypoints.py`) |
| **No external network:** the whole suite (664 tests, including slow) was run under a session-wide socket guard that refuses any non-loopback, non-Unix connection | **0 attempts**. The guard was shown to fire on a probe. Subprocesses do not inherit it, but they reach only the database socket and loopback. |
| New tracked secrets | None. The only credential-shaped literals are labelled test placeholders. |
| Live validation plan | Not executed: there are no live-marked tests, and no request to github.com or a model vendor (guard above) |

No new defects were found in Phase 21. The Phase 18–20 findings are recorded in the CHANGELOG: the test-harness token issue and the network-guard allowlist entry for the adapter.

### Phase 23 review items (not changed)

- **P-2:** investigator tool results sent to a model provider (source windows, grep lines, the trigger diff) are not redacted; only logs are. The spec does not require it. Redacting them would limit what a third party receives, but it is a data-sharing decision, so it is left for your review. The privacy draft discloses it.
- **P-3 (spec conflict):** `problem_snippet` may be up to 4000 characters, while FS-SEC-3 says excerpts are ≤2 KB. It is now redacted, but its size limit is not aligned. Decide whether the 2 KB rule applies to source snippets.
- **C-CFG-1 (config/spec conflict, Phase 25):** `LOG_MAX_BYTES_PER_JOB` (Settings, default 2 MB; listed in IMPLEMENTATION-PLAN §4 and `.env.example`) is **not used** by any code. The effective cap is `Limits.max_log_bytes` = 512 MB per log, streamed in bounded memory. Wiring the 2 MB value would break AT-LOG-04, which requires a 200 MB log. Decide whether to remove the setting or to wire it with a value compatible with AT-LOG-04. Nothing was changed.

## 5. Phase 27 security and release gate (2026-10-19)

The gate suite was run as one group (259 tests) under the session-wide network guard, with **0 external connection attempts**.

| Gate item | Evidence (local tests and repository) | Result |
|---|---|---|
| SECURITY DEFINER: fixed `search_path`, `pg_temp` last; not executable by PUBLIC | `test_db_security.py::test_every_security_definer_function_pins_pg_temp_last_and_is_not_public`, `test_retention.py::test_definer_function_ignores_caller_temp_tables`, `test_fresh_install.py` | Pass |
| Runtime roles cannot alter `alembic_version` or create objects | `test_db_security.py`, `test_fresh_install.py::test_runtime_paths_work_on_the_clean_install` | Pass |
| Every tenant table has RLS and `tenant_isolation`; no undeclared table | `test_db_security.py` (schema guard, mutation-checked), `test_fresh_install.py` | Pass |
| Analysis and publication use the tenant role with tenant context | `test_full_chain.py` and `test_operator_acceptance.py` (per-transaction audit) | Pass |
| System operations use the system role, and wrong roles are refused | `test_process_entrypoints.py`, `test_reproducibility.py`, `test_db_security.py` | Pass |
| Scrubbing covers nested values, encoded URLs, Authorization, Bearer, cookies, signature and token parameters | `test_logging.py` | Pass |
| Startup failures of web, worker and CLIs do not leak secrets | `test_process_entrypoints.py`, `test_cli_entrypoints.py`, `test_fresh_install.py::test_bad_urls_*` | Pass |
| Recovery is bounded and restart-safe | `test_recovery.py`, `test_recovery_faults.py` | Pass |
| The purge never deletes in-flight work | `test_retention.py`, `test_adversarial.py::test_purge_alongside_jobs_in_every_state` | Pass |
| Model output cannot invoke shell, write, network or patch tools | `test_loop.py` (read-only registry; rejection before dispatch), `test_http_adapter.py::test_prompt_injection_*`, `test_github_client.py` (network confinement) | Pass |
| Stored diagnosis text is redacted (P-1) | `test_validate.py::test_stored_snippet_and_replacement_are_redacted` | Pass (fixed in Phase 23) |
| No credentials or signed URLs in new tracked files | Pattern scan of every line added since `890e806` | 0 matches |

**Not claimed:**
- The TEMP and CREATE revocation exists in the role template and is verified on disposable clusters. It has **not** been applied to any real database.
- No real credential has been provisioned (D-11).
- No live exploitation testing was done.

**Open review items from this run:** P-2, P-3, C-CFG-1 (§3 and §4 above).

## 6. Phase 29–32 findings (2026-10-19)

| ID | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| P-1 (re-verified) | — | Independent end-to-end check: 8 synthetic secret formats planted in the log, every model field (nested lists, replacement code, forbidden fields), a malformed first answer, a tool argument and a GitHub error body. **None** reached any table, any log line or any GitHub body. A mutation (removing the replacement redaction) is caught. | — | `tests/db/test_privacy_flow.py` |
| AT-SEC-04 gap | Low (coverage) | The "fake-provider request capture" half of AT-SEC-04 was untested | Test added; it holds | `test_model_input_privacy.py` |
| X-1 | Low (spec conformance) | Log excerpts were capped at 2048 **characters**, so non-ASCII could exceed "≤2 KB" (FS-SEC-3) | Redact, then cap at 2000 UTF-8 bytes | `test_validate.py::test_log_excerpts_are_at_most_2kb_*` |
| L-1 | **Medium** (evidence integrity) | A log cut by the 512 MB download cap was not flagged. With the failed step past the cut, `log_truncated` stayed false (FS-LOG-4 violated), so an incomplete log could be taken for complete evidence. | The stream exposes `truncated`; collection marks the job's log | `test_collect.py::test_download_cap_truncation_*` |
| C-CFG-1 | Resolved | The documented `LOG_MAX_BYTES_PER_JOB` is FS-LOG-4's retention budget; now wired, default unchanged | — | `test_collect.py::test_retention_budget_*`, `test_worker_main.py::test_worker_wires_*` |
| PR-1 gap | Low (coverage) | The fake provider's refusal was tested only for `TW_ENV=local` | `staging` and `prod` tested; openai refusal in every environment; no-fallback check | `test_providers.py` |
| P-4 | Limitation | Redaction is pattern-based; split or encoded secrets are not detected | Documented only | — |

P-2 and P-3 (snippet part) remain open: see DECISION-MEMOS.md.

## 7. Phase 35–41 independent verification (2026-10-19)

| ID | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| P-5 | **Medium** (privacy, secondary persistence) | `short_error()` stored `str(err)`. psycopg errors include `DETAIL: Failing row contains (...)`, and pydantic errors include `input_value=...`. A constraint or validation failure while persisting an analysis would therefore copy row content (diagnosis excerpts and snippet) into `job.last_error` or `publication.last_error`, which are kept 365 days, past FS-SEC-3's 90-day rule. It also broke the function's own "never log content" contract. Confirmed by probe: the row value appears in `str(e)`. | Only the class-level message is kept: the psycopg primary message plus SQLSTATE; the pydantic error count plus field locations | `test_schema_repositories.py::test_short_error_never_copies_row_or_input_content` |
| L-2 | Medium (report correctness) | With a truncated log and no error line, the report stated "the log has no error line … (only an exit code, timeout or kill)". If the error lay past the download cap or outside the retained budget, that statement was false. | Wording is conditional on `log_truncated`: "no error line was found in the retained part of the log …". The reason code is unchanged, so contracts and the benchmark are unaffected. | `test_render.py::test_truncated_log_without_error_line_never_claims_*` |
| — | Coverage | Download-cap boundaries (at the cap, one byte over, multibyte, empty); the excerpt cap on the full pre-pass path; structural proof that no code path reaches a real model | Tests added | `test_github_client.py`, `test_validate.py`, `test_providers.py` |
| W-1 | Low (robustness; found by the Phase 41 full gate) | The worker installed its graceful signal handlers only after startup (≈2.2 s: imports, role, schema and key checks, workspace sweep). A SIGTERM in that window, such as a quick orchestrator restart, killed it with the default action (exit −15), skipping graceful cleanup. Nothing could be claimed in that window, so no job was affected. The 2 s fixed sleep in two tests started failing as startup grew past 2 s. | Handlers are installed first (`worker.starting` event); a stop during startup closes resources and exits 0. The tests wait for events instead of sleeping. | `test_process_entrypoints.py::test_sigterm_during_startup_is_graceful` (fails with the old ordering), `::test_worker_starts_idles_and_stops_gracefully` |
| P-4 | Limitation (unchanged) | Pattern-based redaction misses split, encoded or unknown-format secrets | Not fixable by patterns. Possible mitigations, each a decision: entropy-based detection (false positives in hashes and ids); P-2 option C (do not read secret-looking files); customer guidance to keep secrets out of logs. | — |

Notes:
- `safe_error_text` in `github/client.py` is unused (dead code; no sink).
- The P-1 mutation check was re-run on a scratch copy and the source restored (see CHANGELOG).

## 8. Phase 43 final review (2026-10-19)

| ID | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| P-5b | **Medium** (privacy; completes P-5) | The P-5 fix kept PostgreSQL's *primary* message, the pydantic field locations, and `str(err)` for any other exception. Probes showed all three can carry input: `invalid input syntax for type integer: "<value>"`, extra and dict keys in locations, `KeyError("<content>")`. | Stored error text now depends only on uncontrollable parts: SQLSTATE plus schema identifiers; pydantic error count, model name and fixed error codes; Tracewise's own exception messages and callers' plain reason-code strings, which the code controls; otherwise the class name only. A first version also reduced plain reason strings to `str`, which broke 8 cancellation tests; the full gate caught it and it was corrected. The existing redact-and-cap test was moved to a Tracewise exception, and a class-only assertion added for foreign ones. | `test_schema_repositories.py::test_short_error_has_no_bypass_*` (failed before) |
| L-2b | Low (wording) | The L-2 wording said "the log was truncated" also when a job's log was **unavailable** | "incomplete (truncated or partly unavailable)" | `test_collect.py::test_l2_partly_unavailable_*` |
| W-1b | Coverage | The window between `worker.started` and the first claim was untested | — | `test_worker_main.py::test_signal_after_startup_but_before_the_loop_*` |
