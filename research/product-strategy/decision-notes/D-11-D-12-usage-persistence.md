# D-11 grants, D-12 retention, and usage-breakdown persistence

- **Date:** 2026-11-01
- **Status:** Proposal for owner decision; nothing implemented
- **Update (2026-11-01, fourth batch):**
  - **D-11 option C is implemented as migration 0015**, not 0012: that number went to the attempt fence. The access
    requirements were proven by the callers in §1.3 and by the full test suite running against the revoked grants.
  - **Usage persistence is implemented as migration 0014**, in a smaller form than §2.4: two nullable subsets and a
    `usage_source`, with no tool-use column and no generated total.
  - **Requeue identity is migration 0013.**
  - D-12 is unchanged: recommendations only (§1.14). Nothing was run against a real database.
- **Basis:** read-only audit of `main` at a738c61 plus the uncommitted working tree. No tests were run, no databases were started. Paths are relative to the repository root. Every statement about current behaviour cites file:line.

---

## Part 1: D-11 (excess grants) and D-12 (retention interpretations)

### 1.1 Correction to the planning documents

`implementation-gap-report.md:70` says "Migration prepared" and `:147` says "Apply the prepared migration". **No revoke migration exists.** `src/tracewise/db/migrations/versions/` holds 0001–0011 only, and the head is 0011 (`0011_analysis_quota.py`). Outside the migrations, `REVOKE` targeting `tracewise_app` appears only in `scripts/db/provision_roles.sql` (PUBLIC TEMP/CREATE) and in tests. The only text describing the migration is a *proposal* (`docs/internal/OWNER-DECISION-PACKET.md:51-53`). Before anyone can approve it, it has to be written (size S).

### 1.2 Current grants (as migrated through 0011)

These are the effective table grants. Sources: `0001_initial.py:175-179` (app), `0004_recovery.py:38`, then `0005_rls.py:43-51` (system grants, and app access to the recovery tables revoked), and `0006` (IUD/TRUNCATE on `alembic_version` revoked). `docs/DEPLOYMENT-BLUEPRINT.md:121-135` documents the same matrix, and `tests/db/test_privilege_matrix.py:44` checks it against the catalogue.

| Table | `tracewise_app` (RLS) | `tracewise_system` (BYPASSRLS) | RLS policy |
|---|---|---|---|
| alembic_version | S | S | none |
| installation | SIU | SIU | `id = tracewise_tenant()` (0005:30-31) |
| repository, workflow_run, analysis, publication | SIU | SIU | `installation_id = tracewise_tenant()` (0005:36-40) |
| audit_event | SI | SI | same |
| job, webhook_delivery, usage_event, failure_signature | **SIUD** | **SIUD** | same |
| recovery_checkpoint, redelivery_request | — | SIU | none (system only) |

Other grants: USAGE on every sequence for both roles (0001:178, 0005:46). EXECUTE on `tracewise_purge(integer)` goes to the system role only (0008:165-171). The function is SECURITY DEFINER and owned by the migration owner (0008:54-55), with its search path hardened in 0009.

### 1.3 Required runtime permissions, derived from the SQL each process runs

| Process (pool) | Tables and operations actually used | Evidence |
|---|---|---|
| web (system) | webhook_delivery I/U/S; installation I/U/S; repository I/U/S; workflow_run I/U (upsert); job I (enqueue) and U (`cancel_pending`); audit_event I; alembic_version S | `web/asgi.py:49-51`; `web/ingest.py:43-81`; `web/lifecycle.py:73-132`; `db/repositories.py:72-215`; `jobs/queue.py:116-118,235-263`; `web/health.py:31` |
| worker (system) | job S/U (claim, heartbeat, finish, retry, dead); alembic_version S | `worker.py:97,107-108`; `jobs/queue.py:128-277` |
| worker (tenant, `tenant=` set) | installation S and repository S (`repository_scope` join); workflow_run S/I/U; analysis S/I/U; publication S/I/U (including `FOR UPDATE`) | `jobs/handlers/analyze.py:103-105,125,234-260,287,387-420,427-428`; `github/publish.py:204-222`; `db/repositories.py:222-310,348-398,420-476` |
| recovery (system) | recovery_checkpoint S/I/U; redelivery_request S/I/U; webhook_delivery S; installation S; repository S; plus the ingest path for re-found runs | `recovery.py:115-122,202-252,283,351-366` |
| retention (system) | EXECUTE `tracewise_purge` only; no direct table DML | `retention.py:73`, `retention.py:106` |
| ops (system) | S on analysis, job, publication | `ops.py:75-150` |

