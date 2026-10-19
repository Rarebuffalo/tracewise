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

## S0: Install and baseline (G-PLAT-6 partial, FS-INS-2)

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

## S1: Duplicate delivery, redelivery and listing (G-PLAT-12)

1. Redeliver the S0 delivery from GitHub's App settings.
   - **Expect:** same `X-GitHub-Delivery` GUID → `duplicate_delivery`; no new job, no new write.
   - **Capture:** whether the GUID is really unchanged (EV-P06 says it is).
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

1. **Suspend during publication.** Use a slow fake provider, or a CI failure with a large log, so there is time. Suspend the installation in the window between the commit comment and the Check Run.
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
| G-PLAT-3 | Publish at 59k, 65k and 70k characters | Through a test-only renderer cap override in the test deployment: accept or reject per surface. Keep the production cap below the measured limit. |
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
