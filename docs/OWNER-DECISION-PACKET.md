# Owner decision packet (Phase 52)

One page of what is still waiting on you, rechecked against the repository at the end of Phase 52. Every item
lists what is decided in code today, the question, the choices and their consequences. Nothing here is decided by
the implementation. Detail lives in [DECISIONS.md](DECISIONS.md), [OWNER-DECISION-SHEET.md](OWNER-DECISION-SHEET.md),
[SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md), [GITHUB-CONTRACT-AUDIT.md](GITHUB-CONTRACT-AUDIT.md) and
[DEPLOYMENT-BLUEPRINT.md](DEPLOYMENT-BLUEPRINT.md).

**Independent of every item below:** the offline implementation is complete for everything specified. Each item
blocks only the work named in its last line.

## 1. D-12 retention: accept or change four implemented interpretations

The purge mechanics are implemented and tested: `tracewise_purge()` (migrations 0008/0009) and `python -m
tracewise.retention`, which is unscheduled. Four interpretations are built in:

| | Interpretation as implemented | If you change it |
|---|---|---|
| (a) | The whole diagnosis document counts as an "excerpt" and is cleared at 90 days | Narrower: keep the non-text fields longer; wider: clear sooner |
| (b) | 365 days for jobs, runs, usage and redelivery bookkeeping, where the spec states no period | Any other period needs a new migration that replaces the purge function |
| (c) | Audit rows are kept after a tenant purge, until their own 365 days | Deleting them at purge time removes the evidence of the purge itself |
| (d) | A minimal installation tombstone with no expiry, so a deleted installation cannot be re-activated | Expiring it allows reuse after the period; GitHub never reuses ids |

**Approval needed:** "accept (a)–(d)", or name the change. **Blocks:** PRIVACY-NOTICE-DRAFT §5, and scheduling retention.

## 2. D-14: report surfaces that may or may not have been published on the final attempt

**Implemented (decided by FS-ERR-1):** if nothing could have reached GitHub (no analysis row for the run attempt),
the final attempt publishes the "could not complete" notice. **Open:** a surface was attempted and GitHub answered
5xx or timed out. A publication row records `pending`/`failed`, which cannot prove absence. Today there is no
notice, the job ends `dead`, and the rows show each surface's state.

| Option | Correctness | Duplicate risk | Latency | Recovery |
|---|---|---|---|---|
| (a) keep | Never contradicts a visible report; a surface may stay silently missing | None | None | Operator sees `dead` plus the rows; a GitHub re-run fixes it |
| (b) reconcile first: list the PR/commit comments and check runs (the code already does this on retries), then notify only surfaces proven absent, worded "report partly published" | Correct whenever the listing succeeds; if the listing also fails, falls back to (a) | Low (adopts what it finds) | 1–3 extra GET calls on the final attempt only | Same as (a) when GitHub is down |
| (c) one deferred publication-only retry after the deadline | Most complete; re-uses the existing idempotent publisher | Low | Minutes | Needs a new job kind or claim rule; the most code |

**Recommendation:** (b). The publisher's reconciliation (`_find_comment`, `_find_check_run`) already proves
presence by app identity and first-line marker, so it adds no new state. Not implemented until you approve.
**Blocks:** nothing else.

## 3. D-11: database roles and credentials

The current grants are in the privilege matrix (DEPLOYMENT-BLUEPRINT §6, checked against the live catalogue by
`tests/db/test_privilege_matrix.py`).

- **Excess found:** the tenant role (`tracewise_app`) still holds the 0001 grants on system-plane tables: S/I/U/D on
  `job`, `webhook_delivery`, `usage_event` and `failure_signature`. RLS confines those rows to the current tenant,
  and its code paths do not use them.
- **Proposed least privilege:** a migration that revokes `job`, `webhook_delivery` and DELETE on `usage_event` and
  `failure_signature` from `tracewise_app`. It affects no tenant-plane operation (the analyze handler and publisher
  do not touch them). The migration would be reversible.
- **Also needed:** separate credentials per role from your secret store; the PUBLIC revoke template
  (`scripts/db/provision_roles.sql`) applied to the real database.

**Approval needed:** the revoke migration (yes/no), and who provisions the credentials. **Blocks:** any real
deployment.