**Migration-only (owner):** DDL, the `alembic_version` writes (0006), definer ownership of `tracewise_purge`, and every DELETE on analysis, publication, audit_event, workflow_run and repository. Those DELETEs happen only inside the definer function (0008:79-151).

**Findings not stated in the packet:**
- No runtime code issues a `DELETE` on any Tracewise table. Searching `src/tracewise` for `DELETE FROM` outside the migrations finds only the separate `waitlist` schema. So the **system role's** DELETE on the four tables (0005:45) is also unused.
- `usage_event` and `failure_signature` have **no runtime writer**. `add_usage` (`db/repositories.py:500-504`) and `record_signature` (`:481-497`) are never called. Only the purge function touches these tables (0008:91,108,130,141).
- The tenant plane never writes `installation`, `repository` or `audit_event`, yet the app role holds I/U on the first two and I on the third (0001:176).

### 1.4 Excess app grants and the concrete risk of each

These risks apply only to whoever controls a `tracewise_app` session, for example through an SQL-injection-style bug in tenant-plane code or a future process that holds only the tenant credential. The worker process holds **both** credentials (`worker.py:97-98`), so code execution inside the worker already gives the attacker the system role. Revoking the excess grants is defence in depth against tenant-plane bugs. It does not contain a compromised worker.

| Grant | Concrete risk |
|---|---|
| job **I** | `dedupe_key` is globally UNIQUE (0001:73) and predictable: `analyze:{repo_id}:{run_id}:{attempt}` (`contracts.py:85-88`). A tenant-scoped insert (RLS forces only `installation_id`) can squat another tenant's future key. That tenant's real run then reads as `duplicate_run` and is silently never analysed (`web/ingest.py:69-79`). A conflict also reveals that the key exists, which RLS cannot hide. Flooding queued rows degrades the shared claim scan (`jobs/queue.py:162-168`). A far-future queued row blocks the tenant's own purge forever (0008:119-124). |
| job **U/D** | A tenant could fake a `running` row whose `run_key` (`{repo}:{run}`, `web/ingest.py:75`) blocks claims for that run (`queue.py:165-166`), or rewrite and delete its own job history, which erases the operator evidence `ops.py` relies on. |
| webhook_delivery **I/U/D** | `delivery_id` is a global PK (0001:38). A pre-inserted GUID suppresses that delivery (`repositories.py:76-81`) and its redelivery (`recovery.py:202`). GUIDs are random, so this is low likelihood. A tenant could also erase its own intake record. |
| usage_event **I/U/D** | No writer today. Once usage feeds billing or quota, a tenant could forge or erase its own usage. |
| failure_signature **I/U/D** | No writer today. The PK is installation-scoped since 0010 (`0010:35`), so the risk is limited to the tenant's own rows. |
| installation **I/U**, repository **I/U** (not in the packet) | A tenant-plane bug could flip its own installation from `deleted` back to `active` or alter `purge_after`. That breaks D-10 terminality and the purge schedule (0008:119-125). It could also re-enable or rename its own repositories. |
| audit_event **I** (not in the packet) | A tenant could forge its own audit rows (`actor` is free text, 0001:165). |
| sequences USAGE on `job_id_seq` etc. | Harmless `nextval` gaps. |
| system **D** on the four tables | Unused (§1.3). The purge runs as the definer. |

### 1.5 D-11 options

