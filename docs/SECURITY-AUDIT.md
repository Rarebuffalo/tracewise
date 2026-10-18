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
