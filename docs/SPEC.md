# Tracewise MVP Feature Specification (canonical)

Version 2.0, 2026-10-18. Supersedes all earlier specs (see `research/README.md` path map).

**References**

| Prefix | Document |
|---|---|
| EV-… | `research/final-evidence-review/EVIDENCE-LEDGER.md` |
| AT-… | [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md) |
| T-… | [TASKS.md](TASKS.md) |

**Priority**

| Priority | Meaning |
|---|---|
| **P0** | MVP core: must pass before the MVP is complete |
| **P1** | Before the first external installation |
| **P2** | Later: validate first |

**Product scope (decided 2026-10-18).** When a GitHub Actions workflow run fails, Tracewise:

1. runs a deterministic pre-pass over the failed jobs' logs;
2. runs a bounded, read-only AI investigation of the relevant repository code;
3. validates every claim against evidence (falling back to *inconclusive*);
4. publishes a diagnosis to a commit comment or PR comment, and a neutral Check Run.

**Supported customer repositories:** Python (pytest, ruff, mypy) and TypeScript (tsc, jest, vitest, eslint). Other ecosystems get generic handling only.

**Implementation language:** Python (D-2).

**No accuracy, latency or cost claims** are made until they are measured on the benchmark ([BENCHMARK.md](BENCHMARK.md)).

## 1. Requirements

### 1.1 Installation and permissions

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-INS-1 | Public GitHub App; works with no files added to the repo; analysis starts on the next failed run | EV-C04, EV-C05 | AT-INS-01 | T-101, T-801 | P0 |
| FS-INS-2 | Permissions exactly: Actions **read**, Contents **read**, Metadata **read**, Pull requests **write**, Checks **write**. No other repository write scope. No user-to-server authorization. Event: `workflow_run`. | EV-P09; Q2 | AT-INS-02, AT-SEC-01 | T-301, T-801 | P0 |
| FS-INS-3 | On `installation.deleted` / `suspend`: stop new jobs. In-flight jobs whose token mint fails end as `cancelled_uninstalled` with no publish. Purge tenant data after a grace period (default 7 days). | EV-P21 | AT-INS-03 | T-701 | P1 |
| FS-INS-4 | Honour `installation_repositories` added and removed | EV-P21 | AT-INS-04 | T-701 | P1 |

### 1.2 Events and orchestration

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-EVT-1 | Analyse `workflow_run` with `action=completed` and `conclusion ∈ {failure, timed_out}`. Ignore all other conclusions. `startup_failure` is excluded until live gate G-PLAT-1. | EV-P01, EV-P03 | AT-EVT-01..04 | T-106 | P0 |
| FS-EVT-2 | Webhook returns 2xx within 10 s. All work happens in a background worker. Delivery row and job row are inserted in **one transaction**. | EV-P05 | AT-EVT-05 | T-105, T-106 | P0 |
| FS-EVT-3 | Verify `X-Hub-Signature-256` (HMAC-SHA256 over the raw body, constant-time) before parsing. Missing or invalid → 401. Body >25 MB → 413 (defensive). | EV-P07, EV-P04 | AT-SEC-02 | T-106 | P0 |
| FS-EVT-4 | Idempotent on `X-GitHub-Delivery` and on `(repo_id, run_id, run_attempt)`. No ordering assumptions. | EV-P02, EV-P06, EV-P08 | AT-EVT-06 | T-105, T-106 | P0 |
| FS-EVT-5 | Recovery: (a) redeliver failed deliveries via `GET /app/hook/deliveries` and `POST /app/hook/deliveries/{id}/attempts`; (b) a bounded periodic sweep of recent failed runs per enabled repo, because events over 25 MB are never delivered | EV-P06, EV-P04 | AT-REL-03 | T-702 | P1 |
| FS-EVT-6 | Concurrency: global worker cap; ≤2 concurrent per installation; one analysis per `(repo, run_id)` at a time | EV-P18 | AT-REL-04 | T-105 | P1 |