- **A. Keep the current grants.** No work. Every risk in §1.4 stays.
- **B. Packet proposal** (`OWNER-DECISION-PACKET.md:51-53`): revoke all app privileges on `job` and `webhook_delivery`, and DELETE on `usage_event` and `failure_signature`. This removes the dedupe-squatting and queue risks, but leaves I/U on `installation`/`repository` and I on `audit_event`.
- **C. Least privilege from §1.3 (recommended).** The app keeps S on installation and repository, SIU on workflow_run, analysis and publication, and USAGE only on the sequences for workflow_run, analysis and publication. Revoke everything else, including `alembic_version` unless preflight needs it (today it does not: `preflight.py:205` runs only `require_tenant_plane`). Also revoke the system role's DELETE on the four tables. The downgrade re-grants exactly what 0001 and 0005 gave.
- **D. C plus separate processes:** a tenant-only analysis process without the system credential. This is architecture work and out of scope now.

**Recommendation: C, as migration 0012** (S effort). Update the matrix in `DEPLOYMENT-BLUEPRINT.md:121-135` in the same change, so that `test_privilege_matrix.py` stays green. Credential provisioning (the other half of D-11) stays a deployment step.

### 1.6 D-12: retention as implemented vs documented

| Data class | `tracewise_purge` (0008) | Docs | Match |
|---|---|---|---|
| analysis.diagnosis (excerpts) | NULL 90 d after `updated_at` (:70-72) | 90 d (DECISIONS D-12a; OPERATIONS §9; DATA-INVENTORY:20) | yes; whole document (interpretation a) |
| analysis row | deleted 180 d after `updated_at` (:76-83) | 180 d (ARCHITECTURE:70) | yes; `updated_at` is bumped by `record_analysis_ops` (`repositories.py:395`) |
| publication | deleted with its analysis (:79) | "with their analysis" | yes |
| usage_event | 365 d from `created_at` (:108); detached from purged analyses (:81) | 365 d (D-12b) | yes; no rows are ever written (§1.3) |
| audit_event | 365 d (:110); **kept** through tenant purge (:128-151 omits it) | D-12c | yes |
| webhook_delivery | 14 d from receipt (:86-87) | 14 d (ARCHITECTURE:67) | yes |
| job | terminal jobs 365 d after `finished_at`; non-terminal never (:102-104) | D-12b | yes |
| failure_signature | 365 d after `last_seen_at` (:91-92) | 365 d | yes; no writer |
| workflow_run | 365 d once unreferenced (:96-98) | D-12b | yes |
| installation | tombstone, no expiry; `account_login` cleared (:155) | D-12d | yes |
| Operational logs | not in the DB; Docker json-file rotation 10 MB × 3 per service (`deploy/staging/compose.yaml:15-19`) | DATA-INVENTORY:39 gives **no period** | **gap**: size-bounded, not time-bounded; host-dependent |

Implementation and documentation agree for every DB class. The open items are the four interpretations (`OWNER-DECISION-PACKET.md:12-24`) and the missing log period. The purge is unscheduled (`OPERATIONS.md:12`), so nothing is deleted in practice until a schedule exists.

### 1.7 Implications for token data and replay state

- Token counts live in two places. The `analysis.tokens_in/tokens_out/cost_usd` columns follow the 180-day analysis class. The copy inside `diagnosis.usage` (`contracts.py:265-271`) is cleared at 90 days under interpretation (a).
- **Replay is memory-only.** OpenAI reasoning items and Gemini signed turns live in `Message.replay`/`StepResponse.replay` (`investigate/provider.py:26-28,77`). The loop appends them only to the in-memory `messages` list (`investigate/loop.py:238`). The Gemini MAC epoch is a per-process random value (`gemini_generate.py:84`). Nothing under `db/` or `jobs/` references replay. The only "replay" hit in `db/repositories.py:114` refers to webhook replays. **No D-12 class is needed for replay.**
- **Documentation mismatch (O-5):** `DATA-INVENTORY.md:38,58` says replayed turns are redacted at the provider boundary. Replay items are in fact passed through unredacted (`investigate/loop.py:111`). This is recorded as O-5 (`implementation-gap-report.md:146`); see `decision-notes/O-5-reasoning-state-replay.md`.

### 1.8 Deletion and audit requirements

