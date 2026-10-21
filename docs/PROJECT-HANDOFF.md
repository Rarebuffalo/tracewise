# Project handoff (canonical; read this first)

**As of 2026-10-21T21:10Z (2026-10-22 local).** Facts here were checked against the working tree at that time.
Re-verify the repository state before relying on anything below (§H).

## A. Project identity

**Tracewise** is a GitHub App that diagnoses failed GitHub Actions workflows. When a run fails it gathers the failed
jobs' logs, the relevant code at the failing commit and the push's diff, runs a deterministic pre-pass, then a
bounded, read-only AI investigation, validates every claim against that evidence, and publishes one deterministic,
evidence-backed report through GitHub (commit comment or PR comment, plus a neutral Check Run). When it cannot
support a conclusion it says so instead of guessing.

- **Target user:** developers and maintainers of repositories that use GitHub Actions; MVP languages Python and
  TypeScript (D-2), generic extraction for everything else.
- **MVP:** [SPEC.md](SPEC.md) (requirements FS-*), [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md) (AT-*),
  [TASKS.md](TASKS.md) (T-*), decisions in [DECISIONS.md](DECISIONS.md) and [ARCHITECTURE.md](ARCHITECTURE.md) (ADR-*).
- **Comparator: "The Plumber"**, the GitHub Marketplace app `the-plumber-app` (app id 3376027; vendor site
  `theplumber.dev`; demo repository `theplumber-dev/coffee_shop`), Free plan, 10 analyses per month
  (research/final-evidence-review/EVIDENCE-LEDGER.md, REPRODUCIBILITY-AND-PROVENANCE.md). Only its declared
  integration and **one** real report (a commit comment, April 2026) are observed; everything else about its runtime
  behaviour is a vendor claim or unknown (research/final-evidence-review/COMPETITOR-BEHAVIOR-VERIFICATION.md).
