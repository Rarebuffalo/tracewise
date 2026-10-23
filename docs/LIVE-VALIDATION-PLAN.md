# Live GitHub validation plan (NOT executed; requires your approval)

**Purpose:** confirm, in a dedicated test organisation, the platform behaviours that offline tests only simulate. These are G-PLAT-1 to G-PLAT-12, plus findings F-1 to F-3 in [GITHUB-CONTRACT-AUDIT.md](GITHUB-CONTRACT-AUDIT.md).

**Nothing here has been run.** Each step lists its expected observation and the evidence to capture. Where GitHub's behaviour is unknown, the plan says so instead of predicting.

## Offline coverage per stage (Phase 51; mocks and local fixtures only, never live verification)

| Stage | Implemented and tested offline | Main tests | GitHub permissions involved | Still needs the live run |
|---|---|---|---|---|
| S0 install, baseline | Signature check, ingest, push publication (commit comment and Check Run), re-run update in place | `test_webhook.py`, `test_analyze_worker.py::test_01`, `test_pub05` | Actions read, Contents read, Checks write, Metadata read | G-PLAT-5 (commit comment with Contents read), G-PLAT-2 (one delivery per attempt), G-PLAT-10 (app ids on objects) |
| S1 duplicates, redelivery, sweep | Dedupe on delivery and on run attempt; redelivery pass with cooldown, attempt cap and held high-water mark; failed-run sweep | `test_recovery.py`, `test_recovery_faults.py`, `test_phase50_reliability.py` (A2) | App JWT: hook deliveries; Actions read | G-PLAT-12: real filter, cursor and GUID semantics |
| S2 declined permission | 403 on a write recorded as `unpublished_permission`; bundled-token refusal **simulated** | `test_10b`, `test_github_contracts.py::test_g_plat_11_*` | Pull requests write (declined) | G-PLAT-7 and G-PLAT-11; the fix for F-1 needs the owner |
| S3 suspension, removal, transfer, uninstall | Re-check before every surface (D-10), explicit-retry rule, repository transfer (0010), deletion tombstone | `test_d10.py`, `test_lifecycle.py`, `test_phase50_transfer.py` | Installation lifecycle events | G-PLAT-6: GitHub's refusal of writes from a suspended installation's token |
| S4 forks, limits, startup failure | Fork PR lookup by `head=`, renderer cap, redirect host allowlist, `git fetch` against a local `http-backend` | `test_pub06`, `report/test_render.py`, `unit/test_github_client.py`, `context/test_gitfetch.py` | Pull requests read/write, Contents read | G-PLAT-1, -3, -4, -8, -9 |
| S5 closing checks | `ops report`/`alerts` (role-checked), retention purge, token and URL scrubbing, network guard | `test_observability.py`, `test_phase50_roles.py`, `test_retention.py`, `unit/test_logging.py` | none | Test-org traffic and the measured p50/p95 |
| Final-attempt notice (FS-ERR-1) | Notice when nothing can be visible; the partial case is D-14 | `test_phase51_final_publication.py` | Checks write, Pull requests write | Whether GitHub applies 5xx-answered writes (it shapes D-14) |

## Preconditions (all needed; any missing = do not start)

- [ ] You approve a dedicated **test organisation** and a **dev GitHub App** (T-801):
  - permissions exactly as FS-INS-2;
  - webhook URL pointing to an approved test deployment.
- [ ] Credentials are **project-scoped only**: the App private key and the webhook secret. No personal tokens, no `gh auth`, nothing global.
- [ ] A test deployment exists, with three separate database credentials (D-11) on a **non-production** database.
- [ ] The model choice is made. If T-605 is not done, stages S1–S5 can run with the `fake` provider; record that the diagnosis quality is not under test.
- [ ] Test repositories:
  - `tw-push` (push failures);
  - `tw-pr` (same-repo PRs);
  - `tw-fork` and a fork of it (fork PRs).

  Each contains only synthetic code; reuse the B-02 fixture.