- The definer function is the only deletion path, and it is bounded, locked and date-free (0008:3-8,57,65). Any new table or column must either join a purge step or inherit its row's step. Columns added to `analysis` inherit step 2 automatically.
- A tenant purge writes a `tenant_purged` audit row (0008:156-158). Retention batches emit `retention.batch` events (`retention.py:86`) but **no audit row**; whether they need one is an owner question.
- Interpretation (c) means 365 days of content-free audit rows outlive a tenant purge. The privacy notice draft has to say so (`PRIVACY-NOTICE-DRAFT.md:60-68`).

### 1.9 D-12 recommendation

Accept (a)–(d) as implemented, with two additions:
1. Name an operational-log period, for example 14 days, enforced by the host. The rotation is size-based, not time-based.
2. State in the policy that usage and billing metadata belong to the 365-day class. This decides Part 2's long-term home.

Scheduling the purge is the step that actually enforces any period.

### 1.10 Tests for Part 1 (when implemented)

`test_privilege_matrix.py` (matrix doc updated), `test_least_privilege.py` (sequence and column grants), `test_rls.py:193` (add asserts that `job`, `webhook_delivery`, `usage_event` and `audit_event` are denied to the app; today the `SELECT id FROM job` at :202 is unreachable because the previous statement raises), a migration 0012 round trip modelled on `test_rls.py:221`, `test_fresh_install.py` (identical catalogue after downgrade and upgrade), and the full analyze and publish suites as the tenant role.

### 1.11 Owner questions

1. Approve option C (or B) for migration 0012?
2. Revoke the system role's unused DELETE too?
3. Accept D-12 (a)–(d)? Which operational-log period?
4. Should a retention run write an audit row?
5. Who provisions the three credentials, and from which secret store?

---

## Part 2: usage-breakdown persistence (design only)

### 2.1 Current state

- `StepUsage` (`investigate/provider.py:55-69`) has integer `input_tokens` and `output_tokens` totals, plus subsets `cached_input_tokens` and `reasoning_output_tokens` that default to **0**.
- OpenAI maps an absent detail to 0 (`openai_responses.py:171-179`). Gemini uses `.get(k, 0)` (`gemini_generate.py:264-266`). **Zero and unknown are indistinguishable.**
- Gemini `toolUsePromptTokenCount` is added into input (`gemini_generate.py:271`) and is not kept separately. Thoughts are added into output and also reported as the reasoning subset.
- The loop sums the subsets (`investigate/loop.py:228-231`). `InvestigationResult` carries them (`:86-90`), but `validate.py:322-329` builds `contracts.Usage` without them. **The breakdown is dropped before persistence.**
- Persisted today: `analysis.provider, model, tokens_in, tokens_out, cost_usd, latency_ms` (0001:104-109), written by `upsert_analysis` (`db/repositories.py:348-389`) from `analyze.py:413-420`.
- No-model analyses store `tokens_in = 0` rather than NULL, because `Usage` defaults to 0 (`validate.py:325-326`).
- `usage_event` is never written (§1.3).
- `cost_usd` prices all input at one rate, including cached tokens (`analyze.py:88-93`).

### 2.2 Risks

- Persisting a subset as 0 when the provider did not report it understates cache use and corrupts later cost analysis. NULL semantics have to be in place before any data is written.
- Putting the breakdown only in `diagnosis` JSON loses it at 90 days (interpretation a).
- Additive `Usage` fields: `_Strict` uses `extra="forbid"` (`contracts.py:31-32`). Stored diagnoses are never re-parsed (no `model_validate` on stored rows in `src/`), so old rows are safe. A rolled-back binary would still not be able to parse a new document if it ever tried.
- `require_schema_at` (`worker.py:108`; `db/session.py:130-134`) makes code and schema move in lockstep. Rollback means downgrading the migration and redeploying the old build together.

### 2.3 Options

