# Verified Feature Spec: Core Parity with The Plumber, plus Tracewise Attribution

Date: 2026-10-17. Evidence IDs (F1–F22) refer to [FINAL-REVERSE-ENGINEERING-AUDIT.md](FINAL-REVERSE-ENGINEERING-AUDIT.md) §4. Test IDs (AT-…) refer to [TRACEWISE-PARITY-ACCEPTANCE-TESTS.md](TRACEWISE-PARITY-ACCEPTANCE-TESTS.md).

**Goal.** Reproduce The Plumber's observable value and user journey:

1. a failed GitHub Actions run;
2. an automatic structured diagnosis with root cause, file and line, a fix, and the files examined;
3. the report posted on the commit or PR.

Add the evidenced gap, attribution, as the differentiator. This document specifies **what** must be true. How to build it is constrained only where reliability or security requires it.

**Priority key**

| Priority | Meaning |
|---|---|
| **P0** | Required for core parity |
| **P1** | Important, deferrable past the first internal build |
| **P2** | Differentiation |
| **—** | Out of MVP |

---

## 1. Parity table

| ID | Feature | Competitor evidence | Confidence | Tracewise implementation requirement | Acceptance test | Priority |
|---|---|---|---|---|---|---|
| FS-INS-1 | Install as a GitHub App from a public install page; no repo configuration file | F4, F5 (VERIFIED, DOCUMENTED "No config changes") | High | Public GitHub App. Works with zero files added to the repo. Analysis starts on the next failed run after install. | AT-INS-01 | P0 |
| FS-INS-2 | Permission set | F1 (VERIFIED) | High | `actions:read`, `contents:read`, `metadata:read`, `pull_requests:write`, plus **`checks:write`** (our addition, FS-PUB-3). No other write scopes. Rejects work if an installation lacks a required permission (FS-ERR-3). | AT-INS-02, AT-SEC-01 | P0 |
| FS-INS-3 | Uninstall and suspend handling | Not observable (UNKNOWN) | — | On `installation.deleted` or `suspend`, stop new jobs. In-flight jobs end as `cancelled_uninstalled` with no publish. Purge tenant data within 7 days. | AT-INS-03 | P1 |
| FS-INS-4 | Repository selection (all or selected repos) | GitHub-native | High | Honour `installation_repositories` added/removed. Ignore events for repos no longer in scope. | AT-INS-04 | P1 |
| FS-EVT-1 | Trigger on `workflow_run.completed` with a failure conclusion | F2, F9 (VERIFIED for `failure`/`push`) | High | Analyse when `action=completed` and `conclusion ∈ {failure, timed_out, startup_failure}`. Ignore `success`, `cancelled`, `skipped`, `neutral` and `action_required`. `startup_failure` gets the "workflow could not start" path (FS-DX-6). | AT-EVT-01..04 | P0 |
| FS-EVT-2 | Asynchronous processing | F10, F16 (INFERRED, strong) | High | Respond 2xx within 10 s of a verified delivery. Do all work in a background worker. | AT-EVT-05 | P0 |
| FS-EVT-3 | Webhook authenticity | UNKNOWN for competitor | — | Verify `X-Hub-Signature-256` with a constant-time comparison **before** parsing. Reject on mismatch (401). Body size cap of 25 MB (GitHub's maximum payload). | AT-SEC-02 | P0 |
| FS-EVT-4 | Deduplication | UNKNOWN for competitor; F3 implies re-runs would duplicate its comments | — | Idempotency on `X-GitHub-Delivery` **and** on `(repo_id, run_id, run_attempt)`. A re-run attempt updates the same report (FS-PUB-4). | AT-EVT-06, AT-PUB-05 | P0 |
| FS-EVT-5 | Missed-delivery recovery | — | — | A periodic reconciliation lists recent App deliveries and failed runs, and enqueues missing analyses (GitHub does not auto-redeliver: DOCUMENTED, GitHub). | AT-REL-03 | P1 |
| FS-EVT-6 | Concurrency control | UNKNOWN | — | Global worker concurrency cap; per-installation cap of 2; one analysis per `(repo, run_id)` at a time. | AT-REL-04 | P1 |
| FS-LOG-1 | Retrieve logs of failed jobs | F6 (DOCUMENTED), consistent with F9 | Medium-high | Fetch jobs for the run attempt, then each failed job's log via `GET /actions/jobs/{id}/logs` with an installation token. | AT-LOG-01 | P0 |
| FS-LOG-2 | Identify the failed step and job | F9: the report names the failed step (as a command) | High (n=1) | Report the **job name and step name**, and the step's command where derivable. Parse `##[group]` and `##[error]` markers and the jobs API `steps[]`. | AT-LOG-02 | P0 |
| FS-LOG-3 | Expired or missing logs | F19: the 410 is VERIFIED platform behaviour | High | 410/404 on logs → publish an "inconclusive: logs unavailable" report with run metadata only. Never a guessed cause. | AT-LOG-03 | P0 |
| FS-LOG-4 | Large logs | UNKNOWN for competitor | — | Stream. Keep the failed-step sections, plus ±200 lines around each `##[error]` and the first error-like line, up to 2 MB per job. If anything was dropped, set `log_truncated=true` and say so in the report. | AT-LOG-04 | P0 |
| FS-LOG-5 | Secret redaction before any storage or LLM call | UNKNOWN for competitor | — | Respect GitHub's `***` masking. Add a regex and entropy pass (tokens, keys, JWTs, connection strings). | AT-SEC-04 | P0 |
| FS-CTX-1 | Read repository code at the failing commit | F6 (DOCUMENTED clone), F9/F11 (VERIFIED: quotes non-log code) | High that code is read; mechanism UNKNOWN | Read-only access to the tree at `head_sha`. Either a **partial clone in an ephemeral directory** (`--filter=blob:none --no-checkout`, then `checkout` of `head_sha`; hooks disabled; LFS skipped; no build or test execution), or contents-API range fetches. Repo size cap 1 GB; files over 1 MB not read. | AT-CTX-01..03 | P0 |
| FS-CTX-2 | Record which files and ranges were examined | F14 (VERIFIED text, n=1) | High | Every file read is logged as `{path, start_line, end_line}` from the **actual** read, not from model text. Paths are repo-root-relative (fixes the competitor's `coffee_shop/coffee_shop/` artefact, F14). | AT-CTX-04, AT-RPT-06 | P0 |
| FS-CTX-3 | Commit and diff context | No evidence the competitor uses it (F13) | — | Fetch the trigger commit's diff (vs its parent for push; vs merge base for PR) and its changed-file list. | AT-ATR-01 | P0 (needed by FS-ATR-1) |
| FS-CTX-4 | Workspace cleanup | F7 (DOCUMENTED claim) | Low as fact | Delete the workspace in a `finally` block on every exit path, including timeouts and crashes (startup sweep of stale dirs). Never persist source files. | AT-SEC-06 | P0 |
| FS-DX-1 | Identify the first causal error, not the last line | F9 (VERIFIED n=1: chose the first failing assertion and grouped siblings) | High (n=1) | Deterministic extractor ranks candidate errors by step order and timestamp. Downstream cascades (same ImportError ×N, "N failed" summaries, steps after a failed build) are marked secondary. | AT-DX-02, AT-DX-07 | P0 |
| FS-DX-2 | Group sibling failures with the same cause | F9 ("…and 3 other test failures") | High (n=1) | Group failures by normalised fingerprint and shared implicated location. Report the count and names. | AT-DX-03 | P0 |
| FS-DX-3 | Explain *why* it failed (mechanism) | F9, F11 (VERIFIED) | High | LLM investigation with read-only tools (`read_file(path, start, end)`, `grep(pattern, path_glob)`, `list_dir`, `get_commit_diff`). ≤12 tool calls, ≤120 s, token budget enforced. Structured output (§3). | AT-DX-01, AT-DX-04 | P0 |
| FS-DX-4 | Locate the problematic code (file + line + snippet) | F9, F11 (VERIFIED) | High | `problem_location` must point inside a range in `files_examined`. The snippet is copied by the system from the file, **not** taken from model text. | AT-DX-05, AT-VAL-02 | P0 |
| FS-DX-5 | Recommended fix (text + replacement snippet) | F9, F11 (VERIFIED; correct on n=1) | High | `fix.description` ≤600 chars, plus an optional `fix.replacement` for one location (≤20 lines). Text only: no commits, branches or PRs. Omitted when the category is not code (FS-DX-6) or confidence is low. | AT-DX-06 | P0 |
| FS-DX-6 | Non-code categories get a non-code remedy | Competitor: UNKNOWN (no category field) | — | Category ∈ `code_regression`, `test_defect`, `dependency`, `config_secret`, `infra_runner`, `flaky_suspect`, `workflow_invalid`, `unknown`. Non-code categories produce `next_steps` (re-run, pin, configure secret) instead of a code fix. | AT-DX-08..11 | P1 |
| FS-DX-7 | Confidence | F21: the "High" label has no basis | High | Bands `high`, `medium`, `low`, plus `basis[]` (e.g. "error line quotes the changed line", "validator 3/3"). No numeric probability until calibrated. | AT-DX-12 | P0 |
| FS-DX-8 | Abstain when evidence is insufficient | UNKNOWN for competitor | — | `status=inconclusive` when: the validator rejects the root-cause claim; no error line is found; logs are unavailable or truncated past the error; the budget is exhausted. The report then gives 1–3 diagnostic next steps and **no fix**. | AT-DX-13, AT-DX-14 | P0 |
| FS-ATR-1 | Trigger-commit relevance | **Gap evidenced** (F13) | High | Compute whether the trigger commit's changed files intersect the implicated files (log paths, problem location, examined files). Report one of: "this commit changed X, which is implicated" / "this commit changed only Y, none implicated: the failure likely pre-dates it" / "unknown". Intersection is **evidence, not a verdict**: when lane history (FS-ATR-2) or a dependency or runner signal (FS-ATR-4) contradicts it, those win. Real trap: R-03, where the trigger edits a docstring in the traceback file but the cause is an upstream Werkzeug change. | AT-ATR-01..03, AT-ATR-09 | **P2 (but cheap, ship in MVP)** |
| FS-ATR-2 | Last green / first bad in lane | Gap (F13) | — | Lane = `(repo_id, workflow_id, event_class, branch, head_repo_id)`. Find the last successful run and the first failing run. Name the commit range and, where one commit in it touches the problem location, name it. | AT-ATR-04..06 | P2 |
| FS-ATR-3 | Flaky suspicion | — | — | The same fingerprint passed on the same `head_sha` (another attempt), or alternated in the lane → `flaky_suspect`, with "re-run" as the first next step | AT-ATR-07 | P2 |
| FS-ATR-4 | Dependency drift | — | — | Resolved package versions in the install step differ from the last green run's, with no lockfile change → `dependency` category, naming the package and versions | AT-ATR-08 | P2 |
| FS-RPT-1 | Report header + summary | F9 (VERIFIED) | High | Title; failed job and step; one-sentence root cause; confidence band; fix size (`trivial`, `small`, `larger`, `n/a`) | AT-RPT-01 | P0 |
| FS-RPT-2 | What Failed | F9 | High | ≤15 redacted log lines verbatim, plus sibling-failure count | AT-RPT-02 | P0 |
| FS-RPT-3 | Why It Failed | F9 | High | ≤800 chars | AT-RPT-03 | P0 |
| FS-RPT-4 | Problematic Code | F9 | High | `path:line` (repo-relative, linked to the blob at `head_sha`) and a ≤15-line snippet | AT-RPT-04 | P0 |
| FS-RPT-5 | Recommended Fix | F9 | High | Per FS-DX-5 | AT-RPT-05 | P0 |
| FS-RPT-6 | Files Examined | F9, F14 | High | Every examined file with its true range and a one-line verdict | AT-RPT-06 | P0 |
| FS-RPT-7 | Attribution section | Absent in competitor (F13) | — | FS-ATR-1 always; FS-ATR-2 when available | AT-RPT-07 | P2 (MVP) |
| FS-RPT-8 | For AI Agents block | F9 (VERIFIED) | High | A fenced block containing: repo, `head_sha`, failing job and step, the reproduce command (the step's `run:` line, when it is a single command), problem location, fix instructions, and a verify command. **Plain text, no links.** Present only when `status=diagnosed` and the category is code or test. | AT-RPT-08 | P0 |
| FS-RPT-9 | Links back to the run, job and commit | Absent in competitor (F14) | — | Footer links to the run, job and commit | AT-RPT-09 | P1 |
| FS-RPT-10 | Size and safety | — | — | ≤60,000 chars (GitHub limit 65,536). Escape `@` mentions and HTML. No model-generated links. | AT-SEC-07 | P0 |
| FS-PUB-1 | Post on push failures (no PR) | F9: commit comment (VERIFIED) | High | **Commit comment** on `head_sha` (needs only `contents:read`). It cannot be edited, so post exactly once per `(repo, head_sha, workflow_id)`, after the final attempt's analysis or the first analysis. Later attempts update only the Check Run. | AT-PUB-01, AT-PUB-05 | P0 |
| FS-PUB-2 | Post on PR failures | F5 (DOCUMENTED; never observed, F12) | Medium | One **PR comment** per `(PR, workflow_id)`, **upserted** (edited) on later runs and attempts. Uses `pull_requests:write`. | AT-PUB-02, AT-PUB-05 | P0 |
| FS-PUB-3 | Check Run | Competitor cannot (F3) | — | One `Tracewise` Check Run per `(head_sha, workflow run)`, conclusion `neutral`, with the full report in `output.text` and ≤10 annotations at the problem location. Updated in place. | AT-PUB-03 | P1 (deliberate improvement) |
| FS-PUB-4 | Re-run behaviour | Competitor can't edit commit comments (F3) | — | A new attempt re-analyses: it updates the Check Run and the PR comment, and adds no new commit comment | AT-PUB-05 | P0 |
| FS-PUB-5 | Fork PRs | UNKNOWN | — | Try a PR comment and a Check Run. On 403, record `unpublished_permission` and log it; never fail silently in the metrics. | AT-PUB-06 | P1 |
| FS-PUB-6 | Outcome on the next run | Competitor: none observed | — | The next completed run in the same lane marks the analysis `resolved`, `still_failing_same`, or `different_failure`. Shown on the Check Run (and PR comment), not as a new comment. | AT-PUB-07 | P2 |
| FS-ERR-1 | Analysis failure | UNKNOWN | — | Any internal error after logs are fetched → "Tracewise could not complete the analysis" Check Run (neutral) + a short PR comment. **No commit comment** on push, to avoid noise. Retry ≤2 with backoff. | AT-REL-01 | P0 |
| FS-ERR-2 | GitHub rate limit or 5xx | — | — | Honour `Retry-After` and `x-ratelimit-reset`; exponential backoff; job deadline 10 min | AT-REL-02 | P0 |
| FS-ERR-3 | Missing permission | — | — | A 403 on a needed call → the report states which permission is missing (if it can still publish), plus an internal metric | AT-REL-05 | P1 |
| FS-QTA-1 | Quota | F5: 10/month free (DOCUMENTED) | Medium | A configurable monthly analysis quota per installation. On exceed: no analysis; one "quota reached" Check Run per day per repo; no comments. | AT-QTA-01 | P1 |
| FS-SEC-1 | Prompt-injection resistance | UNKNOWN for competitor | — | Logs, code, commit messages and PR text are untrusted data inside delimiters. Tools are read-only and path-confined to the workspace (no `..`, no symlinks out). No network tool. Output is schema-validated. The renderer ignores model-supplied URLs and mentions. | AT-SEC-08..10 | P0 |
| FS-SEC-2 | Log spoofing of deterministic parsers | — | — | Attribution never relies solely on log text printed by repo code. Version-drift and runner-change rules require a matching signal from structured sources (job metadata, lockfile diff) or are capped at `low` confidence. | AT-SEC-11 | P1 |
| FS-SEC-3 | Data retention | F7 (DOCUMENTED claim) | — | Persist: run metadata, report text, redacted excerpts (≤2 KB) for 90 days, fingerprints for 365 days. Never persist raw logs or source. A tenant purge path exists. | AT-SEC-06, AT-SEC-12 | P0 |
| FS-SEC-4 | LLM provider data use | UNKNOWN for competitor | — | A zero-retention / no-training API configuration; the provider is listed as a sub-processor in the privacy notice | AT-SEC-13 (doc check) | P0 |
| FS-OPS-1 | Observability | UNKNOWN | — | Per-analysis record: stage timings, token usage, cost, outcome status, publish result. Error tracking; alert on a failure rate above 10% per hour. | AT-OPS-01 | P1 |
| FS-OPS-2 | Latency | F10: competitor 6m14s observed vs "<2 min" claimed | n=1 | **Target** (unmeasured): p50 ≤ 2 min, p95 ≤ 5 min from `workflow_run.completed` to publish. Hard job deadline 10 min. | AT-OPS-02 | P1 |

---

## 2. Feature classification

### 2.1 Required for core parity (P0)

FS-INS-1, FS-INS-2, FS-EVT-1–4, FS-LOG-1–5, FS-CTX-1–4, FS-DX-1–5, FS-DX-7, FS-DX-8, FS-RPT-1–6, FS-RPT-8, FS-RPT-10, FS-PUB-1, FS-PUB-2, FS-PUB-4, FS-ERR-1, FS-ERR-2, FS-SEC-1, FS-SEC-3, FS-SEC-4.

### 2.2 Important but deferrable (P1)

FS-INS-3, FS-INS-4, FS-EVT-5, FS-EVT-6, FS-DX-6, FS-PUB-3, FS-PUB-5, FS-RPT-9, FS-ERR-3, FS-QTA-1, FS-SEC-2, FS-OPS-1, FS-OPS-2.

### 2.3 Unverified competitor behaviour (do not design around it as fact)

- PR-comment format and whether it edits PR comments.
- Behaviour on non-unit-test failures, multiple errors, flaky tests, infra failures and large logs.
- An agentic tool loop; a fixed read window; clone vs API.
- Workspace deletion; actual retention; LLM provider.
- Dedupe and retry; which conclusions trigger analysis besides `failure`.
- Latency beyond n=1.

### 2.4 Differentiation supported by evidence

| Feature | Evidence for the gap |
|---|---|
| **FS-ATR-1 trigger-commit relevance** | F13. The competitor's only report missed that the trigger commit was README-only. Cheapest and highest-signal; include in the MVP. |
| FS-ATR-2 lane attribution | F13 plus the market evidence in 05. Not demonstrable on the demo case itself (no in-repo history). |
| FS-DX-7 / FS-DX-8 evidence-based confidence and abstention | F21. The competitor's confidence has no basis. |
| FS-PUB-3 / FS-PUB-4 editable surfaces with no re-run duplicates | F3 constraint |
| FS-RPT-9 run, job and commit links | F14 |

**Not evidenced as differentiation:** flaky and dependency detection versus The Plumber specifically (unknown whether it does this). These are differentiated against GitHub-native tools per 03/05, which is out of this audit's scope.

### 2.5 Out of scope for the first MVP

- Automated fix PRs or commits.
- Sandbox test execution or verification.
- Dashboard and billing.
- Slack and other notifications.
- Non-GitHub CI.
- Self-hosting and BYO LLM key.
- Cross-repo or upstream-fork history (state it as a limitation, per audit C-P7).
- Cross-tenant breakage signals.

---

## 3. Data contracts

### 3.1 `Diagnosis` v2 (replaces the plan's attribution-only schema)

```json
{
  "schema_version": "2",
  "run": {"repo_id": 0, "repo": "o/r", "run_id": 0, "attempt": 1, "head_sha": "…", "event": "push|pull_request", "pr_numbers": []},
  "status": "diagnosed | inconclusive | logs_unavailable | workflow_invalid",
  "failed": [{"job_id": 0, "job": "Tests (Python 3.11)", "step": "Run pytest", "command": "pytest --tb=short -v"}],
  "primary_error": {"log_ref": {"job_id": 0, "line_start": 0, "line_end": 0}, "excerpt_redacted": "…", "fingerprint": "sha256:…"},
  "siblings": {"count": 3, "names": ["test_multiple_items_total", "…"]},
  "category": "code_regression | test_defect | dependency | config_secret | infra_runner | flaky_suspect | workflow_invalid | unknown",
  "root_cause": "≤300 chars",
  "why": "≤800 chars",
  "problem_location": {"path": "coffee_shop/pricing.py", "line_start": 41, "line_end": 41},
  "fix": {"description": "≤600 chars", "replacement": {"path": "…", "line_start": 41, "line_end": 41, "new_text": "…"}, "size": "trivial|small|larger|n/a"},
  "next_steps": ["≤3 items, ≤160 chars each"],
  "files_examined": [{"path": "coffee_shop/pricing.py", "start": 1, "end": 43, "verdict": "≤140 chars"}],
  "attribution": {
    "trigger_commit": "sha", "trigger_changed_files": ["README.md"],
    "trigger_touches_implicated": false,
    "statement": "This push changed only README.md; the failure likely pre-dates it.",
    "last_green_sha": null, "first_bad_sha": null, "introducing_sha": null, "basis": ["no_lane_history"]
  },
  "confidence": {"band": "high|medium|low", "basis": ["…"]},
  "limits": {"log_truncated": false, "files_skipped": [], "budget_exhausted": false},
  "usage": {"model": "…", "input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "latency_ms": 0}
}
```

### 3.2 Validator rules (an analysis fails closed to `inconclusive`)

1. `primary_error.log_ref` lines exist in the retained log, and `excerpt_redacted` is a substring of them (after redaction).
2. `problem_location` lies within some `files_examined` range. `files_examined` comes from the tool log, not the model.
3. `fix.replacement.path` equals `problem_location.path`. The replaced lines exist.
4. Every path mentioned in `why` or `root_cause` either exists at `head_sha` or is flagged and stripped.
5. `attribution.trigger_touches_implicated` is computed by code, never by the model.
6. If rule 1 or 2 fails: `status=inconclusive`, the fix is omitted, and `next_steps` is kept.

---

## 4. Tracewise reference architecture (implementation choices)

| Component | Choice | Type | Why |
|---|---|---|---|
| Runtime | One Python 3.12 service with `web` and `worker` processes (as in the existing plan, ADR-01) | Choice | Small surface; existing plan |
| Queue | Postgres job table with `SKIP LOCKED` (existing ADR-03) | Choice | One datastore |
| Code context | Partial clone to an ephemeral, size-capped tmpfs or disk dir per job, deleted in `finally` | Choice (see FS-CTX-1) | Supports grep and listing for the investigator. Contents-API fallback for repos over the size cap. |
| Investigator | A single model with a bounded tool loop (≤12 calls), read-only tools, structured output. Model chosen by eval on the acceptance set (Haiku 5.5 vs Sonnet 5.5). | Required capability; model is a choice | Parity on novel failures (FS-DX-3) |
| Deterministic pre-pass | Log splitter, first-error ranker, fingerprint, sibling grouping, trigger-diff intersection | Choice (reliability) | Testable without an LLM; reduces tokens |
| Publisher | Check Run (always) + PR comment upsert, or a single commit comment | Parity + improvement | FS-PUB-1..4 |
| Storage | Postgres: installations, repos, runs, analyses (Diagnosis JSON), fingerprints, deliveries, usage | Choice | FS-SEC-3 |

Changes from the existing IMPLEMENTATION-PLAN:

- LLM default **on**;
- code-context component added;
- `pull_requests:write` restored;
- commit-comment publisher added;
- `Diagnosis` v2;
- the trigger-commit relevance check added.

Everything else (attribution engine, RLS, reconciliation, retention) carries over.