- **Strategy:** essential parity with that workflow first; evidence-backed differentiation second (attribution from
  the push's diff ships in the MVP; lane history, flaky and dependency drift are P2 behind ADR-13). No comparative
  claim without AT-CMP-01 (a head-to-head in an approved test organisation).

### Parity matrix (essential workflow)

Comparator classes are the research's own labels. "Live" = needs the real GitHub test organisation.

| Capability | Comparator evidence | Tracewise implementation | Tests | Status |
|---|---|---|---|---|
| Install without repository config | Documented | `web/lifecycle.py`, `github/auth.py` | `tests/db/test_lifecycle.py` | Parity offline; live install is S0 |
| Trigger on a failed `workflow_run` | Observed for `failure` (n=1) | `web/webhooks.py`, `web/ingest.py` (`failure`, `timed_out`) | `tests/db/test_webhook.py` | Parity; `startup_failure` awaits G-PLAT-1 (live) |
| Asynchronous processing | Inferred | `jobs/queue.py`, `jobs/worker.py`, `worker.py` | `tests/db/test_queue.py`, `test_worker.py` | Parity |
| Failed job, step, first error, sibling grouping | Observed (n=1) | `prepass/`, `analysis/collect.py` | `tests/unit/test_primary.py`, `test_extractors.py` | Parity |
| Code at the failing commit | Observed / Documented | `context/gitfetch.py`, `context/contents_api.py`, `context/tools.py` | `tests/context/test_gitfetch.py`, `test_contents_api.py`, `test_tools.py` | Parity |
| Root cause, why, location, fix text, confidence | Observed (n=1) | `investigate/`, `analysis/diagnose.py` | `tests/investigate/`, `tests/context/test_diagnose_e2e.py` | Implemented; **real-model quality unmeasured** (T-605) |
| Report in GitHub (commit comment, PR comment) | Commit comment observed; PR comment documented only | `github/publish.py`, `github/pulls.py`, `report/render.py` | `tests/db/test_analyze_worker.py`, `test_github_worker.py`, `test_full_chain.py` | Parity offline; live in S0–S2 |
| Check Run | Comparator cannot create one | `github/publish.py` (neutral, upserted) | as above | Tracewise addition |
| Re-runs, duplicates, incomplete analyses | Unknown | dedupe in `web/ingest.py`; markers; `render_could_not_complete`; `recovery.py` | `tests/db/test_phase51_final_publication.py`, `test_recovery*.py` | Implemented; D-14 open |
| Attribution from the push's diff | Absent in its report | `context/trigger.py` | `tests/context/test_trigger.py` | Differentiator (MVP) |
| Lane history, dependency drift, flaky | Unknown | `analysis/lane.py`, `analysis/drift.py`; flaky not built | `tests/unit/test_lane.py`, `test_drift.py` | P2, **not surfaced** (ADR-13); T-902 blocked (B-04) |
| Quota | 10/month documented | migration 0011, `jobs/handlers/analyze.py` | `tests/db/test_quota.py` | Implemented; value is your decision |

**Comparator unknowns** (never claim parity or superiority on these): handling of `timed_out`/`cancelled`/
`startup_failure`, PR runs, re-runs; flaky, dependency, infrastructure and multi-error cases; quota exhaustion,
uninstall, missing permissions; PR comment format; clone versus API; model vendor; actual retention; latency
beyond n=1; any change since April 2026.

## B. Architecture

```
workflow_run webhook → HMAC check, 25 MB cap, dedupe (web/) → durable Postgres queue (jobs/queue.py)
→ worker (worker.py, jobs/handlers/analyze.py) → jobs, logs, code, diff (analysis/collect.py, context/)
→ deterministic pre-pass (prepass/) → bounded investigation (investigate/loop.py; tools read_file, grep,
  list_dir, get_diff only) → validation and confidence (investigate/validate.py, confidence.py)
→ deterministic report (report/render.py) → idempotent publication (github/publish.py)
```

- **Database:** PostgreSQL 16, migrations 0001–**0011** (head) in `src/tracewise/db/migrations/versions/`. Roles from
  `scripts/db/provision_roles.sql`: `tracewise_owner` (non-superuser; owns the schema; migrations only),
  `tracewise_app` (tenant plane, row-level security always applies), `tracewise_system` (system plane, the only
  `BYPASSRLS` role). Processes refuse the wrong role at startup; the migration CLI refuses runtime roles, superusers
  and non-owners. Details: [OPERATIONS.md](OPERATIONS.md) §1–§2, [DEPLOYMENT-BLUEPRINT.md](DEPLOYMENT-BLUEPRINT.md) §6.
- **Providers:** `investigate/providers.py`. `fake` (scripted) is accepted **only** with `TW_ENV=test` and produces
  "could not complete" reports. `openai` (codec `investigate/openai_responses.py`, adapter `investigate/http_adapter.py`)
  is written and tested offline but **refuses to start** until the approvals in [SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md) §1.
- **GitHub App permissions (exact):** Actions read, Contents read, Metadata read, Pull requests write, Checks write;
  event `workflow_run`. Publication: one write-once commit comment for push runs, one upserted PR comment for PR runs,
  one neutral Check Run "Tracewise" (`external_id` = run id), all reconciled before creating, so retries never
  duplicate. Missing permissions are recorded as `unpublished_permission`, never escalated.
- **Operations CLIs:** `python -m tracewise.{preflight,db.migrate,worker,recovery,retention,ops}`; web:
  `uvicorn --factory tracewise.web.asgi:create_runtime_app`. Staging bundle: [deploy/staging/](../deploy/staging/README.md).

## C. Repository state at handoff

- **Branch** `fix/preview-fetch-credentials`, **HEAD** `2da0e27`, remote `origin` (not pushed since). **The working tree
  has extensive uncommitted work** (tracked modifications plus new files across `src/`, `tests/`, `docs/`, `deploy/`,
  `scripts/`, `Dockerfile`, `.dockerignore`), none committed. Untracked user assets `.claude/` and `tracewise-brand/`
  must be preserved.
- **Migration head:** `0011` (analysis quota).
- **Verification run 2026-10-21T21:10Z on this tree:**
  - `make lint type docs`: exit 0 (ruff clean, 252 files formatted, mypy strict clean, docs check PASS);
  - `make image-check`: exit 0, all 8 steps passed (built `tracewise:local`);
  - `make ci`: exit 0, **1385 passed, 0 failed, 0 skipped, 0 network attempts**, truth lock matches;
  - `python -m tracewise.bench signals`: exit 0 (dependency drift, unseen split: 0 FP, 2 FN, 28 TN; no accuracy claim);
  - `python -m tracewise.bench verify`: 26 cases, truth lock matches; `git diff --check`: clean.
- **Local resources:** Docker image `tracewise:local`; cached `postgres:16` and `caddy:2`. Unrelated containers (for
  example `aeo-audit-db`) are not part of this project and must be left alone.

## D. Completed work (evidence in the linked docs and tests)

- The whole webhook-to-report pipeline offline, with scripted providers: [CHANGELOG.md](CHANGELOG.md), TASKS T-101…T-503.
- Synthetic benchmark (26 cases, truth lock) and META cases P-01…P-03 from recorded public metadata:
  [BENCHMARK.md](BENCHMARK.md), [benchmark-runs/](benchmark-runs/).
- Tenancy and least privilege: RLS, role contracts, privilege matrix and catalogue guards
  (`tests/db/test_rls.py`, `test_privilege_matrix.py`, `test_least_privilege.py`).
- Reliability: queue leases and retries, redelivery and sweep with overlap locks, idempotent publication, D-10
  re-checks, retention, quota, final-attempt notices.
- Security: signature check, input bounds, redaction, prompt-injection containment, read-only tools, no secrets in logs.
- Operations: preflight, migration CLI, health/readiness, troubleshooting runbook (OPERATIONS §8a), runtime image,
  staging Compose bundle rehearsed locally (deploy/staging/README.md "Readiness status").
- Latest fix this sprint: AT-EVT-03 (a job GitHub ended `timed_out` is now named in every report).

## E. Remaining work

| ID | Impact | Evidence now | Status | Blocker / action | Acceptance | Next step |
|---|---|---|---|---|---|---|
| T-801 / T-802 (S0–S3) | First real diagnosis path | Plan, gates, preflight, rehearsal | BLOCKED_EXTERNAL | VM, DNS, test org, dev App, secrets | LIVE-VALIDATION-PLAN stage gates; S0 contract below | Operator steps 1–11 in deploy/staging/README.md |
| T-803 (live Track F) | Live publishing/context tests | Offline equivalents | BLOCKED_EXTERNAL | Test org | AT-PUB-01…03, AT-CTX-01 live | After S0 |
| T-605 (+ T-401/T-402 remainder) | Real diagnosis quality | Adapter, codec, smoke harness offline | BLOCKED_APPROVAL | A-1…A-7 (SMOKE-RUNBOOK §1) | Smoke outcome classes §6, then the real-model benchmark (AT-DX-*, AT-DX-15) | Your written approvals |
| T-1002 | Staging deployment | Image, Compose bundle, rehearsal | BLOCKED_EXTERNAL | Host choice and provisioning (D-11) | Readiness gate on the host | Provision the VM |
| T-1003 | Soak and restore drill | Runbooks, local restore | BLOCKED_EXTERNAL | Staging host | Soak with p50/p95; restore rehearsed on the host | After S3 |
| T-706 | Cost figure, alert routing | Report and alert rule | BLOCKED_APPROVAL | Prices (T-605); routing; threshold 0.2 provisional | Priced cost; routed alert | Decide routing |
| T-1001 | Pilot terms, privacy | Notice draft | BLOCKED_APPROVAL | Counsel; model family (AT-SEC-13) | Reviewed notice and terms | Counsel review |
| T-901 surfacing | "Already failing" signal | Computed, not shown | BLOCKED_APPROVAL | Held-out evaluation + your decision (ADR-13) | docs/benchmark-runs/2026-10-22-signals-dependency-drift.md procedure | Approve the evaluation fetch |
| T-903 surfacing | Dependency-drift note | Computed, not shown | BLOCKED_APPROVAL | Same as T-901; recall limit (B-17) | Same | Same |
| T-902 | Flaky suspicion | — | BLOCKED_APPROVAL | B-04; ingest lacks a passed-attempt signal | AT-ATR-07 | Decide B-04 |
| T-904 | Outcome tracking | — | DEFERRED | P2, changes published reports | AT-PUB-07 | After pilot |
| AT-CMP-01, AT-RPT-10 | Any comparative or usefulness claim | — | BLOCKED_APPROVAL | Install the comparator in a test org; user study | As defined | Only if you want claims |
| Owner decisions | Policy | OWNER-DECISION-PACKET | BLOCKED_APPROVAL | D-11, D-12, D-14, B-04, A-05, A-04, B-12, D-5, E-01, validator rule 3, quota value, alert threshold, deleted-run notice, G-PLAT-11 (after S2), D-10 follow-up (after S3), worker-crash step in S0–S3 | [OWNER-DECISION-PACKET.md](OWNER-DECISION-PACKET.md) | Decide in order of the pilot path |

No local implementation gap remains that can be closed without one of the above.

## F. Exact next actions

1. **Staging host readiness** (your actions): provision a VM, DNS name and firewall; create the test organisation,
   repositories and the dev App (not installed); write the secret files; then follow deploy/staging/README.md steps
   6–11 until preflight exits 0 and `/readyz` is 200 over HTTPS. *(Requires your authorisation: provisioning,
   the App.)*
2. **First S0** *(authorisation required)*: install the App on `tw-push` only; push one failing commit. Passes when:
   one delivery ingested, exactly one commit comment with `<!-- tracewise:cc:wfN -->`, one neutral Check Run
   "Tracewise" with the could-not-complete notice, re-runs update in place without new comments, no abort condition.
3. **S1–S3** *(authorisation per stage)*: in order, per LIVE-VALIDATION-PLAN "Stage gates"; record G-PLAT findings;
   then decide G-PLAT-11 and D-10. Enable cron schedules only after S1, with your approval.
4. **Real-model smoke and evaluation** *(approvals A-1…A-7, then separate approvals for wiring and evaluation)*:
   SMOKE-RUNBOOK §1–§6 on your machine; then the real-model benchmark (AT-DX-15, E-01).
5. **Private-pilot decision:** after S0–S3 pass, the T-605 evaluation is reported, D-12 and alert routing are
   decided, the privacy notice and terms are reviewed, a staging soak and restore drill are done (OPERATIONS §10).

**Definition of done, first live milestone:** step 2's S0 contract plus S1–S3 gates, with the fake provider; it
proves the GitHub pipeline, **not** diagnosis quality. **Private pilot:** OPERATIONS §10 release checklist, every
item true.

## G. Operating rules

- No commit, push, deploy, publish, branch switch, provisioning or App installation without explicit authorisation.
- Never open, print, copy or modify `research/final-audit-public/evidence/marketplace.html`; do not touch
  `research/final-audit/evidence/` or `research/final-audit-public/evidence/`. Never edit `TRUTH.lock` or benchmark truth.
- Provider gate: `LLM_PROVIDER=openai` stays refused; no real model call without SMOKE-RUNBOOK §1 approvals.
- Never print or store secrets; never weaken a test or present a simulated result as live evidence.
- **Commands that can reach external services:** `scripts/openai_smoke.py --live` (model provider);
  `python -m tracewise.recovery` and a running worker or web process with real credentials (GitHub);
  `make image` / `docker compose up` / `uv sync` (registries, PyPI); the website's waitlist email sender
  (`waitlist/outbound.py`). Offline and safe: `make ci` (network guard, `-m "not live"`), `make image-check`
  (containers without network), `python -m tracewise.bench verify|signals|meta --recorded`.
- Leave unrelated containers and volumes alone.

## H. Resuming in a new account

Paste this:

> You are continuing the Tracewise project. First read `docs/PROJECT-HANDOFF.md`. Then verify the live repository
> state (branch, HEAD, `git status`, migration head) before relying on it. Read only the source files the next task
> needs. Preserve all uncommitted changes, `.claude/`, `tracewise-brand/` and every protected path listed in §G; do
> not commit, push, deploy or contact external services unless I authorise it. Continue from the next unresolved
> acceptance criterion in §E/§F rather than repeating completed audits.