### 1.3 Logs (deterministic pre-pass)

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-LOG-1 | List jobs for the run attempt. Download only failed jobs' logs (`GET /actions/jobs/{id}/logs`; 302 → URL valid 1 min) with the installation token. | EV-P09, EV-P12 | AT-LOG-01 | T-302 | P0 |
| FS-LOG-2 | The failed job and step come from the **jobs API** (`steps[]`). Log group markers are used only to slice text. The report names the job, the step **and** the step's command where derivable. | EV-P25, EV-C12 | AT-LOG-02, AT-SEC-11 | T-201 | P0 |
| FS-LOG-3 | Logs 404/410 → `logs_unavailable` report with metadata only; never a guessed cause. 403 → `permission_denied` (FS-ERR-3). | EV-P13, EV-P14 | AT-LOG-03 | T-302, T-503 | P0 |
| FS-LOG-4 | Stream. Keep the failed-step section, ±200 lines around each error marker and the first error-like line, ≤2 MB per job. Set `log_truncated` and show it. | — | AT-LOG-04 | T-206 | P0 |
| FS-LOG-5 | Before any storage or LLM call: strip ANSI and control sequences (including OSC 8 and C1 controls); redact secrets (GitHub `***`, then regex and entropy) | — | AT-SEC-04, AT-LOG-06 | T-202 | P0 |
| FS-DX-1 | Rank candidate errors by step order and line. Mark downstream cascades as secondary. | EV-C07 | AT-DX-02, AT-DX-07 | T-205 | P0 |
| FS-DX-2 | Group sibling failures by normalised fingerprint and shared location. Report the count and names. ≤3 independent primaries. | EV-C07 | AT-DX-03, AT-DX-16 | T-205 | P0 |
| FS-DX-9 | Extractors for pytest, Python tracebacks, ruff, mypy, tsc, jest/vitest and eslint, plus a generic fallback. Regexes are time-bounded and line-length-capped. | D-2 | AT-LOG-05, AT-SEC-15 | T-203, T-204, T-205 | P0 |

### 1.4 Code context and investigation

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-CTX-1 | Read-only tree at `workflow_run.head_sha`. A shallow single-commit **object** fetch into a per-job temporary bare repository; **no checkout**; hooks disabled, LFS smudge off, no submodule init and no execution. Contents-API fallback at the same SHA; otherwise an explicit unavailable result. Skip files >1 MB and binaries. | EV-P16, EV-P17, EV-P22 | AT-CTX-01..02 | T-304 | P0 |
| FS-CTX-2 | `files_examined` is taken from the tool-call log: `{path, start, end}`, repo-relative, clipped to EOF. Never from model text. | EV-C12 | AT-CTX-04, AT-RPT-06 | T-305, T-403 | P0 |
| FS-CTX-3 | Trigger diff: changed files of `head_sha` vs its parent (push) or the merge base (PR), via the compare API. Truncation flagged (≤250 commits, ≤300 files). | EV-P15 | AT-ATR-01 | T-306 | P0 |
| FS-CTX-4 | Workspace deleted in `finally`, plus a startup sweep. Source is never persisted. | EV-C03 | AT-SEC-06 | T-304 | P0 |
| FS-CTX-5 | Path safety: every tool path is validated and resolved **inside the commit's tree** (never on a filesystem). Reject `..`, absolute paths, unsafe encodings, and symlinks resolving outside the tree. Submodules are reported as "not inspected". | EV-P16 | AT-CTX-03, AT-SEC-09 | T-305 | P0 |
| FS-CTX-6 | For PR runs, the report states that CI tested the merge with the base branch | EV-P20, EV-P22 | AT-RPT-11 | T-501 | P1 |
| FS-DX-3 | Bounded investigation behind a **provider interface** (OpenAI first; others pluggable). Tools: `read_file(path,start,end)`, `grep(pattern,glob)`, `list_dir(path)`, `get_diff()`. **No** write, exec or network tools. ≤12 tool calls, ≤120 s, token budget. Structured output; 1 repair attempt, then inconclusive. Offline tests use a deterministic fake provider; no API key is needed. | Q1, Q4 | AT-DX-01, AT-DX-04, AT-SEC-10 | T-401, T-402 | P0 |
| FS-DX-4 | `problem_location` lies within an examined range. The snippet is copied by the system from the file at `head_sha`. | EV-C07 | AT-DX-05 | T-403 | P0 |
| FS-DX-5 | Text-only fix: `fix.description` ≤600 chars + optional single-location `replacement` ≤20 lines. No commits, branches or PRs. Omitted for non-code categories or low confidence. | Q1 | AT-DX-06 | T-402, T-403 | P0 |
| FS-DX-6 | Categories: `code_regression`, `test_defect`, `dependency`, `config_secret`, `infra_runner`, `flaky_suspect`, `workflow_invalid`, `unknown`. Non-code categories get `next_steps`, not a code fix. | — | AT-DX-08..11 | T-402 | P1 |
| FS-DX-7 | Confidence band `high`/`medium`/`low` + `basis[]`. `high` requires deterministic corroboration: the error references the location, or a changed line. No numeric probability. | EV-C07 | AT-DX-12 | T-404 | P0 |
| FS-DX-8 | `inconclusive` when the validator rejects the root cause, no error line exists, logs are truncated past the error, the budget is exhausted, or the provider fails. 1–3 next steps; **no fix**. | — | AT-DX-13, AT-DX-14 | T-403 | P0 |

