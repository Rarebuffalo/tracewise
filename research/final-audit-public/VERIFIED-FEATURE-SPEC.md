# Verified Feature Spec: Core Parity with The Plumber, plus Tracewise Attribution (public-evidence edition)

Date: 2026-10-17.

- **Evidence IDs (P-…):** [FINAL-REVERSE-ENGINEERING-AUDIT.md](FINAL-REVERSE-ENGINEERING-AUDIT.md) §4. These come from unauthenticated public sources only.
- **Test IDs (AT-…):** [TRACEWISE-PARITY-ACCEPTANCE-TESTS.md](TRACEWISE-PARITY-ACCEPTANCE-TESTS.md).
- **Supersedes:** `research/VERIFIED-FEATURE-SPEC.md` (S2) where they differ. Every difference is marked **Δ**.

**Goal.** Reproduce The Plumber's observable journey, and add evidence-based attribution as the differentiator:

1. a failed GitHub Actions run;
2. an automatic diagnosis with root cause, file and line, a fix, and the files examined;
3. the report posted on the commit or PR.

**Platform facts used.** Marked "GitHub-doc" where taken from GitHub's public documentation (audit §3.1). Anything only community-reported is marked **UNVERIFIED** and must pass a LIVE test before being relied on.

**Priority key**

| Priority | Meaning |
|---|---|
| **P0** | Core parity |
| **P1** | Important, deferrable |
| **P2** | Differentiation |
| **—** | Out of MVP |

---

## 1. Parity table