- [ ] Log capture is on for the test deployment, as JSON event lines. Evidence goes to an approved, non-public location; never commit it.

**Evidence for every step:**
- delivery GUIDs;
- `ops report` JSON;
- the relevant `event` lines;
- screenshots or API JSON of the GitHub surfaces;
- DB row counts (`job`, `publication`, `analysis`).

**Never capture:** tokens, signed URLs or log blobs.

## Operator checklist for S0–S3 (prepared offline; nothing below has been run)

**Owner-provided inputs** (none exist in this repository; none may be committed):

| Input | Where it goes | Who provides it |
|---|---|---|
| Test organisation and the three test repositories | GitHub | Owner (T-801 approval) |
| Dev GitHub App: id, private key (`.pem`), webhook secret (≥16 random characters) | `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` (file mode 0600, **outside** any git working tree), `GITHUB_WEBHOOK_SECRET` | Owner creates the App |
| HTTPS URL of the test deployment (`/webhooks/github`) | App settings | Owner (no hosting exists yet) |
| Three database credentials on a non-production database (D-11) | `DATABASE_URL` (tracewise_app), `DATABASE_URL_SYSTEM` (tracewise_system), `DATABASE_URL_MIGRATIONS` (owner) | Owner / DBA |
| Model choice; without it the run uses `TW_ENV=test LLM_PROVIDER=fake` and diagnosis quality is not under test | `LLM_PROVIDER`, `TW_ENV` | Owner |
| Monthly analysis quota (optional) | `ANALYSIS_QUOTA_MONTHLY` | Owner decision |