- **A. Extend `analysis` (recommended now).** It is one row per analysis and is already tenant-readable under RLS (0005:36-40). It inherits the 180-day class and the purge step, and needs no new grants (`test_least_privilege.py:53` forbids column grants; new columns inherit the table grants).
- **B. A `usage_event` ledger** (one row per kind). It has 365-day retention and survives analysis deletion (0008:81). But its schema is untyped (`kind text, quantity numeric`, 0001:152-159), it has no writer, and its grants are exactly what D-11 changes. Revisit it for billing, after D-11 and D-12.
- **C. Only in `contracts.Usage`.** It is lost at 90 days. Rejected.

### 2.4 Proposed migration 0012 (or 0013 if the D-11 revoke lands first)

```sql
ALTER TABLE analysis
  ADD COLUMN input_tokens_cached     integer,  -- NULL = provider did not report it
  ADD COLUMN input_tokens_tool_use   integer,  -- Gemini toolUsePromptTokenCount; NULL elsewhere
  ADD COLUMN output_tokens_reasoning integer,
  ADD COLUMN tokens_total integer GENERATED ALWAYS AS (tokens_in + tokens_out) STORED,
  ADD COLUMN usage_source text CHECK (usage_source IN ('provider', 'partial', 'no_call')),
  ADD CONSTRAINT analysis_usage_subsets CHECK (
        (input_tokens_cached     IS NULL OR (tokens_in  IS NOT NULL AND input_tokens_cached     BETWEEN 0 AND tokens_in))
    AND (input_tokens_tool_use   IS NULL OR (tokens_in  IS NOT NULL AND input_tokens_tool_use   BETWEEN 0 AND tokens_in))
    AND (input_tokens_cached IS NULL OR input_tokens_tool_use IS NULL
         OR input_tokens_cached + input_tokens_tool_use <= tokens_in)
    AND (output_tokens_reasoning IS NULL OR (tokens_out IS NOT NULL AND output_tokens_reasoning BETWEEN 0 AND tokens_out))),
  ADD CONSTRAINT analysis_tokens_nonneg CHECK (tokens_in >= 0 AND tokens_out >= 0) NOT VALID;
-- DOWN: DROP CONSTRAINT analysis_tokens_nonneg, analysis_usage_subsets; DROP COLUMN usage_source, tokens_total,
--       output_tokens_reasoning, input_tokens_tool_use, input_tokens_cached.
```

**Semantics:**
- `usage_source` is NULL for legacy rows, which means unknown.
- `'no_call'` means no model was invoked. The totals are then genuinely 0, or NULL once the code is fixed.
- `'provider'` means every step reported usage.
- `'partial'` means the run ended mid-investigation (budget, timeout or provider failure after some steps), so the totals cover completed steps only.
- An aggregated subset is NULL unless **every** step reported that field.

The cached ≤ input check holds for Gemini too: cached is part of `promptTokenCount` (`gemini_generate.py:266`), and input = prompt + toolUse. Provider and model ids already exist as columns (0001:104-105). `tokens_total` is generated, so it cannot drift from the totals.

**Compatibility:**
- Every new column is nullable, so `ADD COLUMN` does not rewrite the table. Existing rows read as unknown.
- `NOT VALID` avoids scanning existing rows for the non-negativity check. Validating it later is optional.

**Tenant access:** RLS and grants are unchanged. The app (worker tenant plane) writes the columns and ops (system) reads them (`ops.py:100-104`). There is no tenant-facing reader today.

### 2.5 Code changes needed

1. `StepUsage`: make the subsets `int | None = None`, add `tool_use_input_tokens: int | None`, and guard `__post_init__` against None.
2. Codecs:
   - OpenAI: `_detail` returns None when the field is absent and 0 only when the provider sends 0.
   - Gemini: return None for an absent `cachedContentTokenCount`, `thoughtsTokenCount` or `toolUsePromptTokenCount`, while still adding present values into the totals.
   - The fake and bench providers (`bench/providers.py:29`) report subsets as None.
3. `loop.py`: aggregate with None propagation, and add `usage_source` to `InvestigationResult`.
4. `contracts.Usage`: add optional `cached_input_tokens`, `reasoning_output_tokens`, `tool_use_input_tokens` and `usage_source`, defaulting to None. This keeps them inside the `ValidatedDiagnosis` digest (`validate.py:114-125`). The change is additive, so `schema_version` can stay "2" (owner question). `validate.py:322-329` populates the new fields.
5. `upsert_analysis` and `analyze._persist`: pass the new columns. Optionally store NULL totals for `'no_call'`.
6. Out of scope here: `cost_usd` with a cached-input price, which needs a new price setting.