| ID | Feature | Competitor evidence | Confidence | Tracewise requirement | Acceptance test | Priority |
|---|---|---|---|---|---|---|
| FS-INS-1 | Install as a GitHub App; no repo config | P-13, P-14 (DOCUMENTED "No config changes") | High | A public GitHub App works with zero files added to the repo. Analysis starts on the next failed run after install. | AT-INS-01 | P0 |
| FS-INS-2 | Permission set | P-1, P-9 (VERIFIED) | High | `actions:read`, `contents:read`, `metadata:read`, `pull_requests:write`, plus our addition `checks:write` (FS-PUB-3). No other repository write scopes. Δ: **no user-to-server authorization** in the MVP: no "request user authorization during installation", no OAuth callback. | AT-INS-02, AT-SEC-01 | P0 |
| FS-INS-3 | Uninstall and suspend | UNKNOWN | — | On `installation.deleted` or `suspend` (delivered to all Apps by default; GitHub-doc), stop new jobs. In-flight jobs end `cancelled_uninstalled` with no publish. Purge tenant data ≤7 days. | AT-INS-03 | P1 |
| FS-INS-4 | Repository selection | GitHub-native (P-9 note: "all or selected repositories") | High | Honour `installation_repositories` added and removed | AT-INS-04 | P1 |
| FS-EVT-1 | Trigger on a failed run | P-1, P-6 (fired on `push`/`failure`) | High for `failure` | Analyse when `action=completed` and `conclusion ∈ {failure, timed_out}`. Δ: `startup_failure` is analysed **only if** LIVE test AT-EVT-04 shows GitHub delivers it (UNVERIFIED, audit U-7). Ignore `success`, `cancelled`, `skipped`, `neutral` and `action_required`. | AT-EVT-01..04 | P0 |
| FS-EVT-2 | Asynchronous processing | P-6 (INFERRED strong) | High | 2xx within 10 s of a verified delivery (GitHub-doc expectation). All work in a background worker. | AT-EVT-05 | P0 |
| FS-EVT-3 | Webhook authenticity and size | Competitor UNKNOWN | — | Verify `X-Hub-Signature-256` (HMAC-SHA256 over the raw body, constant-time) **before** parsing. 401 on mismatch. Δ: reject bodies >25 MB with 413. GitHub-doc: "Payloads are capped at 25 MB". | AT-SEC-02 | P0 |
| FS-EVT-4 | Deduplication | Competitor UNKNOWN; its commit comments can't be edited (P-2) | — | Idempotent on `X-GitHub-Delivery` **and** on `(repo_id, run_id, run_attempt)`. Re-runs update existing editable surfaces (FS-PUB-4). | AT-EVT-06, AT-PUB-05 | P0 |
| FS-EVT-5 | Missed-delivery recovery | — | — | GitHub does not auto-redeliver failed deliveries (GitHub-doc, verified 2026-10-15). A periodic reconciliation redelivers failed or unknown deliveries via the App deliveries API. | AT-REL-03 | P1 |
| FS-EVT-6 | Concurrency | UNKNOWN | — | Global worker cap; ≤2 concurrent per installation; one analysis per `(repo, run_id)` at a time | AT-REL-04 | P1 |
| FS-LOG-1 | Retrieve failed-job logs | P-14 (DOCUMENTED), consistent with P-3 | Medium-high | List jobs for the run attempt. For each failed job, `GET /actions/jobs/{id}/logs` with an installation token. GitHub-doc: 302 to a URL valid for 1 minute. | AT-LOG-01 | P0 |
| FS-LOG-2 | Name the failed job **and step** | P-4/P-8: the competitor shows the *command* (`pytest --tb=short -v`), not the step name ("Run pytest") | High (n=1) | Report job name, step name and the step's command where derivable. Step boundaries come from the jobs API `steps[]` plus log group markers. **Not from log text alone** (FS-SEC-2). | AT-LOG-02 | P0 |
| FS-LOG-3 | Logs unavailable | P-17: public 403; expiry INFERRED | High (platform) | 404/410 on logs → an "inconclusive: logs unavailable" report with run metadata only, never a guessed cause. 403 → `permission_denied` path (FS-ERR-3). | AT-LOG-03 | P0 |
| FS-LOG-4 | Large logs | UNKNOWN | — | Stream. Keep failed-step sections, ±200 lines around each `##[error]` and the first error-like line, ≤2 MB per job. If anything was dropped, set `log_truncated=true` and say so. | AT-LOG-04 | P0 |
| FS-LOG-5 | Secret redaction | UNKNOWN | — | Keep GitHub's `***`. Add a regex and entropy pass **before** any storage or LLM call. | AT-SEC-04 | P0 |
| FS-CTX-1 | Read repo code at the failing commit | P-5/P-8: code read VERIFIED; clone DOCUMENTED (P-14, P-11) | High that code is read | Read-only tree at `head_sha`. Either: ephemeral partial clone (`--filter=blob:none`, hooks disabled, LFS skipped, no build or test execution), using the installation token; or contents-API range fetches. Repo cap 1 GB; skip files >1 MB. | AT-CTX-01..03 | P0 |
| FS-CTX-2 | Record files and ranges examined | P-8: the competitor's ranges and paths are not repo-true | High | `files_examined` comes from the tool-call log: actual `{path, start, end}`, repo-root-relative, clipped to EOF. Never from model text. | AT-CTX-04, AT-RPT-06 | P0 |
| FS-CTX-3 | Trigger and diff context | No positive evidence the competitor uses it (P-7) | — | Fetch the trigger commit's changed files: vs its parent for push; vs merge base for PR (compare API; Contents read) | AT-ATR-01 | P0 (needed by FS-ATR-1) |
| FS-CTX-4 | Workspace cleanup | P-11 (self-attested) | Low as fact | Delete the workspace in `finally` on all paths. Startup sweep of stale dirs. Never persist source. | AT-SEC-06 | P0 |
| FS-DX-1 | First causal error | P-3 (n=1: first failing assertion) | High (n=1) | Deterministic ranker by step order and timestamp; downstream cascades marked secondary | AT-DX-02, AT-DX-07 | P0 |
| FS-DX-2 | Group siblings | P-3 ("…and 3 other test failures") | High (n=1) | Group by normalised fingerprint plus shared implicated location; report the count and names | AT-DX-03 | P0 |
| FS-DX-3 | Explain *why* (mechanism) | P-4, P-5 | High | Bounded LLM investigation with read-only tools (`read_file`, `grep`, `list_dir`, `get_commit_diff`). ≤12 tool calls, ≤120 s, token budget. Structured output (§3). The model is selected by eval, not by recency. | AT-DX-01, AT-DX-04 | P0 |
| FS-DX-4 | Problematic code (file, line, snippet) | P-4, P-5 | High | `problem_location` must lie inside an examined range. The snippet is copied by the system from the file at `head_sha`. | AT-DX-05, AT-VAL-02 | P0 |
| FS-DX-5 | Recommended fix (text and replacement) | P-4, P-5 (correct on n=1) | High | `fix.description` ≤600 chars, plus an optional single-location `replacement` (≤20 lines). Text only: no commits, branches or PRs. Omitted for non-code categories or low confidence. | AT-DX-06 | P0 |
| FS-DX-6 | Non-code categories | Competitor UNKNOWN (no category field, P-4) | — | `code_regression`, `test_defect`, `dependency`, `config_secret`, `infra_runner`, `flaky_suspect`, `workflow_invalid`, `unknown`. Non-code categories produce `next_steps` instead of a code fix. | AT-DX-08..11 | P1 |
| FS-DX-7 | Confidence with a basis | P-4: "High" with no basis | High | Band `high`/`medium`/`low` plus `basis[]`. No numeric probability until calibrated. | AT-DX-12 | P0 |
| FS-DX-8 | Abstain | UNKNOWN | — | `status=inconclusive` when the validator rejects the root cause, no error line is found, logs are unavailable or truncated past the error, or the budget is exhausted. Then 1–3 diagnostic steps and **no fix**. | AT-DX-13, AT-DX-14 | P0 |
| FS-ATR-1 | Trigger-diff relevance | **Gap observed n=1** (P-7) | High (n=1) | Compute whether the trigger's changed files intersect the implicated files. Say "this push changed only X; none implicated; likely pre-dates it", "…changed X, which is implicated", or "unknown". **Evidence, not a verdict:** lane history (FS-ATR-2) and dependency or runner signals (FS-ATR-4) override it. The intersection is computed by code. | AT-ATR-01..03, AT-ATR-09 | **P2, ship in MVP** (cheap) |
| FS-ATR-2 | Lane last-green / first-bad | Gap (P-7) | — | Lane = `(repo_id, workflow_id, event_class, branch, head_repo_id)`. Name the commit range; name a commit only with a direct link (per IMPLEMENTATION-PLAN §7.8). | AT-ATR-04..06 | P2 |
| FS-ATR-3 | Flaky suspicion | — | — | Same fingerprint passed on the same `head_sha` in another attempt, or alternates in the lane → `flaky_suspect`, with re-run as the first step | AT-ATR-07 | P2 |
| FS-ATR-4 | Dependency drift | — | — | Resolved versions differ from last green with no lockfile change, **and** the error references the package → `dependency` | AT-ATR-08 | P2 |
| FS-RPT-1..6 | Report: Summary; What Failed; Why; Problematic Code; Recommended Fix; Files Examined | P-4 | High | As in S2 spec FS-RPT-1..6. Δ: Summary names the job and step **and** the command (FS-LOG-2). | AT-RPT-01..06 | P0 |
| FS-RPT-7 | Attribution section | Absent (P-7) | — | FS-ATR-1 always; FS-ATR-2 when available | AT-RPT-07 | P2 (MVP) |
| FS-RPT-8 | For AI Agents block | P-4 (VERIFIED); P-14 names Cursor, Claude Code and Windsurf (DOCUMENTED) | High | Fenced plain-text block with: repo, `head_sha`, job and step, reproduce command (when the step's `run:` is a single command), location, fix instruction, verify command. **No URLs.** Only for `diagnosed` code or test categories. | AT-RPT-08 | P0 |
| FS-RPT-9 | Links to the run, job, commit and blob | Absent in competitor (P-8) | — | Footer links built by code from IDs, never from model text | AT-RPT-09 | P1 |
| FS-RPT-10 | Size and safety | — | — | Δ: ≤60,000 chars for comments and ≤60,000 for check output. GitHub's limits are **community-reported (~65,536), not documented: UNVERIFIED**; AT-PUB-08 measures them. Escape `@` mentions and HTML. No model-supplied links. | AT-SEC-07, AT-PUB-08 | P0 |
| FS-PUB-1 | Push failure → commit comment | P-3 (VERIFIED) | High | One new commit comment on `head_sha`. Needs only Contents read (GitHub-doc). **Cannot be edited** (Contents write needed; GitHub-doc), so post exactly once per `(repo, head_sha, workflow_id)`, on the **first** completed analysis. Later attempts and outcomes update only the Check Run. | AT-PUB-01, AT-PUB-05 | P0 |
| FS-PUB-2 | PR failure → PR comment | P-13 (DOCUMENTED; never observed, P-12) | Medium | One PR comment per `(PR, workflow_id)`, **upserted** (edited) via `pull_requests:write` (GitHub-doc: create and edit allowed) | AT-PUB-02, AT-PUB-05 | P0 |
| FS-PUB-3 | Check Run | Competitor cannot (P-2) | — | One "Tracewise" Check Run per `(head_sha, run)`, conclusion `neutral`, with the report in `output.text` and ≤10 annotations, updated in place | AT-PUB-03 | P1 |
| FS-PUB-4 | Re-run behaviour | Competitor constraint P-2 | — | A new attempt updates the Check Run and the PR comment. No new commit comment. | AT-PUB-05 | P0 |
| FS-PUB-5 | Fork PRs | UNKNOWN | — | Attempt a PR comment and a Check Run. On 403, record `unpublished_permission`. No crash, no silent drop. | AT-PUB-06 | P1 |
| FS-PUB-6 | Outcome tracking | — | — | The next completed run in the lane marks the analysis `resolved`, `still_failing_same` or `different_failure`, on editable surfaces only | AT-PUB-07 | P2 |
| FS-ERR-1 | Analysis failure | UNKNOWN | — | "Could not complete" Check Run, plus a short PR comment on PRs. **No commit comment** on push. Retry ≤2. | AT-REL-01 | P0 |
| FS-ERR-2 | Rate limits and 5xx | — | — | Honour `retry-after` and `x-ratelimit-reset`; backoff; 10-min job deadline (GitHub-doc rate-limit guidance) | AT-REL-02 | P0 |
| FS-ERR-3 | Missing permission | — | — | A 403 on a needed call → state the missing permission where we can still publish; plus a metric | AT-REL-05 | P1 |
| FS-QTA-1 | Quota | P-13 (10/month free, DOCUMENTED) | Medium | Configurable monthly quota per installation. Over quota → one "quota reached" Check Run per day per repo; no comments. | AT-QTA-01 | P1 |
| FS-SEC-1 | Prompt-injection resistance | UNKNOWN | — | Logs, code, commit and PR text are untrusted and delimited. Tools are read-only, path-confined (no `..`, no symlinks out) with no network. Output is schema-validated. The renderer ignores model URLs and mentions. Δ: **P0 tests are in the MVP, not optional.** | AT-SEC-08..10 | P0 |
| FS-SEC-2 | Log spoofing | — | — | Repo code can print fake `##[error]`, `Successfully installed`, and so on. Step boundaries come from the jobs API. Dependency or runner claims require a structured corroborating signal (lockfile diff, job metadata) or are capped at `low`. | AT-SEC-11 | P0 (Δ from P1) |
| FS-SEC-3 | Data retention | P-11 (self-attested claim) | — | Persist run metadata, report text, redacted excerpts ≤2 KB (90 days) and fingerprints (365 days). Never raw logs or source. A tenant purge path exists. | AT-SEC-06, AT-SEC-12 | P0 |
| FS-SEC-4 | LLM provider disclosure | P-11: competitor discloses "AI inference provider (LLM API)", model unnamed | — | Name our provider **and** model family in the privacy notice and in our own Marketplace Transparency section. Use the provider's no-training / retention settings. | AT-SEC-13 | P0 |
| FS-SEC-5 | Credential hygiene (Δ new) | — | — | Installation tokens scoped to the repo and the needed permissions, memory-only, ≤1 h. **No personal or global CLI credentials** are used by the service, tests or benchmark tooling. The benchmark uses a project-scoped token approved per project. | AT-SEC-05, AT-SEC-14 | P0 |
| FS-OPS-1 | Observability | UNKNOWN | — | Per-analysis stage timings, tokens, cost, outcome and publish result; an alert on a failure rate >10%/h | AT-OPS-01 | P1 |
| FS-OPS-2 | Latency | P-6: 6m14s observed (n=1) vs "<2 min" claimed (P-14) | n=1 | **Target**, unmeasured: p50 ≤2 min, p95 ≤5 min; hard deadline 10 min | AT-OPS-02 | P1 |

## 2. Classification

| Class | Features |
|---|---|
| **Core parity (P0)** | FS-INS-1/2; FS-EVT-1–4; FS-LOG-1–5; FS-CTX-1–4; FS-DX-1–5, 7, 8; FS-RPT-1–6, 8, 10; FS-PUB-1, 2, 4; FS-ERR-1, 2; FS-SEC-1–5 |
| **Important, deferrable (P1)** | FS-INS-3/4; FS-EVT-5/6; FS-DX-6; FS-PUB-3, 5; FS-RPT-9; FS-ERR-3; FS-QTA-1; FS-OPS-1/2 |

**Unverified competitor behaviour (do not design to it as fact):**

- agentic tool loop; clone vs API; workspace deletion; retention;
- LLM vendor and model;
- PR-comment format and edits;
- dedupe and re-runs; non-`failure` conclusions;
- behaviour on any class except one Python unit-test regression;
- latency beyond n=1;
- whether the attribution gap still exists today.

**Differentiation supported by evidence:**

| Feature | Evidence |
|---|---|
| FS-ATR-1 trigger-diff relevance | P-7, n=1 |
| FS-DX-7 / FS-DX-8 evidence-based confidence and abstention | P-4 |
| FS-PUB-3/4 editable surfaces, no duplicate comments on re-run | P-2 |
| FS-RPT-9 links back to run, job, commit and blob | P-8 |
| FS-CTX-2 repo-true paths and ranges | P-8 |
| FS-SEC-4 named model in the disclosure | P-11 |

All are claims about **one sample**. Marketing claims need AT-CMP-01.

**Out of MVP:**

- fix PRs and commits;
- sandbox execution;
- dashboard and billing;
- Slack;
- non-GitHub CI;
- self-hosting and BYO key;
- cross-repo or fork-parent history;
- cross-tenant signals.

## 3. Data contracts

`Diagnosis` v2 and validator rules 1–6 are **as in the S2 spec §3**, with these Δ:

- `failed[]` items must include `step` (the name from the jobs API) **and** `command`.
- `attribution.basis` must contain `no_lane_history` when no in-lane baseline exists (the coffee_shop situation, P-6).
- **Validator rule 7 (new):** every URL in the rendered report is generated by code from repository, run, job, SHA and path identifiers. Any URL-like token in model text is stripped.
- **Validator rule 8 (new):** `trigger_touches_implicated`, `last_green_sha`, `first_bad_sha` and `introducing_sha` are set **only** by deterministic code. Model output for these fields is ignored.

## 4. Reference architecture

As in [FINAL-REVERSE-ENGINEERING-AUDIT.md](FINAL-REVERSE-ENGINEERING-AUDIT.md) §8 (Part B), which carries over IMPLEMENTATION-PLAN ADR-01/03/05/09. Its components:

- one Python service with `web` and `worker` processes;
- a Postgres job table;
- an ephemeral code context;
- a bounded investigator;
- a validator;
- a publisher for the Check Run plus a commit or PR comment.

Changes from IMPLEMENTATION-PLAN v1 are listed in audit §11.2.
