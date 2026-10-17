# GitHub Platform Verification (implementation-critical)

Date: 2026-10-17. Official docs were fetched as raw markdown into `evidence/docs/` (FETCH-LOG has the URLs). EV-IDs are from [EVIDENCE-LEDGER.md](EVIDENCE-LEDGER.md).

**Grades**

| Grade | Meaning |
|---|---|
| **DOC** | Official documentation states it |
| **OBS** | Observed in public, unauthenticated data |
| **GATE** | Requires a live test in an authorized environment we did not create. These are listed in §8 as implementation gates. |

## 1. `workflow_run`

| # | Claim | Grade | Evidence | Design consequence |
|---|---|---|---|---|
| 1.1 | Actions are `requested`, `in_progress` and `completed`. `completed` fires "regardless of whether the workflow was successful or unsuccessful". The App needs Actions **read**. | DOC | EV-P01 | Filter on `action=completed`, then on `conclusion` |
| 1.2 | The docs give **no conclusion enum** for the webhook. The REST runs `status` filter lists `failure`, `timed_out`, `cancelled`, `action_required`, `neutral`, `skipped`, `stale`, `success` (no `startup_failure`). `startup_failure` appears only in the Check Suites conclusion enum. | DOC (by absence) | EV-P03 | **GATE G-PLAT-1:** does an App receive `completed` with `startup_failure`? Until then, analyse only `failure` and `timed_out`. |
| 1.3 | `requested` does not occur on re-runs. Re-runs reuse `GITHUB_SHA` and `GITHUB_REF`. ≤50 re-runs. | DOC | EV-P02 | Dedupe on `(repo, run_id, run_attempt)`. **GATE G-PLAT-2:** confirm `completed` is delivered per attempt with an incremented `run_attempt`. |
| 1.4 | `head_sha` meaning for PR runs is undocumented on the webhook page. For workflows triggered by `pull_request`, `GITHUB_SHA` is the merge commit. | DOC | EV-P20 | Do not assume `head_sha` is the merge commit |
| 1.5 | In one same-repo PR, run `head_sha` = PR head SHA | OBS (n=1) | EV-P22 | Treat `head_sha` as the PR head. Read code at `head_sha`. Note in reports that CI tested the merge with the base, so base changes can matter. |
| 1.6 | The run object's `pull_requests` was empty in 20/20 sampled PR runs. It is documented as empty for forks. | OBS + DOC | EV-P23, EV-P10 | **Never rely on `pull_requests`.** Resolve PRs via `GET /commits/{sha}/pulls` (same-repo) or `GET /pulls?head=<owner>:<branch>` (forks). GATE G-PLAT-4. |

## 2. Webhook delivery

| # | Claim | Grade | Evidence | Consequence |
|---|---|---|---|---|
| 2.1 | Respond 2XX within 10 s, otherwise the delivery has failed | DOC | EV-P05 | Enqueue-only handler |
| 2.2 | No automatic redelivery. Redelivery keeps the same `X-GitHub-Delivery`. Deliveries can be listed and redelivered via `/app/hook/deliveries…`. | DOC | EV-P06 | Delivery-ID dedupe plus a reconciliation job |
| 2.3 | HMAC-SHA256 in `X-Hub-Signature-256` (absent without a secret); constant-time compare; never `==` | DOC | EV-P07 | Reject a missing header; `hmac.compare_digest` over the raw body |
| 2.4 | Payloads over 25 MB are **not delivered** | DOC | EV-P04 | A 413 path is defensive only. Oversized events are silently missing, so reconciliation by listing failed runs is the backstop. |
| 2.5 | No ordering guarantee is stated | DOC (absence) | EV-P08 | Idempotent upserts keyed by `(run, attempt)`; tolerate `completed` arriving before `in_progress` |

## 3. Permissions per Tracewise operation

All from the official permissions table, EV-P09 (rows with line numbers in `evidence/permission-rows.txt`).

| Operation | Endpoint | Permission | Grade |
|---|---|---|---|
| List jobs for an attempt | `GET /actions/runs/{id}/attempts/{n}/jobs` | Actions read | DOC |
| Download job log | `GET /actions/jobs/{id}/logs` (302, URL valid 1 min) | Actions read | DOC (EV-P12) |
| Lane history | `GET /actions/workflows/{id}/runs` | Actions read | DOC |
| Trigger diff | `GET /compare/{basehead}` | Contents read | DOC |
| Read files | `GET /contents/{path}`; `GET /git/trees/{sha}`; `GET /tarball/{ref}`; HTTP git with `x-access-token` | Contents read | DOC (EV-P17) |
| Create commit comment | `POST /commits/{sha}/comments` | **Contents read** | DOC (GATE G-PLAT-5: confirm live) |
| Edit commit comment | `PATCH /comments/{id}` | **Contents write** (we do not request it, so commit comments are write-once) | DOC |
| Create or edit PR comment | `POST /issues/{n}/comments`, `PATCH /issues/comments/{id}` | Pull requests write **or** Issues write | DOC |
| Find PR for a commit | `GET /commits/{sha}/pulls` | Pull requests read (granted by write) | DOC |
| Create or update Check Run | `POST`/`PATCH /check-runs` | Checks write (Apps only) | DOC (EV-P10) |
| Find our Check Run | `GET /commits/{ref}/check-runs?check_name=` | Checks read | DOC |

