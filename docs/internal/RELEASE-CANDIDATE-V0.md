# Tracewise V0 release candidate: commit plan, staging gates, acceptance (prepared 2026-11-02; nothing executed)

Status words used here:
- **Implemented:** code exists.
- **Offline verified:** tests on disposable infrastructure with fakes.
- **Staging verified / Production verified:** real evidence. **None yet.**
- **Blocked:** cannot proceed without a missing input.
- **Requires owner decision:** a policy or approval only the owner can give.

## 1. Commit plan (for approval; nothing is staged)

Base: `main` at `a738c61`. The groups below are the review units. **Measured buildability** (2026-11-02; each
state is an export of `HEAD` with the groups overlaid, then mypy and the full pytest suite):

| State | Result |
|---|---|
| 1 | fails (`test_migrations_0012_0017`: needs group 5) |
| 1–2 | fails (`test_observability` cost test: needs group 5) |
| 1–3 | fails (`test_attempt_fencing`: needs group 5) |
| 1–4 | fails (same) |
| **1–5** | **passes**: 1,898 tests, mypy, ruff, docs check |
| 1–6 | passes (the current tree; final `make ci`) |

Options (owner decision):
- **(A) six commits:** rejected. Four intermediate commits would be knowingly broken, which bisection and reverts
  depend on not being the case.
- **(C, recommended) two commits:**
  1. "V0 release candidate: migrations, queue, publication, investigation, tests" = groups 1–5. Builds and passes on
     its own.
  2. "V0 documentation and records" = group 6. Documentation only; reverting it cannot break the code.

  Reviewers still read by group: the table below is the review map.
- **(B) one atomic commit:** groups 1–6. The simplest revert, but documentation and code are mixed.

Either way: add untracked paths (`??`) by name, never `git add .` or `-A`. Migrations 0012–0017 travel together in
the code commit. Their order is enforced by Alembic's `down_revision` chain, not by the commits.