### 1.5 Attribution

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-ATR-1 | Trigger-diff relevance, **a signal, not proof**: `touches_implicated` = true / false / unknown, computed by code from FS-CTX-3 and the implicated paths. Wording: "changed only X; not implicated; likely pre-dates this push" / "changed X, which is implicated" / unknown. Never "caused by". | EV-C11, EV-P26 | AT-ATR-01..03, AT-ATR-09 | T-306 | P0 |
| FS-ATR-2 | Lane history: last green / first red; lane = `(repo_id, workflow_id, event_class, branch, head_repo_id)` | EV-P26 | AT-ATR-04..06 | T-901 | P2 |
| FS-ATR-3 | Flaky suspicion (the same SHA passes on another attempt) | EV-P02 | AT-ATR-07 | T-902 | P2 |
| FS-ATR-4 | Dependency drift with structured corroboration (lockfile diff) | — | AT-ATR-08 | T-903 | P2 |

### 1.6 Report

| ID | Requirement | Tests | Tasks | Pri. |
|---|---|---|---|---|
| FS-RPT-1 | Summary: job, step, command, one-sentence root cause, confidence band, fix size | AT-RPT-01 | T-501 | P0 |
| FS-RPT-2 | What Failed: ≤15 redacted verbatim log lines + sibling count | AT-RPT-02 | T-501 | P0 |
| FS-RPT-3 | Why It Failed: ≤800 chars | AT-RPT-03 | T-501 | P0 |
| FS-RPT-4 | Problematic Code: repo-relative `path:line` (no duplicated prefix), linked to the blob at `head_sha`, ≤15-line snippet | AT-RPT-04 | T-501 | P0 |
| FS-RPT-5 | Recommended Fix (FS-DX-5) | AT-RPT-05 | T-501 | P0 |
| FS-RPT-6 | Files Examined with true ranges and verdicts | AT-RPT-06 | T-501 | P0 |
| FS-RPT-7 | Attribution line (FS-ATR-1) | AT-RPT-07 | T-501 | P0 |
| FS-RPT-8 | For AI Agents: plain-text block (repo, SHA, job and step, reproduce command, location, fix instruction, verify command), **no URLs**; only for diagnosed code or test categories | AT-RPT-08 | T-501 | P0 |
| FS-RPT-9 | Links to the run, job, commit and blob, generated by code from IDs only | AT-RPT-09 | T-501 | P1 |
| FS-RPT-10 | Size and safety. Provisional cap 60,000 chars per surface; GitHub limits are undocumented (EV-P11), to be confirmed by G-PLAT-3. Mentions and HTML escaped. Model-supplied URLs stripped. | AT-SEC-07, AT-PUB-08 | T-501 | P0 |