## 4. Benchmark items (never changed to make scores pass)

| Item | Evidence | Question | Supported choices and consequences |
|---|---|---|---|
| B-04 | C1 rated `high_confidence_wrong`: `flaky_suspect` at high confidence without attempt metadata | BENCHMARK §2 says "≤ medium"; AT-DX-11 says `flaky_suspect` "only with attempt metadata; otherwise inconclusive is accepted" | **Cap at medium:** keeps the label and meets §2, but not the strict AT-DX-11 reading. **Inconclusive:** meets both, but loses the hint |
| A-05 | AT-LOG-04 is met (error kept, truncation flagged); the truth also expects `first_error` | Correct the truth (a new lock), or keep it | Correcting changes the frozen truth (needs your sign-off); keeping leaves a known failure |
| B-12 | Citing a file deleted by the push is "invalid evidence" (validator rule 4) | Allow evidence paths deleted in the trigger diff? | Allow: more complete explanations; Keep: stricter, safer. Decide with D-5 |
| D-5 | Compiler points at a different file → the correct answer is rated low | Relax the conflict rule? | Keep strict until real-model data exists (recommended) |
| E-01 | Prompt-injection resistance cannot be shown with fake providers | — | Measured in T-605 only |

## 4a. Open questions from the Phase 57 audit and later work (nothing decided)