**Minimum MVP permission set** (parity, plus a Check Run):

| Permission | Level |
|---|---|
| Actions | read |
| Contents | read |
| Metadata | read |
| Pull requests | write |
| Checks | write |

**Permission removal or upgrade:** new permissions require approval by each installation (EV-P21). Design: on a 403, record `permission_denied` naming the missing permission. Never retry-loop.

## 4. Data access limits

| # | Claim | Grade | Evidence | Consequence |
|---|---|---|---|---|
| 4.1 | Logs are retained 90 days by default (1–90 days public, 1–400 private) | DOC | EV-P14 | `logs_unavailable` path. Lane baselines older than retention cannot be log-compared. |
| 4.2 | Anonymous job-log download on public repos returns 403 | OBS (n=2) | EV-P13 | Benchmarks cannot use public logs without a credential |
| 4.3 | Compare returns ≤250 commits; file list ≤300 | DOC | EV-P15 | Truncation flag; no file-intersection claims beyond the limits |
| 4.4 | Contents API: ≤1 MB full; 1–100 MB raw only; >100 MB unsupported. Symlink and submodule types exist. | DOC | EV-P16 | Skip files >1 MB in MVP. Do not follow symlinks. Do not recurse into submodules. |
| 4.5 | Installation token lasts 1 h and is scopable; HTTP git needs Contents | DOC | EV-P17 | Scope tokens to repo plus permissions. Mint per job. |

## 5. Output limits

| # | Claim | Grade | Consequence |
|---|---|---|---|
| 5.1 | ≤50 annotations per Check Run request | DOC (EV-P10) | Cap at 10 |
| 5.2 | Comment-body and Check Run output length limits | **Not documented** (EV-P11). Community reports of about 65,536 are *not authoritative*. | **GATE G-PLAT-3:** measure live. Until then, cap rendered output at 60,000 characters and treat the cap as provisional. |

## 6. Forks and merge commits

| # | Claim | Grade | Consequence |
|---|---|---|---|
| 6.1 | The Checks API does not detect pushes to fork branches (empty `pull_requests`) | DOC (EV-P10) | **GATE G-PLAT-4:** can our App create a Check Run on a fork PR head SHA in the base repo? Can it comment on the PR (the PR lives in the base repo)? |
| 6.2 | `GET /commits/{sha}/pulls` returned `[]` for a fork PR head SHA | OBS (n=1, EV-P24) | Use `GET /pulls?head=` with the run's `head_repository.owner.login` and `head_branch` |
| 6.3 | Secrets are not passed to fork-triggered workflows | DOC (EV-P19) | Customer failures on fork PRs are often `config_secret`. The diagnosis rules need this context. |
| 6.4 | For `pull_request` workflows the tested code is the merge commit | DOC (EV-P20) | Reading `head_sha` code can miss base-branch changes. State this as a limitation in reports. |

## 7. Rate limits

DOC (EV-P18): ≥5,000/h per installation (up to 12,500; 15,000 on GHEC); 100 concurrent requests; 900 points/min; 80 content-creating requests/min and 500/h.

Consequences:

- per-analysis request budget;
- per-installation concurrency of 2;
- honour `retry-after` and `x-ratelimit-reset`;
- publishing counts as content creation.

## 8. Implementation gates (live tests requiring an authorized environment; not created by us)

| Gate | Test | Blocks |
|---|---|---|
| **G-PLAT-1** | Invalid workflow YAML → is `workflow_run.completed` delivered, and with which conclusion? | `startup_failure` support only |
| **G-PLAT-2** | Re-run failed jobs ×2 → one `completed` per attempt with `run_attempt` 2 and 3? | Re-run dedupe design (FS-EVT-4, FS-PUB-4) |
| **G-PLAT-3** | POST a comment and a Check Run output at 59k, 65k and 70k chars → accepted or rejected? | Renderer cap (FS-RPT-10) |
| **G-PLAT-4** | Fork PR → Check Run creation on the head SHA; PR comment; PR lookup by `head=` | Fork support (FS-PUB-5) |
| **G-PLAT-5** | Commit comment created with an installation token holding **Contents read only** | The push-failure parity surface (FS-PUB-1) |
| **G-PLAT-6** | Uninstall during a job → token mint fails with 401/404; in-flight publish fails cleanly | Uninstall handling (FS-INS-3) |
| **G-PLAT-7** | Remove `pull_requests` from an installation (decline the permission upgrade) → 403 path | FS-ERR-3 |

These need a test GitHub account or org plus a dev App, created and approved by the user. **Not created.**