**Commands, in order** (run in the test deployment's environment; each must succeed before the next):
On the recommended single-VM staging, the same commands run through Compose: `deploy/staging/README.md` steps 7–11 (for example `docker compose --profile jobs run --rm preflight`).

1. Migrate as the owner (only `DATABASE_URL_MIGRATIONS` set in this shell): `uv run python -m tracewise.db.migrate upgrade`, then `uv run python -m tracewise.db.migrate status` (exit 0 = at head).
2. Preflight, configuration only (no network): `uv run python -m tracewise.preflight --process all` (`all` also covers `python -m tracewise.recovery`, used in S1, which needs the system URL and the App credentials). Exit 0 is required; exit 2 lists the failed checks by name; exit 3 means a setting is invalid. Output never contains a value.
3. Preflight with the database (read-only: roles and schema head): `uv run python -m tracewise.preflight --process all --database`.
4. Confirm by hand each `manual` line the preflight prints (App permissions exactly as FS-INS-2, the `workflow_run` subscription, the webhook URL and secret, installation scope). The preflight cannot see GitHub and does not try.
5. Start the web process and check `/readyz` returns 200; start one worker (§1a of OPERATIONS.md).
6. Only then install the App on `tw-push` and begin S0. Run S1–S3 in order; stop at any abort condition below.

A failed preflight starts nothing: the module has no GitHub or model client (tested in `tests/unit/test_preflight.py`), and the web and worker processes repeat their own startup refusals independently.

## Stage gates (prepared offline; checked against the CLIs in this build)

S0 in this plan is the install baseline; environment readiness is the gate **before** it. Each row: do the action,
check the expectation, and continue only when "Proceed when" holds. On failure, apply the cleanup and the rollback
conditions below.

| Stage | Prerequisites | Action / command | Expected (observable) | On failure | Proceed when |
|---|---|---|---|---|---|
| Readiness | Owner inputs in the checklist above | `python -m tracewise.db.migrate upgrade`; `python -m tracewise.db.migrate status`; `python -m tracewise.preflight --process all --database`; start web and one worker | migrate status exit 0; preflight exit 0 (warnings allowed: fake provider, quota); `/readyz` 200; `worker.started` event | Fix the named check; nothing has reached GitHub | All four hold and every `manual` preflight line is confirmed by hand |
| S0 | Readiness | Install the App on `tw-push`; push a failing commit; re-run twice | §S0 below: one comment, one Check Run updated in place, one `completed` per attempt. **Fake provider:** surfaces depend on the log (see the note under §S0) | Uninstall the App | No abort condition; ids captured |
| S1 | S0 | Redeliver; stop web during a failure, then `python -m tracewise.recovery deliveries`; then `python -m tracewise.recovery runs` | §S1: `duplicate_delivery`; `"redelivered": 1`; second pass `already_received`; sweep `"enqueued": 1`, then `"duplicates": 1` | Stop recovery; no cleanup needed (dedupe) | No second job for any run attempt |
| S2 | S1 | Decline a permission; failing PR on `tw-pr` | §S2: `publication.state = unpublished_permission` with `missing_permission`; record the mint result | Restore and re-approve permissions | Mint behaviour recorded; never more than requested |
| S3 | S2 | Suspend, remove the repository, uninstall (see §S3 step 1 limits) | Jobs `cancelled` with `installation_suspended`, `repo_not_in_scope` or `cancelled_uninstalled`; installation `deleted` with `purge_after` | Reinstall; delete test PRs and branches | No write after `deleted`; old id stays a tombstone |
| S4 | S3 (G-PLAT-3 also needs T-605) | §S4 table rows | Recorded per gate | Revert `REPORT_MAX_CHARS` | Each gate recorded (accept, reject or not run, with the reason) |
| S5 | S4 | `python -m tracewise.ops report`; `python -m tracewise.ops alerts`; grep captured logs; uninstall; `python -m tracewise.retention` | report and p50/p95 labelled test-org traffic; zero token shapes; tenant purged, tombstone kept (retention exit 0, or 3 = run again) | Rotate any leaked secret (rollback section) | Findings recorded in GITHUB-CONTRACT-AUDIT.md |

**The App is created before the readiness gate, installed only at S0.** Creating the dev App (step 3 of
`deploy/staging/README.md`) gives the id, key and webhook secret the preflight needs; it reaches no repository. Its
**installation** on `tw-push` starts S0 and is a deliberate, separately authorised action, as is every later live
event. Offline tests (the first table) cover our side of each stage with fake GitHub; none of them is live evidence.

**How to inspect each result on the staging host** (`deploy/staging`, with `TW_SECRETS_DIR` and `TW_DOMAIN` set):

| Evidence | Command |
|---|---|
| Event lines (`webhook.ingested`, `publication.result`, `job.*`, `recovery.*`) | `docker compose logs --since 30m web worker \| grep '"event"'` |
| Job, publication and analysis states | `docker compose exec -T db psql -U postgres -d tracewise -c "SELECT status, count(*) FROM job GROUP BY 1"` (likewise `publication` by `surface, state, missing_permission`; `analysis` by `status`) |
| Delivery outcomes and GUIDs | `docker compose exec -T db psql -U postgres -d tracewise -c "SELECT delivery_id, event, outcome FROM webhook_delivery ORDER BY received_at DESC LIMIT 20"` |
| Recovery summary | the JSON printed by `docker compose --profile jobs run --rm recovery deliveries` (fields `redelivered`, `already_received`, `enqueued`, `duplicates`, `stopped`, `completed`) |
| Report and latency | `docker compose --profile jobs run --rm ops report` |
| GitHub surfaces | the commit's comments and Checks tab in the GitHub UI, or the API JSON, captured without tokens |

**Known gaps in S0–S3 (flagged, not redefined):**
- **Worker crash recovery** (a killed worker's lease expiring and another worker publishing exactly once) is not a
  live step; it is covered only offline (`tests/db/test_worker_main.py`). Adding it to a stage is your decision.
- **S2** records GitHub's behaviour under three hypotheses; it has no pass/fail beyond "recorded, and never more than
  requested". The follow-up (G-PLAT-11, F-1) is your decision after S2.
- **S3 step 1** cannot be timed deliberately in this build (see the step); it may end up recorded as step 2.

## S0: Install and baseline (G-PLAT-6 partial, FS-INS-2)

> **With the fake provider (the first live milestone), what step 2 publishes depends on the failed job's log.** No
> root cause is ever named. **No recognised error line** (for example only `Process completed with exit code 1`):
> the deterministic pre-pass ends the analysis `inconclusive` (`no_error_line`) without invoking the provider
> (`investigate/loop.py`, `has_error_line`); that is a completed analysis, so the existing policy publishes the
> write-once commit comment (FS-PUB-1) and the Check Run. **A recognised error line** (for example a Python
> traceback): the investigation runs, the fake provider fails each attempt, and after the retries (about
> 1–3 minutes) the run ends `could_not_complete`, published on the Check Run only (plus the PR comment on PR runs),
> never as a commit comment (FS-ERR-1, D-8; `tests/db/test_analyze_worker.py::test_11_rel01_*`). Check Runs are
> published in both cases. **Owner decision 2026-10-22: option (a)**: S0 runs with the fake provider; commit-comment
> validation and G-PLAT-5 stay **deferred**, not passed (OWNER-DECISION-PACKET §4a). Observed 2026-10-23: run
> 40008159332 (no error line) ended `inconclusive` and published one commit comment and one Check Run, consistent
> with the policy above; this is recorded as an observation, not as a G-PLAT-5 pass. The stage definition below is
> unchanged.

1. Install the App on `tw-push` only.
   - **Expect:** `webhook.lifecycle` `processed`; `installation` active; repository rows for `tw-push`.
   - **Capture:** the installation id, and the granted permissions in GitHub's installation page.
2. Push a commit that fails CI (B-02 defect).
   - **Expect:**
     - one `workflow_run.completed` → `webhook.ingested` `enqueued`;
     - one commit comment on the head SHA, carrying the marker `<!-- tracewise:cc:wfN -->`;
     - one neutral Check Run "Tracewise" with `external_id` set to the run id.
     - **G-PLAT-5:** the commit comment is accepted with Contents read only.
   - **Capture:** the comment and Check Run ids, and their `performed_via_github_app.id` and `app.id` (G-PLAT-10).
3. Re-run the failed jobs twice.
   - **Expect (G-PLAT-2):** one `completed` per attempt, with `run_attempt` 2 and then 3; the commit comment count stays 1; the Check Run is updated in place.
   - **Unknown:** whether GitHub always delivers per attempt.

**Cleanup:** none (S1 continues from here). **Abort if:** any duplicate commit comment, any write to another repository, or any token in the logs.

> **Observed 2026-10-22 to 2026-10-23 (one environment, fake provider; observations, not guarantees).** Local
> trial on a laptop behind an ngrok tunnel, development App on one test repository, not the `tw-push` organisation
> layout above. Timeline (UTC): App installed on 2026-10-22, when the first two failing runs were ingested and
> cancelled by a token-mint 401 (OWNER-DECISION-PACKET §4a); every run below and the redelivery in §S1 date from
> 2026-10-23.
> - Run 40008159332, log without a recognised error line: see the note at the top of this section.
> - Run 40011572580, log with a Python traceback, attempts 1–3 (the first run plus two "Re-run failed jobs"): one
>   `completed` delivery per attempt, each `enqueued` once (dedupe keys `…:40011572580:1`, `:2`, `:3`); every
>   attempt's job hit three fake-provider failures and ended `could_not_complete`. Check Run 120614188181 was
>   created on attempt 1 and updated in place on attempts 2 and 3 (one `update_check_run` 200 each;
>   `source_attempt` 1 → 2 → 3). No commit comment, no second Check Run, no new publication row.
> - **G-PLAT-2:** each re-run delivered `in_progress` and `completed` only (no `requested`, no `check_suite`
>   event), with `run_attempt` incremented. This matches the gate's expectation for two re-runs; whether GitHub
>   always delivers per attempt remains unknown.
> - Final counts: 21 deliveries, 6 jobs, 6 workflow-run rows, 4 analyses, 3 publication rows; no live AI call; no
>   token or secret found in the retained container logs (from 2026-10-23 17:58 UTC, when web and worker were last
>   recreated; earlier logs were not kept); no GitHub write outside the test repository in those logs.
> - G-PLAT-5 stays **deferred**; G-PLAT-10 (`performed_via_github_app.id`, `app.id`) was not captured.

## S1: Duplicate delivery, redelivery and listing (G-PLAT-12)

1. Redeliver the S0 delivery from GitHub's App settings.
   - **Expect:** same `X-GitHub-Delivery` GUID → `duplicate_delivery`; no new job, no new write.
   - **Capture:** whether the GUID is really unchanged (EV-P06 says it is).
   - **Observed 2026-10-23 (S0 environment above):** redelivering the processed attempt-3 `completed` delivery of
     run 40011572580 arrived with the same GUID and was answered `duplicate_delivery`; no job claimed, no GitHub
     call, all counts unchanged. One redelivery only; steps 2–4 not run, so S1 is not passed.
2. Stop the test deployment's web process. Cause one CI failure, then restart.
   - **Expect:** GitHub lists the failed delivery under `GET /app/hook/deliveries?status=failure`.
   - **Run:** `python -m tracewise.recovery deliveries`.
   - **Expect:** `redelivered: 1`; the redelivered webhook is ingested once; a second pass shows `already_received`.
   - **Capture:** the list response's cursor `Link` header shape, and whether `status=failure` filters as assumed.
3. Disable redelivery (keep the web process stopped during a failure, then do not redeliver). **Run:** `python -m tracewise.recovery runs`.
   - **Expect:** the sweep finds the run through `GET /actions/runs?status=failure&created>=…` → one job → published once. A second sweep reports `duplicates: 1`.

**Cleanup:** none. **Abort if:** a second job is created for the same run attempt.

## S2: Declined permission and the bundled token (G-PLAT-7, G-PLAT-11, F-1)

1. Change the dev App to request an extra permission and **decline** it on the test installation. Alternatively, uninstall and reinstall the App with Pull requests access unapproved, if GitHub's UI allows that.
   - **Record exactly** what the installation's granted permissions show.
2. Open a same-repo PR on `tw-pr` whose CI fails.
3. **Observe the token mint** for the `publish` scope (Contents read, Pull requests write, Checks write). This is the unknown at the heart of F-1.

**Expected under each hypothesis:**

| GitHub behaviour | Expected Tracewise result today | Decision it informs |
|---|---|---|
| Mint refused (422 or similar) for the bundled request | `pr_comment`, `commit_comment` (D-4 fallback) and `check_run` all `unpublished_permission`. **No surface published.** That contradicts AT-REL-05. | Approve per-surface tokens (recommended) or a mint retry without `pull_requests` |
| Mint succeeds with reduced permissions | Our `_verify_scope` accepts a subset; the PR comment POST gets 403 → `unpublished_permission`; the Check Run is published and names the missing permission (AT-REL-05 as intended) | Keep the bundled token |
| Mint succeeds, then the PR association call is refused | The association error leads to the D-4 commit-comment fallback; the Check Run is published | Confirms D-4 fallback behaviour |

**Capture:**
- the mint response status and body `message`, with **no token**;
- `publication` rows and their `missing_permission`;
- the Check Run text.

**Cleanup:** restore the App's permissions and re-approve on the installation. **Abort if:** a mint is ever granted **more** than requested (we fail closed, but record it).

## S3: Suspension, deletion, repository removal (G-PLAT-6, D-10, F-2, F-3)

1. **Suspend during publication.** This build has no way to widen the window between the commit comment and the Check Run (there is no slow provider setting, and the provider runs before publication), so this step can only be attempted by timing, with a failure whose analysis takes long enough to suspend during it. If the suspension lands before publication, record it as step 2 instead. The re-check itself is covered offline (`tests/db/test_d10.py`).
   - **Unknown:** whether GitHub refuses the Check Run write from the already-minted token (F-2).
   - **Expect (D-10(a) decided):** Tracewise re-checks before the Check Run, so it does **not** publish. The job ends `cancelled` `installation_suspended`. Separately, record whether GitHub would have refused the write anyway.
2. **Suspend, then cause a failure, then unsuspend.**
   - **Expect:** the job is cancelled `installation_suspended`. After unsuspend, the run stays `duplicate_run` (D-10(b) decided: only an explicit re-run analyses it) unless it is re-run on GitHub (new attempt).
3. **Remove `tw-push` from the installation mid-job.**
   - **Expect:** before publication → `cancelled` `repo_not_in_scope`, zero writes; after the first surface → no further surface (D-10(a)); `cancelled` `repo_not_in_scope`.
4. **Re-add `tw-push`.**
   - **Expect:** `repository_added` (`removed_at` cleared, `enabled` kept); new failures are analysed.
5. **Uninstall during a job.**
   - **Expect (G-PLAT-6):** the token mint fails with 401 or 404 → `cancelled_uninstalled`; no publication. `installation.deleted` → status `deleted`, `purge_after` = +7 days.
   - **Reinstall:** GitHub issues a **new** installation id. The old one stays `deleted` (tombstone) and the new one is active. Capture both ids.

**Cleanup:**
- reinstall the App;
- delete test PRs and branches;
- leave the comments, which are evidence;
- after S5, run `python -m tracewise.retention` on the test database only.

**Abort if:** any write after `deleted`, or any resurrection of the old installation id.

## S4: Forks, limits, startup failure (G-PLAT-1, -3, -4, -8, -9)

| Gate | Step | Expect or record |
|---|---|---|
| G-PLAT-1 | Push invalid workflow YAML | Is `workflow_run.completed` delivered, and with which conclusion? We ignore `startup_failure`. Record what GitHub sends. |
| G-PLAT-3 | Publish at 59k, 65k and 70k characters | Raise `REPORT_MAX_CHARS` (no upper bound; default 60000) in the test deployment only: accept or reject per surface. **Needs a model** (T-605): the fake provider only produces short could-not-complete notices, so this gate cannot run with `fake`. Keep the production cap below the measured limit. |
| G-PLAT-4 | Fork PR on `tw-fork` | `/commits/{sha}/pulls` returns `[]`; `pulls?head=owner:branch` finds the PR. Record whether the Check Run and PR comment writes are permitted. |
| G-PLAT-8 | Log download | Record the redirect host. If it is not in the allowlist, logs fail closed (`UnsafeRedirect`). Never record the signed query string. |
| G-PLAT-9 | Code context | `git fetch --depth=1 --filter=blob:limit=1m` with a Basic-auth installation token succeeds against github.com |

## S5: Closing checks

- Run `python -m tracewise.ops report` and `alerts`. Capture the report and the observed p50/p95. Label these as **test-org traffic**, not production.
- Grep the captured logs for token shapes, `sig=` and `X-Amz-`. Expect zero.
- Uninstall the App and wait for `purge_after`, or set it on the test database only. Run `python -m tracewise.retention`; expect the tenant purged and the tombstone kept.

## Rollback and stop conditions (any stage)

Stop and roll back (uninstall the App; stop the test deployment; rotate the webhook secret and App key if any leak is suspected) if any of these occurs:
- a write outside the three surfaces or to an unapproved repository;
- a duplicate commit comment;
- a token or secret in any log or report;
- a cross-tenant row visible to `tracewise_app`;
- a token granted more than requested;
- any behaviour that would contact a non-test organisation.

Record the findings in GITHUB-CONTRACT-AUDIT.md and the review queue. Decisions (G-PLAT-11, D-10) are made **after** S2 and S3, by you.