| # | Group | Paths | Depends on |
|---|---|---|---|
| 1 | Database migrations and permissions | `src/tracewise/db/migrations/versions/0012_job_attempt_fence.py` ?? · `0013_operator_requeue.py` ?? · `0014_analysis_usage_breakdown.py` ?? · `0015_least_privilege.py` ?? · `0016_usage_source_backfill.py` ?? · `0017_purge_skips_live_runs.py` ?? · `src/tracewise/db/session.py` · `src/tracewise/db/repositories.py` · `scripts/db/provision_roles.sql` · `tests/pg.py` · `tests/db/test_migrations_0012_0017.py` ?? · `tests/db/test_least_privilege.py` · `tests/db/test_fresh_install.py` · `tests/db/test_rls.py` · `tests/db/test_cross_phase.py` · `tests/db/test_phase50_transfer.py` · `tests/db/test_session_timeouts.py` ?? · `tests/db/test_process_entrypoints.py` · `docs/DEPLOYMENT-BLUEPRINT.md` (its privilege matrix is checked by a test) | — |
| 2 | Queue, fencing, requeue, retention, operations | `src/tracewise/jobs/queue.py` · `src/tracewise/jobs/worker.py` · `src/tracewise/requeue.py` ?? · `src/tracewise/ops.py` · `src/tracewise/retention.py` · `src/tracewise/recovery.py` · `src/tracewise/config.py` · `.env.example` · `tests/db/test_queue.py` · `tests/db/test_requeue.py` ?? · `tests/db/test_retention.py` · `tests/db/test_recovery_faults.py` · `tests/db/test_quota.py` · `tests/db/test_observability.py` · `docs/CONFIGURATION.md` | 1 |
| 3 | GitHub client and publication | `src/tracewise/github/client.py` · `src/tracewise/github/errors.py` · `src/tracewise/github/endpoints.py` · `src/tracewise/github/auth.py` · `src/tracewise/github/publish.py` · `src/tracewise/report/render.py` · `src/tracewise/contracts.py` · `src/tracewise/context/paths.py` · `src/tracewise/web/lifecycle.py` · `tests/github_fake.py` · `tests/github_state.py` · `tests/unit/test_github_client.py` · `tests/unit/test_github_deadline.py` ?? · `tests/unit/test_github_auth.py` · `tests/unit/test_contracts.py` · `tests/db/test_github_contracts.py` · `tests/db/test_publication_reconcile.py` ?? · `tests/db/test_attempt_fencing.py` ?? · `tests/investigate/test_phase50_links_and_markers.py` | 2 |
| 4 | Investigation, tools, provider protocol, pre-pass | `src/tracewise/analysis/attempt.py` ?? · `src/tracewise/analysis/collect.py` · `src/tracewise/analysis/diagnose.py` · `src/tracewise/context/source.py` · `src/tracewise/context/contents_api.py` · `src/tracewise/context/gitfetch.py` · `src/tracewise/context/provider.py` · `src/tracewise/context/tools.py` · `src/tracewise/investigate/replay.py` ?? · `src/tracewise/investigate/loop.py` · `src/tracewise/investigate/provider.py` · `src/tracewise/investigate/http_adapter.py` · `src/tracewise/investigate/openai_responses.py` · `src/tracewise/investigate/gemini_generate.py` · `src/tracewise/investigate/prompt.py` · `src/tracewise/investigate/validate.py` · `src/tracewise/prepass/extractors/generic.py` · `scripts/openai_smoke.py` · `tests/context/test_attempt_deadline.py` ?? · `tests/context/test_read_budgets.py` ?? · `tests/context/test_tool_errors.py` ?? · `tests/context/test_collect.py` · `tests/context/test_contents_api.py` · `tests/context/test_gitfetch.py` · `tests/context/test_tools.py` · `tests/investigate/test_replay.py` ?? · `tests/investigate/test_codec_contract.py` ?? · `tests/investigate/test_loop.py` · `tests/investigate/test_validate.py` · `tests/investigate/test_gemini_generate.py` · `tests/investigate/test_http_adapter.py` · `tests/investigate/test_openai_smoke_harness.py` · `tests/unit/test_prepass_heldout_containers_auth.py` ?? · `tests/report/test_report_outcomes.py` ?? · `docs/MODEL-ADAPTER.md` · `docs/architecture/multi-provider-design.md` ?? · `src/tracewise/bench/report.py` · `tests/bench/test_harness.py` · `src/tracewise/investigate/confidence.py` · `tests/bench/test_review_items.py` | 3 |
| 5 | Analysis handler (ties 1–4 together) | `src/tracewise/jobs/handlers/analyze.py` · `tests/db/test_analyze_worker.py` · `tests/db/test_phase50_reliability.py` · `tests/db/test_recovery_semantics.py` ?? · `tests/db/test_publication_recovery.py` ?? · `tests/db/test_usage_persistence.py` ?? · `tests/db/test_operator_acceptance.py` | 1–4 |
| 6 | Operations documentation and records | `docs/internal/RELEASE-CANDIDATE-V0.md` ?? · `docs/LIVE-VALIDATION-RUNBOOK.md` ?? · `docs/BENCHMARK.md` · `docs/DECISIONS.md` · `deploy/staging/README.md` · `deploy/staging/compose.local.yaml` · `README.md` · `docs/README.md` · `docs/ARCHITECTURE.md` · `docs/OPERATIONS.md` · `docs/DATA-INVENTORY.md` · `docs/PRIVACY-NOTICE-DRAFT.md` · `docs/CHANGELOG.md` · `docs/GITHUB-CONTRACT-AUDIT.md` · `docs/LIVE-VALIDATION-PLAN.md` · `docs/internal/OWNER-DECISION-PACKET.md` · `docs/internal/PROJECT-HANDOFF.md` · `docs/DEVELOPMENT.md` · `docs/SELF-HOSTING.md` · `docs/SMOKE-RUNBOOK.md` · `research/README.md` · `research/gemini-api-reference-2026-10-26/README.md` · `research/anthropic-api-reference-2026-11-01/` ?? · `research/deepseek-api-reference-2026-11-01/` ?? · `research/product-strategy/implementation-gap-report.md` ?? · `research/product-strategy/decision-notes/` ?? | 1–5 |

**Not in the release:**
- `.claude/`, `marketing/` and `tracewise-brand/` (protected, never staged).
- The competitor landscape, product strategy and feature roadmap drafts: kept outside the repository (owner
  decision, 2026-11-21), together with the competitor audit and evidence that research/ used to hold.

Checked before this plan:
- no secret-shaped strings in the diff or the untracked files;
- no generated or cache files among the paths;
- `git diff --check` clean.

## 2. Staging execution (Gates A–C; none executed; each gate needs explicit approval)

Legend: **[W-DB]** writes the staging database; **[W-HOST]** changes host or service state (downtime); **[W-GH]**
writes to GitHub (`tw-live` only); **[RO]** read-only. Commands are the staging README's (directory
`deploy/staging`, `TW_SECRETS_DIR` set, profile `jobs` for one-off jobs). Card ids refer to
[LIVE-VALIDATION-RUNBOOK.md](../LIVE-VALIDATION-RUNBOOK.md).