| Item | Question | Choices and consequences |
|---|---|---|
| **Validator rule 3 (fix replacement range)** | A suggested replacement may target lines the model never read (e.g. lines 1–5 while only 40–41 were read). Should rule 3, like rule 2 for the location, require the replacement to lie inside an examined range? | **Require it:** fewer unsupported fixes; some fixes are dropped and only the location remains. **Keep:** today's behaviour, which the written rule allows. |
| **Monthly analysis quota value (T-703)** | The quota mechanics are implemented (`ANALYSIS_QUOTA_MONTHLY`), but FS-QTA-1 gives no number. Which value per installation per month, and should a value be required in production? | **Unset (today's default):** no limit. **A number:** cost is capped; over-quota runs get one notice per repository per day and no analysis. |
| **S0 with the fake provider** — **decided 2026-10-22: option (a)**; commit-comment validation deferred, publication policy unchanged | *Correction 2026-10-23: the premise below was inaccurate. The fake provider is only invoked when the failed job's log has a recognised error line; then the run ends `could_not_complete` (Check Run only, D-8). A log without one ends `inconclusive` (`no_error_line`) without a provider call, which is a completed analysis and gets the commit comment under the existing policy (observed on run 40008159332). The decision (a) and the G-PLAT-5 deferral are unchanged.* Original question: the fake provider ends every analysis `could_not_complete`, which D-8 publishes on the Check Run only. S0's commit-comment expectations (and G-PLAT-5, a commit comment accepted with Contents read) therefore cannot be observed in the fake-provider milestone. How should they be covered? | **(a) Accept S0-fake as Check-Run-only** and check the commit comment once a real model produces completed analyses (no change; G-PLAT-5 stays open longer). **(b) Approve a deterministic staging-only fake answer** (TW_ENV=test only) that returns an honest "inconclusive" result, which is a completed analysis and so exercises the write-once commit comment without claiming a diagnosis (a small code change; needs your approval). **(c) Run S0 only after the real model** (delays the first live milestone). |
| **Installation-token 401 treated as an uninstall** (observed 2026-10-22 during S0 setup, open finding) | `GitHubHTTP.app_call` maps a 401 on the token mint, like a 403 or 404 on the installation, to `InstallationUnavailable`, and the analyze job ends `cancelled_uninstalled` with no notice and no retry (FS-INS-3). A 401 there means GitHub rejected the App JWT (deleted or wrong private key, wrong App ID, clock skew), not that the installation is gone. Observed live on 2026-10-22: two S0 jobs were cancelled this way. The likely cause is a local private key whose key pair had been deleted in the App settings: a replacement key resolved it (`GET /app` 200 on 2026-10-23); the worker logs of 2026-10-22 were not retained, so this is inferred; the job rows carry only `cancelled_uninstalled`, indistinguishable from a real uninstall. Should a mint 401 be distinguished? | **Keep (today):** a misconfigured App looks like an uninstalled one; runs during the fault are silently skipped. **Distinguish 401:** fail loudly (job `dead` or retried with an error event and alert) so the operator fixes the key; uninstall and suspension handling unchanged; a small code change, needs your approval. |
| **Run deleted while being analysed** | A 404 from the jobs API (run deleted mid-processing) ends the job `dead` with no notice, whereas missing logs give a `logs_unavailable` report. Should a deleted run get a notice? | **Notice:** the user sees something, but on a run that no longer exists. **Silent (today):** nothing to show on a deleted run. |
| **Lane history: surfacing (T-901, T-903, T-604)** | The lane foundation and dependency drift are computed offline and published nowhere (ADR-13). META P-01–P-03 now pass from the recorded anonymous metadata of 2026-10-17 (docs/benchmark-runs/2026-10-22-meta-recorded.md), with no new fetch, but the case logic was written knowing the labels, so this is not held-out evidence. May "already failing before this push" or a dependency-drift note appear in reports, and what evidence is required first? | **Require held-out META cases first (fresh anonymous fetch, approved separately):** slower, independent evidence. **Surface now as a labelled signal:** earlier user value on 3 consistency-checked cases. **Keep unsurfaced (today).** |

## 5. Alert threshold

The rule fires at (dead + could-not-complete) ÷ finished ≥ **0.2** over 1 h, with at least 10 jobs. It is pinned by
`tests/db/test_alert_boundaries.py` and the main alert test (exactly 0.2 fires, 0.1 is ok, 9 jobs is
insufficient). **Evidence needed:** the baseline failure rate from staging traffic. **Choice:** confirm 0.2, or set
the observed baseline plus a margin. Unchanged until you decide.

## 6. G-PLAT-11 / F-1: one refused publish token blocks every surface

One bundled `publish` token (Contents read, Pull requests write, Checks write) is used for all surfaces. Under a
simulated refusal of that token, nothing is published, which is contrary to AT-REL-05.

| Option | Effect |
|---|---|
| (a) per-surface tokens | Narrowest privileges; three token mints per job; changes ADR-16 |
| (b) on refusal, re-mint without `pull_requests` | Smaller change; Check Run and commit comment still publish |
| (c) keep | Only safe if GitHub never refuses the bundled mint |

**Recommendation in the audit:** (a), but only if live stage S2 shows GitHub really refuses. **Blocks:** nothing
offline; decide after S2.

## 7. OpenAI: three separate authorisations

1. **Smoke call** (SMOKE-RUNBOOK §1):
   - A-1: written authorisation for one run of at most 3 requests;
   - A-2: the model id and its source;
   - A-3: a project-scoped key in a `chmod 600` file outside the repository;
   - A-4: the account's data-retention and training settings;
   - A-5: approval of the synthetic content;
   - A-6: approval of the command;
   - A-7: prices for the cost bound (under 4,500 input and 6,144 output tokens).
2. **Provider activation** (`LLM_PROVIDER=openai` in `providers.py`): only after a passing smoke run.
3. **T-605 evaluation** (benchmark with the real model, E-01, cost and latency): separately.

Approving 1 does not approve 2 or 3.

## 8. Signed URLs in `marketplace.html`

The file holds AWS signed-URL query strings (expired 2026-10-17). It was not opened. **Choice:** redact the query
strings (recommended before any push) or leave as is. It is an evidence file, so editing it needs your approval.

## 9. Hosting, live GitHub validation and legal review (external)

- **T-1002 hosting** (DEPLOYMENT-BLUEPRINT): the platform; TLS and a public webhook URL; the secret store; process
  supervision; schedules for recovery, retention and alerts; alert routing; a staging soak (T-1003).
- **Live GitHub:** a test organisation and a development App to run LIVE-VALIDATION-PLAN S0–S5. Offline coverage
  per stage is listed there.
- **Supply chain:** CI references `actions/checkout@v4` and `astral-sh/setup-uv@v6` by tag. Pinning them to commit
  SHAs needs the exact upstream revisions, which cannot be verified offline. Do it when a remote exists.
- **Legal:** PRIVACY-NOTICE-DRAFT (owner, contact, legal basis, provider terms) and the pilot terms need counsel's
  review. Nothing in the repository is legal approval.