There are no JSON-schema snapshot files in the repo. Contract tests assert field values directly (`tests/investigate/test_codec_contract.py:232,245,278`).

### 2.6 Tests required

- Migration round trip and fresh-install catalogue identity.
- CHECK rejections: cached > in, reasoning > out, cached + tool_use > in, and a subset with NULL total. NULL subsets accepted. Legacy rows survive with NULLs.
- RLS: a tenant reads only its own breakdown (extend `test_rls.py:88`). The privilege matrix is unchanged.
- Retention: the columns survive the 90-day content clear and go with the row at 180 days (`test_retention.py:111,407`).
- Codecs: absent field gives None, an explicit 0 gives 0, and malformed input fails closed. Gemini tool-use is kept separately and still counted in input (`test_gemini_generate.py`, `test_codec_contract.py`).
- Loop: None propagation across steps, plus `usage_source` for each terminal outcome.
- Handler: persisted columns equal `Usage`, and no-call runs are stored as `'no_call'`.
- Ops report still parses.

### 2.7 D-12 dependency and recommendation

Option A does **not** depend on D-12. The new columns join the existing 180-day `analysis` class, the same class as today's `tokens_in` and `tokens_out`. D-12 (a) affects only the diagnosis copy. A 365-day usage ledger (option B) does depend on D-12 (b) and on D-11, because it changes `usage_event` grants.

**Recommendation:** implement option A now, as soon as a real provider is enabled, so that unknown and zero are never conflated in live data. Do it after the D-11 migration if that is approved first, to keep the migrations in a simple order. Defer the `usage_event` billing ledger until D-11 and D-12 are both decided.

### 2.8 Owner questions

1. Approve the `analysis` columns (option A) now and the ledger later?
2. Should `tokens_total` be generated, or store the provider-reported total (Gemini `totalTokenCount`)?
3. Should no-call analyses store NULL totals instead of 0 (a behaviour change for `ops report`)?
4. Should `schema_version` stay "2" for additive optional `Usage` fields?
5. Should the provider-returned model snapshot id be persisted alongside the configured model?


---

## 1.12 Privilege matrix after migrations 0012–0015 (implemented; tested)

S/I/U/D = SELECT/INSERT/UPDATE/DELETE, X = EXECUTE. The worker holds both runtime credentials. The web, recovery,
retention and `ops report|alerts` processes hold only the system one. `ops requeue` uses a personal operator login.
The migration role (`tracewise_owner`) owns every object, and so has all rights. RLS does not apply to it: tables are
not `FORCE ROW LEVEL SECURITY`.

| Object | `tracewise_app` (tenant plane: worker analysis and publication) | `tracewise_system` (web, worker queue, recovery, retention, ops) | `tracewise_operator` (personal logins) | Required because |
|---|---|---|---|---|
| installation, repository | S | SIU | — | tenant: scope and re-checks; system: lifecycle, ingest |
| workflow_run, analysis, publication | SIU | SIU | — | tenant: persist and publish; system: ingest, ops |
| job | — | SIU | — | queue (claim, heartbeat, finish); tenant asks via `tracewise_job_owned` |
| webhook_delivery | — | SIU | — | ingest, recovery |
| audit_event | — | SI (append-only) | — | lifecycle audit; requeue writes as definer |
| usage_event, failure_signature | — | SIU | — | no runtime writer today; kept for the purge and future use |
| recovery_checkpoint, redelivery_request | — | SIU | — | recovery |
| alembic_version | — | S | — | schema check (worker, preflight) |
| sequences | USAGE on workflow_run, analysis, publication | USAGE on all | — | inserts |
| `tracewise_job_owned(...)` (definer) | X | X | — | D-1/D-2 fence |
| `tracewise_purge(integer)` (definer) | — | X | — | retention |
| `tracewise_requeue(...)` (definer) | — | — | X | I-6 requeue |
| `tracewise_requeue_max_reruns()` | — | — | — (called by the definer) | policy value, owner-replaceable |