### Gate A: staging database (downtime from A-3 to A-8)

| Step | Action | Expected output | Evidence | If it fails |
|---|---|---|---|---|
| A-1 [RO] | `docker compose --profile jobs run --rm migrate status` | JSON with the current revision. The repository's last record is `0011`; anything else, stop and reconcile first | the JSON | stop |
| A-2 [RO] | `pg_dump -Fc` as the owner into the backup location; then `pg_restore --list` on the file | dump exits 0; the list shows tables and functions | file size, checksum, `--list` excerpt | stop: no upgrade without a verified backup |
| A-3 [W-HOST] | `docker compose stop web worker` | both `Exited` | `docker compose ps` | restart them; stop |
| A-4 [W-DB] | create `tracewise_operator` (README "Upgrading…", step 3) | `CREATE ROLE` | psql output | none needed (idempotent check: `\du`) |
| A-5 [W-DB] | `docker compose --profile jobs run --rm migrate upgrade` | `"after": "0017"` | the JSON | re-run (each revision is one transaction). If it fails again: restore A-2 and keep the old build (OPERATIONS §8b) |
| A-6 [RO] | `migrate status`; `preflight` | `"at_head": true`; preflight exit 0 | both outputs | stop; do not start services |
| A-7 [RO] | as the superuser: `\du`, `\dp` on `job`, `analysis`, `audit_event`; `SELECT proname, prosecdef, proconfig FROM pg_proc WHERE proname LIKE 'tracewise_%'` | grants equal DEPLOYMENT-BLUEPRINT §6; three definers with `search_path=pg_catalog, public, pg_temp`; `tracewise_requeue` executable by `tracewise_operator` only | the outputs | stop; restore A-2 if wrong |
| A-8 [W-HOST] | `docker compose up -d web worker proxy`; `curl …/healthz`, `…/readyz` | 200, 200; `worker.started` | logs | `/readyz` names the cause (`schema_mismatch`, `wrong_database_role`) |
| A-9 [W-DB] | operator logins (OPERATIONS §2a), then `ops requeue … --dry-run` with a nonexistent job id | `{"outcome": "not_found", "actor": "operator:ops_<name>"}` | the JSON | fix the login or the grant |

### Gate B: real GitHub integration (fake provider; `TW_ENV=test`)

| Step | Action | Expected output | Evidence | External writes |
|---|---|---|---|---|
| B-1 | G-1: install the staging App on `tw-live` only | `installation` row `active`; one `repository` row | `webhook.ingested`, SQL | **[W-GH]** install |
| B-2 | W-4: a delivery with a wrong signature | 401; no row | `webhook.signature_rejected` | none |
| B-3 | G-2 / W-1 / L-1: push a failing commit (`tw-live` fixture) | one job; the token is restricted to `tw-live` (no `TokenScopeError`); the log is downloaded via the redirect; an analysis is recorded | events; `job`, `analysis` rows | **[W-GH]** commit, Check Run, commit comment |
| B-4 | W-2 / W-3 / W-5: redeliver; re-run in GitHub; redeliver an older `in_progress` | `duplicate_delivery`; `duplicate_run`; no new job; the completed result stands | outcomes | **[W-GH]** re-run |
| B-5 | L-3 / L-5 / L-6: the large-log variant; remove and restore Actions read | truncated flag; `permission_denied` notice; rate limits observed only if they occur | analysis limits; Check Run text | **[W-GH]** permission change, Check Runs |
| B-6 | pagination: the job list of a run with more than 100 jobs is out of fixture scope; record "not exercised" unless the owner adds such a workflow | — | — | — |
| B-7 | P-1, P-2, P-3: Check Run, commit comment, PR comment | one object each; in place on re-run | GitHub ids in `publication` | **[W-GH]** |
| B-8 | cleanup | delete test branches and PRs (keep the App for C) | — | **[W-GH]** |

### Gate C: fake-provider end to end (`TW_ENV=test`)

With `LLM_PROVIDER=fake`, every model step fails, so the provider path ends "could not complete". The diagnosis path
without a model is the "exit 1 only" fixture (`inconclusive`, `no_error_line`, published as a completed analysis).

