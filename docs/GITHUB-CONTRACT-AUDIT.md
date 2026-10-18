# GitHub integration contract audit: 2026-10-19 (Phase 8)

Offline. The sources are:
- recorded GitHub documentation in `research/final-evidence-review/evidence/docs/` (fetched 2026-10-17), with ledger ids EV-P…;
- recorded public API responses in `tests/fixtures/github/recorded/`;
- the local fake GitHub API.

No GitHub endpoint was contacted. **A passing offline test shows what our code does; it never shows what GitHub does.**

**Evidence key:**
- **DOC**: a recorded GitHub doc states it.
- **REC**: a recorded real response shows it.
- **TEST**: local tests pin our behaviour, against fakes or a simulation.
- **NONE**: nothing offline covers it.

## Gates

| Gate | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| G-PLAT-1 | Is `workflow_run.completed` delivered for invalid YAML, and with which conclusion? (AT-EVT-04) | `startup_failure` is ignored (FS-EVT-1) | DOC: EV-P03, which lists `startup_failure` only in the Check Suites enum. TEST: `test_webhook.py`, `test_contracts.py` (ignored) | **Live gate.** Policy unchanged. |
| G-PLAT-2 | One `completed` per re-run attempt, with an incremented `run_attempt` | Dedupe on (repo, run, attempt); re-runs update in place | DOC: EV-P02 (re-runs reuse the SHA; `requested` is not re-sent). TEST: `test_analyze_worker.py::test_17`, `test_pub05` | **Live gate** (delivery per attempt) |
| G-PLAT-3 | Comment and Check Run output limits | Renderer cap of 60,000 characters (provisional) | DOC: EV-P11 (no limit documented). TEST: `report/test_render.py` | **Live gate** (measure 59k/65k/70k) |
| G-PLAT-4 | Fork PR: Check Run on the head SHA; PR comment; lookup by `head=` | Association by API only; fork lookup via `pulls?head=` | DOC: EV-P10. REC: EV-P23/EV-P24 (`flask-commit-*-pulls.json`: `[]` for a fork head). TEST: `unit/test_github_pulls.py`, `test_pub06` | **Live gate** (whether writes are permitted on a fork head) |
| G-PLAT-5 | A commit comment created with **Contents read** only | The publish scope includes `contents: read` | DOC: EV-P09 lists `POST /commits/{sha}/comments` as Contents read. TEST: `test_01` | **Live gate** (the doc is unusual: a write under read) |
| G-PLAT-6 | Uninstall or suspend during a job: the mint fails (401/404), and publication fails cleanly | `InstallationUnavailable` → `cancelled_uninstalled`; scope re-checked before persisting | TEST: `test_lifecycle.py::test_ins03_*`, `::test_token_refused_mid_job_*`; new tests `test_github_contracts.py::test_suspend_mid_job_*`, `::test_repository_removed_mid_job_*` | **Live gate.** New finding F-2 below. |
| G-PLAT-7 | Decline the `pull_requests` upgrade → 403 path | A 403 on a write → `unpublished_permission`; the Check Run names the permission (AT-REL-05) | TEST: `test_10b` (403 on the write) | **Live gate.** See G-PLAT-11. |
| G-PLAT-8 | Log-redirect host allowlist; token response echoes `repositories` | Fails closed with `UnsafeRedirect`; `_verify_scope` | DOC: EV-P12 documents the redirect, not the host. TEST: `unit/test_github_client.py` | **Live gate** |
| G-PLAT-9 | `git fetch --depth=1 --filter=blob:limit=1m` with a Basic-auth installation token | ADR-14 | TEST: `context/test_gitfetch.py` against local `git http-backend` only | **Live gate** |
| G-PLAT-10 | Reconciliation fields: `performed_via_github_app.id`, `app.id`, `external_id` | `_ours()`, `_find_*` | TEST: `test_06`, `test_07`, `test_16b` (spoofed marker not adopted) | **Live gate** |
| G-PLAT-11 | Does a missing permission for one surface block the others? | One bundled `publish` token: contents read, metadata read, pull_requests write, checks write | DOC: "The installation access token cannot be granted permissions that the app was not granted." The response for a *declined* installation permission is **not documented**. TEST (simulated 422): `test_github_contracts.py::test_g_plat_11_*` | **Defect in our design under the simulation (F-1). Fix needs your approval.** |
| G-PLAT-12 | The delivery list honours `status=failure` and cursors; redelivery keeps the GUID; the runs list honours `status` and `created` | `recovery.py` | DOC: EV-P06 (same `X-GitHub-Delivery` on redelivery; endpoints listed). TEST: `test_recovery.py` (14), `test_cross_phase.py` | **Live gate** (filter and cursor semantics are fake-only) |

## Findings

### F-1 (high, conditional on live behaviour): one refused publish mint blocks every surface

Under a simulated `422` for a token request that includes `pull_requests: write`:
- the PR association call fails;
- D-4 falls back to the commit comment;
- the commit comment, the PR comment and the Check Run all end `unpublished_permission`;
- **no surface is published.**

All three use the same bundled publish token, even though the commit comment needs only Contents read and the Check Run only Checks write. The job ends `succeeded` after one attempt, with no retry loop. AT-REL-05 intends the Check Run to be published, naming the missing permission.

- **Not changed.** Splitting tokens per surface (`checks: write`, `pull_requests: write`, `contents: read`) narrows privileges and keeps policy, but it changes the token design (ADR-16) and triples mints per job. It also only matters if GitHub really refuses the bundled mint.
- **Options:**
  - (a) per-surface tokens: recommended if G-PLAT-7 confirms the refusal;
  - (b) retry the mint without `pull_requests` after a refusal;
  - (c) keep as is.
- **Live check:** decline the `pull_requests` upgrade on the test installation, then mint the publish scope.

### F-2 (medium): no scope re-check between publication surfaces (D-10 as implemented)

Scope is re-checked after diagnosis and before persisting. It is not re-checked between the commit comment or PR comment and the Check Run.

`test_suspend_between_surfaces_*` pins the current behaviour: a suspension that lands after the first write still lets the Check Run publish, using the cached token (valid up to 1 h, EV-P17). Whether GitHub refuses writes from a suspended installation's existing token is not documented in the recorded pages (G-PLAT-6).

Not changed, because it is a D-10 semantics decision. Adding `_recheck` before each surface would cost one extra query per surface.

### F-3 (observation, D-9/D-10): runs cancelled while suspended are never re-analysed

`test_run_cancelled_by_suspension_is_not_reanalysed_after_unsuspend`: run deduplication (repo, run, attempt) turns a later delivery of the same run into `duplicate_run`. After `unsuspend`, failures that happened during the suspension stay unanalysed unless they are re-run on GitHub (new attempt). This is consistent with "controlled no-op" (D-9), but not stated anywhere. It is a product decision.

## Still requiring an approved live environment

G-PLAT-1 to G-PLAT-12, all of them. None was exercised against GitHub.