### 1.7 Publishing

| ID | Requirement | Evidence | Tests | Tasks | Pri. |
|---|---|---|---|---|---|
| FS-PUB-1 | Push failure → **one** commit comment on `head_sha` per `(repo, head_sha, workflow_id)`, on the first completed analysis. It is never edited (editing needs Contents write, which we do not request). | EV-P09, EV-C06 | AT-PUB-01 | T-502 | P0 |
| FS-PUB-2 | PR failure → **one** PR comment per `(PR, workflow_id)`, upserted (edited) on later runs and attempts. Found by our App as author plus a hidden marker. | EV-P09 | AT-PUB-02 | T-502 | P0 |
| FS-PUB-3 | Neutral Check Run "Tracewise" per `(head_sha, run_id)`: `external_id=run_id`, conclusion `neutral`, report in `output.text`, ≤10 annotations, updated in place. Looked up by `check_name` before creating. | EV-P10; Q2 | AT-PUB-03 | T-502 | P0 |
| FS-PUB-4 | Re-runs: a new attempt updates the Check Run and PR comment. **No new commit comment.** | EV-P02 | AT-PUB-05 | T-502 | P0 |
| FS-PUB-5 | Fork PRs: attempt the PR comment and Check Run. On 403, record `unpublished_permission`. No crash, no silent drop. | EV-P10 | AT-PUB-06 | T-502, T-503 | P1 |
| FS-PUB-6 | Outcome tracking on the next run in the lane, on editable surfaces only | — | AT-PUB-07 | T-904 | P2 |
| FS-PUB-7 | **PR association by API, never from `workflow_run.pull_requests`.** Same-repo: `GET /commits/{head_sha}/pulls`, filtered to open PRs whose `head.sha == head_sha`. Fork (`head_repository.id ≠ repository.id`): `GET /pulls?state=open&head={head_owner}:{head_branch}`, filtered the same way. No match → treat as a push (commit comment). Several matches → ambiguous: no PR comment (D-4). | EV-P23, EV-P24 | AT-PUB-09, AT-PUB-10 | T-303 | P0 |

### 1.8 Errors, quotas, security, operations

| ID | Requirement | Tests | Tasks | Pri. |
|---|---|---|---|---|
| FS-ERR-1 | Internal failure after logs are fetched → "could not complete" Check Run, plus a PR comment on PRs. **No commit comment.** Retry ≤2. | AT-REL-01 | T-503 | P0 |
| FS-ERR-2 | Honour `retry-after` and `x-ratelimit-reset`; backoff; job deadline 10 min | AT-REL-02 | T-302 | P0 |
| FS-ERR-3 | 403 on read or publish → record the missing permission; publish on the remaining surfaces; metric; no retry loop | AT-REL-05 | T-503 | P1 |
| FS-QTA-1 | Monthly per-installation analysis quota. Over quota → one "quota reached" Check Run per day per repo; no comments. | AT-QTA-01 | T-703 | P1 |
| FS-SEC-1 | Prompt injection: untrusted data is delimited; tools are read-only; schema output; validator; escaped rendering | AT-SEC-08..10 | T-402, T-403, T-501 | P0 |
| FS-SEC-2 | Log spoofing: steps from the jobs API; printed versions and markers alone never drive attribution (capped at `low`) | AT-SEC-11 | T-201, T-306 | P0 |
| FS-SEC-3 | Retention: never persist raw logs or source. Redacted excerpts ≤2 KB for 90 days. Fingerprints and metadata ≤365 days. Tenant purge. | AT-SEC-12 | T-704 | P1 |
| FS-SEC-4 | Privacy notice names the LLM provider (OpenAI first) and the model family in use | AT-SEC-13 | T-1001 | P1 |
| FS-SEC-5 | Credentials: installation tokens scoped to the repo and permissions, memory-only, ≤1 h. The service, tests and **benchmark tooling use no personal, global or CLI GitHub credentials.** The LLM key comes from local env only, never committed or logged. | AT-SEC-05, AT-SEC-14 | T-301, T-102 | P0 |
| FS-SEC-6 | Tenant isolation: tenant key from `installation.id`; Postgres RLS with transaction-local context before the first external installation | AT-SEC-03 | T-705 | P1 |
| FS-OPS-1 | Per-analysis stage timings, token usage, cost, outcome and publish result; failure-rate alert | AT-OPS-01 | T-706 | P1 |
| FS-OPS-2 | Latency is a **target only** (unmeasured): p95 < the 10-min deadline. Report measured values; no claim before measurement. | AT-OPS-02 | T-706 | P1 |