| Step | Cards | Expected | Evidence | External writes |
|---|---|---|---|---|
| C-1 | I-6 | inconclusive report with no model call, `usage_source = no_call`; commit comment and Check Run | `analysis` row; GitHub objects | **[W-GH]** |
| C-2 | R-3 | traceback fixture: 3 attempts, then "could not complete" (Check Run only) | `job.failed` ×2, final outcome | **[W-GH]** |
| C-3 | P-7 | declined Pull requests write: PR comment refused; commit comment and Check Run published; the Check Run names the permission | publication states | **[W-GH]**; permission change |
| C-4 | P-4, P-5, P-8 | SIGKILL during publication: the object is adopted, never duplicated; a write that cannot start → `publication.not_started` | events, object count | **[W-GH]**, **[W-HOST]** |
| C-5 | R-1, R-2, R-8 | crash and stale worker: takeover; stale writes refused; publication resumed without re-investigation | `job.stale_attempt_*`, `analysis.publication_resumed` | **[W-HOST]**, **[W-GH]** |
| C-6 | R-4, R-5 | requeue as an operator (dry run, then real); refused for service roles and a wrong `--operator` | JSON; `audit_event` | **[W-DB]**, **[W-GH]** |
| C-7 | R-7 | retention `--dry-run`, then a real run | exact counts; a `retention.run` audit row | **[W-DB]** deletes |
| Cleanup | — | uninstall the App if nothing follows; restore permissions | — | **[W-GH]** |

### Gates D and E

- **D (real OpenAI):** Blocked. Decision packet: [decision note §5](../../research/product-strategy/decision-notes/provider-data-approval-openai.md).
- **E (production evidence):** after B–D. Needs:
  - real-run accuracy against the owner's chosen bar;
  - a restore drill on a copy;
  - alert routing;
  - the retention schedule;
  - the release and rollback plan.

  Production stays observation-only until a separate release decision.

## 3. Scenario coverage

Column meanings:
- **Pre-pass:** deterministic, offline verified.
- **Pipeline:** scripted provider, end to end, offline verified.
- **Validation:** the evidence validator's behaviour.
- **Real model:** always **required** before any quality claim.

| Scenario | Pre-pass | Pipeline | Validation | Evidence |
|---|---|---|---|---|
| Dependency failures | yes | yes | yes | B-05, B-06, B-17 (benchmark); A-04 held-out |
| Test failures | yes | yes | yes | B-02, B-03 |
| Lint and type check | yes | yes | yes | B-01, B-10 |
| Build and container | yes | no benchmark case | — | held-out `test_prepass_heldout_containers_auth.py` |
| Registry and authentication | yes (2026-11-02 fix) | no benchmark case | — | held-out tests (positive, negative, misleading) |
| Missing configuration | yes | yes | yes | B-07, B-08 |
| Runner and infrastructure | yes | yes | yes | B-09, B-14 |
| Timeouts | yes | yes | yes | B-13; `test_attempt_deadline.py` |
| Incomplete logs | yes | yes | yes | A- and E-cases; L-3 |
| Multiple failures | yes | yes | yes | B-11, B-12 |
| Contradictory evidence | — | yes | yes | B-17 trap; validator rule tests (`test_validate.py`) |

Scripted oracle run on 2026-11-02: 39 runs executed, 4 not applicable (P2), 0 errored. Outcomes: 21 correct,
3 partial, 5 justified abstentions, 0 wrong, 1 overconfident; identical before and after the pre-pass change. After
the B-04 cap (2026-11-03): 22 correct, 3 partial, 5 justified abstentions, 0 wrong, 0 overconfident, no safety
failures. B-04 C1 was the only per-case change. All of this is protocol validation, not model quality. The reports are checked by `tests/report/test_report_outcomes.py`:
a diagnosis names the location and a concrete fix; anything else says why and makes no causal claim.

## 4. V0 acceptance matrix

Status:
- **Offline verified** = tests on disposable infrastructure with fakes.
- **Staging verified** / **Production verified**: none yet.
- **Requires owner decision** where a bar or policy is needed. No threshold is assumed.