The definer functions are owned by the non-superuser owner and run with a fixed `search_path`
(`pg_catalog, public, pg_temp`, so `pg_temp` comes last and cannot shadow). PUBLIC is revoked on all of them.
- **RLS:** enabled with the `tenant_isolation` policy on every installation-scoped table, including those the tenant
  role can no longer reach (defence in depth).
- **Tests:** `test_privilege_matrix.py` (the documented matrix equals the catalogue), `test_least_privilege.py` (no
  runtime DELETE; tenant sequences; definers and their runners), `test_rls.py`, `test_requeue.py`,
  `test_fresh_install.py`.

**Remaining D-11 items (owner):**
- credential provisioning and the secret store;
- whether `usage_event` and `failure_signature` should be dropped while they have no writer;
- a tenant-only analysis process without the system credential (option D).

## 1.13 Data lifecycle matrix

| Data | Why stored | Repository-derived content? | Can be sensitive? | Needed for retries? | Needed for audit? | Deletable? | Retention today (purge, when scheduled) |
|---|---|---|---|---|---|---|---|
| installation | tenant identity, status, purge date | no (account login) | low (login, cleared on purge) | yes | yes | tombstone kept | no expiry; login cleared |
| repository | scope, enabled flag | name only | low | yes | yes | yes | with tenant purge |
| workflow_run | run identity, head SHA, branch | branch name | low | yes | no | yes | 365 d once unreferenced |
| job | queue state, `last_error` (content-free) | no | low | **yes** | partly (failure history) | yes | terminal: 365 d after finish |
| webhook_delivery | dedupe and replay defence | no | low | yes (dedupe) | no | yes | 14 d |
| analysis.diagnosis | the report and its evidence excerpts | **yes** (log and code excerpts, redacted) | **yes** | no (never reused across attempts) | no | yes | cleared at 90 d |
| analysis row (status, usage counts, cost) | ops report, quota | no | low | no | partly | yes | 180 d |
| publication | GitHub object ids, digest (no text) | no | low | **yes** (reconcile) | no | yes | with its analysis |
| audit_event | who did what (lifecycle, requeue actor) | no | low (operator login) | no | **yes** | yes | 365 d; survives a tenant purge |
| usage_event, failure_signature | no writer | — | — | no | no | yes | 365 d |
| provider continuation state | — | — | — | — | — | — | **never persisted** (memory, one investigation) |
| operational logs | debugging, alerts | no content by design (event deny-list) | low | no | partly | host | size-rotated only (gap) |

## 1.14 D-12 recommendation (unchanged in substance)

- Accept the implemented classes (a)–(d).
- Add a time-bounded log period, for example 14 days, enforced by the host.
- **Schedule the purge.** Until it runs, nothing is ever deleted.
- Keep audit records 365 days and through a tenant purge. They now carry operator logins, which the privacy notice
  must mention.
- Do not add irreversible deletion before the owner approves the periods.
- Any deletion stays inside `tracewise_purge`, which is tenant-scoped by construction.

## 1.15 Update (2026-11-02, sixth batch): what retention now does

| Data | Change |
|---|---|
| analysis, publication, workflow_run of a run with a live job | Never purged while the job is queued, waiting or running (0017) |
| audit_event | Gains a `retention.run` row per real purge run (counts only), and still carries operator logins on requeue rows. Retention 365 days, kept through a tenant purge |
| analysis.usage_source | Legacy rows backfilled to `no_call` only where the code proves it (0016) |
| operational logs | 14-day host procedure documented (journald `MaxRetentionSec`); not applied: a host change |
| analysis.diagnosis (log-derived excerpts) | **Unchanged at 90 days (D-12a).** The 14-day recommendation was for operational logs. Shortening the excerpt period needs an explicit owner decision |

The purge has a `--dry-run`, which is exact and rolled back. Scheduling follows
the existing cron convention (deploy/staging README step 13, daily). The schedule is not enabled.