## 2. Out of scope (MVP)

- fix commits, branches or PRs;
- test or code execution;
- dashboard;
- billing integration;
- Slack;
- non-GitHub CI;
- self-hosting;
- cross-repo history;
- TypeScript services.

## 3. Data contracts

### 3.1 Diagnosis v2 (JSON)

```json
{
  "schema_version": "2",
  "run": {"repo_id": 0, "repo": "o/r", "run_id": 0, "attempt": 1, "head_sha": "<40 hex>", "event": "push|pull_request", "pr_number": null},
  "status": "diagnosed | inconclusive | logs_unavailable | permission_denied",
  "failed": [{"job_id": 0, "job": "Tests (Python 3.11)", "step": "Run pytest", "command": "pytest --tb=short -v"}],
  "primary_errors": [{"log_ref": {"job_id": 0, "line_start": 0, "line_end": 0}, "excerpt": "<redacted>", "fingerprint": "<16 hex>",
                      "siblings": {"count": 0, "names": []}}],
  "category": "code_regression | test_defect | dependency | config_secret | infra_runner | flaky_suspect | workflow_invalid | unknown",
  "root_cause": "≤300 chars",
  "why": "≤800 chars",
  "problem_location": {"path": "pkg/mod.py", "line_start": 41, "line_end": 41},
  "fix": {"description": "≤600 chars", "replacement": {"path": "pkg/mod.py", "line_start": 41, "line_end": 41, "new_text": "…"}, "size": "trivial|small|larger|n/a"},
  "next_steps": ["≤3, ≤160 chars each"],
  "files_examined": [{"path": "pkg/mod.py", "start": 1, "end": 43, "verdict": "≤140 chars"}],
  "attribution": {"trigger_sha": "…", "trigger_changed_files": ["README.md"], "touches_implicated": "true | false | null", "statement": "…", "basis": ["trigger_diff"]},
  "confidence": {"band": "high|medium|low", "basis": ["…"]},
  "limits": {"log_truncated": false, "files_skipped": [], "budget_exhausted": false, "diff_truncated": false},
  "usage": {"provider": "openai|fake", "model": "…", "input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "latency_ms": 0}
}
```

### 3.2 Validator rules (fail closed to `inconclusive`)

1. Each `primary_errors[].log_ref` range exists in the retained log, and the excerpt is a substring of it after redaction.
2. `problem_location` lies within a `files_examined` range, and `files_examined` equals the tool log.
3. `fix.replacement.path == problem_location.path`, and the replaced lines exist.
4. Every path in `root_cause`, `why` or `fix.description` exists at `head_sha`. Otherwise it is stripped and flagged.
5. `attribution.*` is computed by code only. Model-supplied values are ignored.
6. If rule 1 or 2 fails → `inconclusive`, the fix is removed, and `next_steps` are kept.
7. Every URL in the rendered report is built by code from IDs. URL-like tokens from the model are removed.
8. `high` confidence requires deterministic corroboration (FS-DX-7). Otherwise it is downgraded to `medium`.