| # | Requirement | Implementation | Verification and evidence | Pass criteria | Status | Remaining |
|---|---|---|---|---|---|---|
| 1 | Webhook authentication and intake | `web/webhooks.py` (body cap, HMAC before parse), `web/ingest.py` | `test_webhook.py`; B-2, B-3 | 401 on a bad signature; one job per failed run attempt | Offline verified | Gate B |
| 2 | Duplicate and out-of-order delivery | unique delivery and dedupe keys; `recovery.py` sweep | `test_webhook.py`, `test_recovery*.py`; B-4, W-6 | no second job; missed deliveries recovered once | Offline verified | Gate B |
| 3 | Durable queue and attempt fencing | `jobs/queue.py`, `tracewise_job_owned` (0012) | `test_attempt_fencing.py`, `test_queue.py`; C-5 | stale attempts change nothing | Offline verified | Gate C |
| 4 | GitHub log retrieval | `analysis/collect.py`, `RepoClient.job_log_lines` (redirect allowlist, caps, deadline) | `test_github_client.py`, `test_github_deadline.py`; B-3, B-5 | log anchored; truncation flagged | Offline verified | Gate B |
| 5 | Deterministic failure analysis | `prepass/` | `test_primary.py`, held-out tests, benchmark Track A 7/8 checks | observed lines only; no inferred cause | Offline verified | Gate B (real logs) |
| 6 | Read-only repository context | `context/tools.py` (four tools, path, budget and deadline rules) | `test_tools.py`, `test_tool_errors.py`, `test_read_budgets.py` | no write, execute or network tool; categorised errors | Offline verified | Gate C |
| 7 | AI provider contract | `investigate/loop.py`, `http_adapter.py`, `openai_responses.py`, `replay.py` | codec contract and replay tests; I-1 to I-7 | bounded steps; fail closed; state bound and capped | Offline verified; product selection refused | **Blocked** (gate D packet) |
| 8 | Evidence validation | `investigate/validate.py`, `confidence.py` | `test_validate.py`; benchmark Track C 22/25 | no unvalidated location or cause published | Offline verified | gate D (the B-04 cap was applied 2026-11-03: `flaky_suspect` ≤ medium) |
| 9 | Diagnosis and report quality | `report/render.py` | `test_report_outcomes.py`; scripted benchmark (protocol only) | a diagnosis has a location and a concrete fix; otherwise a reason and no cause | Offline verified (format); quality **not measured** | **Requires owner decision** on the bar (options: the benchmark's correct-or-justified share; zero high-confidence wrong; per-category minimums), then gate D |
| 10 | Check Run | `Publisher.check_run` (`publish_checks` token) | `test_publication_reconcile.py`, contracts tests; B-7 | one neutral Check Run, updated in place | Offline verified | Gate B |
| 11 | Commit comment | `Publisher.commit_comment` (`publish_commit`, Contents read) | contracts tests; B-7, G-PLAT-5 | one write-once comment; never edited | Offline verified; Contents-read creation per GitHub docs | Gate B confirms |
| 12 | PR comment | `Publisher.pr_comment` (`publish_pr`) | `test_publication_reconcile.py`; B-7 | one comment, edited in place | Offline verified | Gate B |
| 13 | Partial publication | per-surface tokens, `unpublished_permission` | per-surface 403 and declined-mint tests; C-3 | the other surfaces publish; the Check Run names the gap | Offline verified | Gate C (records GitHub's actual refusal) |
| 14 | Publication recovery | `_resume_publication` (identity: tenant, repo, run, attempt, SHA, PR target) | `test_publication_recovery.py` (8 + 1 tests) | resumed without re-investigation; never to a changed target | Offline verified | Gate C (C-5) |
| 15 | Worker recovery and operator requeue | reaper, takeover, `tracewise_requeue` (0013) | `test_requeue.py`, `test_recovery_semantics.py`; C-5, C-6 | takeover safe; requeue authenticated, atomic, audited | Offline verified | Gate C; requeue limit **Requires owner decision** |
| 16 | Usage persistence | 0014, 0016; `ops report` | `test_usage_persistence.py` | NULL = unknown; partial flagged; no double count | Offline verified | gate D (real usage) |
| 17 | Tenant security | RLS (0005), least privilege (0015), definers | `test_rls.py`, `test_privilege_matrix.py`, `test_migrations_0012_0017.py`; A-7 | catalogue equals the documented matrix | Offline verified | Gate A |
| 18 | Retention | purge (0008, 0017), dry run, audit | `test_retention.py`; C-7 | exact dry run; live runs untouched | Offline verified | Gate C; schedule and host logs **Requires owner decision** |
| 19 | Operational reporting | `ops report`, events | `test_observability.py` | stuck or incomplete work visible | Offline verified | alert routing **Requires owner decision** |
| 20 | Deployment, backup and recovery | compose, preflight, `require_schema_at`, OPERATIONS §8/§8b | `test_backup_restore.py`, migration tests; A-1 to A-8 | upgrade with a verified backup; refusal on a wrong schema | Offline verified | Gate A; restore drill (Gate E) |
