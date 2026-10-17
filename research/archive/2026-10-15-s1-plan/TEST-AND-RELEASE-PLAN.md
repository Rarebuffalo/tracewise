# Test and Release Plan

Date: 2026-10-15. This turns `04-failure-benchmark.md` into an executable plan, aligned with [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) §7.

**Nothing in this document has been executed.** Every result table is empty until the tasks run.

## 1. Principles

1. **Ground truth comes first.** Every case's `truth.yaml` is committed before any tool, ours or a competitor's, is run on it.
2. **Synthetic ≠ real.** The benchmark cases (B-xx) prove mechanics. The labeled real-run set (Phase 0, held-out half) proves usefulness. They are reported separately and never averaged together.
3. **False blame is the primary failure.** Every gate lists it first.
4. **Plausible but wrong scores zero:**
   - category and subject must both match;
   - a cited locator that doesn't hold → the whole diagnosis scores zero;
   - naming a commit outside `acceptable_suspects` counts as false blame.

## 2. Benchmark cases (preserved from R-04, with amendments)

**Commit pattern per case:**

| Commit | Content |
|---|---|
| C0 | Green baseline |
| C1 | Fault injection, or an unrelated commit for external causes |
| C2 | Unrelated `README.md` change |

Runs are recorded separately for C1 and C2. Categories use the Plan §2.4 enum.

| ID | Ground truth (from R-04) | Expected on **C1 run** | Expected on **C2 run** | Acceptable alternatives | Must NOT |
|---|---|---|---|---|---|
| B-01 | tsc: renamed export | `CHANGE_IN_RANGE` → C1 (L1/L4) | `PRE_EXISTING` (first bad = C1) | — | Name C2 |
| B-02 | pytest: `subtotal * TAX_RATE` in `pricing.py` | `CHANGE_IN_RANGE` → C1 (L5) | `PRE_EXISTING` (first bad = C1) | C1: `INTRODUCED_IN_RANGE` (range = C1, no link) if L5 is not implemented | Name C2; say C2 caused it |
| B-03 | jest snapshot after intended UI change | `CHANGE_IN_RANGE` → C1 (L1/L5); next action mentions updating the snapshot if intended | `PRE_EXISTING` | — | Name C2 |
| B-04 | Flaky (amended: fails when `GITHUB_RUN_ATTEMPT == 1`, passes on rerun; deterministic for testing) | Before rerun: no commit named. After rerun (attempt 2 green): `FLAKY` supported (outcome `resolved_on_rerun`). | Same | Before rerun: `UNATTRIBUTED`, `INTRODUCED_IN_RANGE` (no SHA), `FLAKY` possible | Name any commit |
| B-05 | Dependency drift: `foo` 1.9.3 → 2.0.0 published between C0 and C1 runs (controlled index) | `DEPENDENCY_CHANGE` foo 1.9.3→2.0.0 | `PRE_EXISTING` (with dependency note) | C2: `DEPENDENCY_CHANGE` | Name C1 or C2 as cause |
| B-06 | Resolution conflict from a C1 bump | `CHANGE_IN_RANGE` → C1 (L2) | `PRE_EXISTING` | — | Name C2 |
| B-07 | Missing secret `DB_URL` needed by a C1 code path | `CONFIGURATION` (`DB_URL`) | `PRE_EXISTING` | C1: `CHANGE_IN_RANGE` → C1 **only if** configuration is also mentioned; C2: `CONFIGURATION` | Name C2 |
| B-08 | Service container broken by a C1 workflow env rename | `CHANGE_IN_RANGE` → C1 (L3) or `CONFIGURATION` | `PRE_EXISTING` | — | Name C2 |
| B-09 | External HTTP timeout | `FLAKY` (possible, R-FLAKY-03) | Same | `UNATTRIBUTED` | Name any commit |
| B-10 | ruff F401 + mypy | `CHANGE_IN_RANGE` → C1 | `PRE_EXISTING` | — | Name C2 |
| B-11 | Two independent: (a) py3.12 leg fails on `datetime.utcnow` DeprecationWarning (**amended:** pytest `-W error::DeprecationWarning` so it's deterministic); (b) lint job failure. Both in C1. | `MULTIPLE`: 2 × `CHANGE_IN_RANGE` → C1 | `PRE_EXISTING` (both) | — | Report one cause only; name C2 |
| B-12 | Cascade: deleted file → tsc error + 40 jest errors | `CHANGE_IN_RANGE` → C1 (L4); exactly 1 primary | `PRE_EXISTING` | — | Report >1 primary |
| B-13 | Hang → job timeout, truncated log | `INTRODUCED_IN_RANGE` (range C1) or `UNATTRIBUTED` | `PRE_EXISTING` or `UNATTRIBUTED` | `CHANGE_IN_RANGE` → C1 only with band `possible` | `FLAKY`; name C2 |
| B-14 | OOM, exit 137, from a C1 fixture | `UNATTRIBUTED` or `INTRODUCED_IN_RANGE` (possible) | `PRE_EXISTING` or `UNATTRIBUTED` | — | `ENVIRONMENT_CHANGE` (runner unchanged); name C2 |
| B-15 | Recurrence of B-04 one week later | `FLAKY` (possible via R-FLAKY-02 history; supported after rerun) | Same | — | Name any commit |
| B-16 | **Redefined** (we don't generate fixes): outcome tracking after B-05. C3 adapts one call site only, C4 pins `foo<2`. | Analysis of C3 run: outcome on the B-05 analysis = `different_failure` | C4 run: outcome `resolved` | — | Claim "fix verified" |

**Amendment log:**

| Case | Change from R-04 | Why |
|---|---|---|
| B-04 / B-15 | Attempt-based failure replaces random failure | Deterministic scoring |
| B-11 | `-W error` | Python 3.12 warns rather than errors by default |
| B-16 | Becomes outcome tracking | R-04's version assumed the tool proposes a fix, which is out of scope (DR-30) |

### 2.1 `truth.yaml` schema

```yaml
case: B-05
description: "foo 2.0 removes bar(); repo unpinned"
runs:
  C1:
    expected_category: DEPENDENCY_CHANGE
    acceptable_categories: [DEPENDENCY_CHANGE]
    expected_subject: {package: foo, from: "1.9.3", to: "2.0.0"}
    acceptable_suspects: []          # no commit may be named
    expected_primary: {parser: py_traceback, error_class: import_error, contains: "has no attribute 'bar'"}
    max_band_if_wrong: possible
  C2:
    expected_category: PRE_EXISTING
    acceptable_categories: [PRE_EXISTING, DEPENDENCY_CHANGE]
    acceptable_suspects: []
```

### 2.2 Fixture repositories

- **Templates:** `bench/cases/B-xx/template/` contains a minimal app:
  - `py/`: FastAPI-free pure-Python package, pytest, ruff, mypy, uv;
  - `ts/`: Node 20 + TypeScript + vitest/jest + eslint, npm with a lockfile.
- **Workflows:** `bench/cases/B-xx/workflow.yml`.
- **Generator:** `bench/scripts/make_case.py B-05` does the following:
  1. creates `tracewise-bench/b05-<date>`;
  2. pushes C0, then waits for green;
  3. applies C1, then waits;
  4. applies C2, then waits;
  5. records run IDs in `bench/results/<date>/runs.json`.
- **B-05:** uses a private package index: a GitHub Pages "simple" index under the test org, or a `uv` find-links directory in a separate repo. Publishing `foo 2.0.0` between steps simulates an upstream release.
- **Recorded fixtures:** `tracewise lab record` saves every GitHub response for each case into `tests/fixtures/github/B-xx/`. Unit and integration tests then run **offline**.

## 3. Golden log fixtures and real data

| Set | Source | Size | Use |
|---|---|---|---|
| Parser goldens | Redacted logs from Phase 0 (public repos) plus benchmark runs | ≥60 logs, all parser families, incl. 1 Windows and 1 macOS | T3.09 unit tests (expected JSON written by hand) |
| Real labeled dev set | 100 of the 200 labeled runs (T0.03) | 100 | Tuning rules and parsers |
| Real labeled held-out set | The other 100 | 100 | G-INT real metrics (T6.12). **Never used for tuning.** |
| Partner data (pilot) | Partner runs with 👍/👎 plus our review | Growing | Post-pilot calibration (≥200 before any numeric confidence) |

**Licensing and privacy:** logs are from public repos, stored redacted. Fixtures include the repo and run URL for provenance. A repo owner can ask for removal.

## 4. Test layers

| Layer | Scope | Tooling | Runs in |
|---|---|---|---|
| Unit: parsers | Goldens; negatives (e.g. "FAILED" printed by `echo`) | pytest parametrized | CI |
| Unit: normalizer, redactor, fingerprint | Idempotence, stability, secret corpus | pytest + hypothesis | CI |
| Unit: rules | Every positive and negative example in Plan §7.5–7.8 (one test per row) | Table-driven | CI |
| Property: verdict invariants | INV-1…INV-4. Example: generate random candidate sets and assert that no SHA is named without a link candidate. | hypothesis | CI |
| Contract | Pydantic models; LLM schema v1 JSON-Schema validity | pytest, jsonschema | CI |
| Integration: DB | Migrations up/down; constraints; queue claim, lease, reaper, backoff, dead letter; idempotent handler re-run | Postgres 16 service, PgBouncer service | CI |
| Integration: webhook API | Signature (valid, invalid, tampered, rotated secret); dedupe; event filter; 413; 503 on DB down; p99 latency smoke | httpx `AsyncClient` | CI |
| Integration: GitHub client | 302 log flow, pagination, rate-limit and secondary-limit responses, 401 refresh, byte cap | respx | CI |
| Integration: handlers | `analyze_run`, `record_outcome`, `installation_event`, `purge`, `retention` on `FixtureRunSource` | pytest | CI |
| Tenant isolation | §5 S4 suite | pytest + RLS (after T6.01) | CI |
| Worker resilience | Kill during a job → reclaimed; crash after Check Run create → no duplicate | pytest with fault injection | CI |
| Benchmark (offline replay) | B-01…B-16 recorded fixtures → expected verdicts | `make bench-offline` | CI (required) |
| Benchmark (live) | Same cases live against `tracewise-dev` / `tracewise-staging` | `make bench-live` | Manual, before each release |
| Real held-out eval | 100 labeled runs | `make eval-real` | Before the pilot and before each rules release |
| LLM eval (4B) | Dev/test split; recorded responses for CI replay | `make eval-llm` | Before enabling or changing the model |
| E2E smoke | Push to the smoke repo → Check Run appears ≤3 min | `tests/e2e` (opt-in) | After each staging deploy |
| Deployment smoke | `/healthz`, `/readyz`, migration head, worker heartbeat, synthetic signed webhook → `202` (with an unknown installation it is ignored safely) | `scripts/smoke.sh` | After each deploy |

## 5. Security tests (map to Plan §9)

| ID | Test | Pass criterion |
|---|---|---|
| S1 (T1) | Fuzz all parsers with 10k adversarial lines plus a ReDoS corpus; a 50 MB synthetic log | No exception escapes; ≤2 s per parser per 50 MB; no catastrophic backtracking |
| S2 (T2) | Injection fixtures in log, commit message and file excerpts (pilot LLM) | Published output unchanged vs deterministic, or LLM output discarded; no unknown SHA, path or mention published |
| S3 (T3) | 50-secret corpus embedded in fake logs | Zero occurrences in DB, Check Run bodies, captured LLM payloads, stdout logs or Sentry events |
| S4 (T4) | Two tenants. Queries under A for B's rows; missing context; pooled connection reused after tenant A's commit | 0 rows / exception / exception respectively |
| S5 (T5) | Bad, missing or tampered signature; replay | 401 / 401 / 401; replay → `duplicate` |
| S6 (T6) | Token request body scoped; log scan for `ghs_`, `ghp_`, `-----BEGIN` | Present / absent |
| S7 (T7) | Renderer with HTML, JS links, `@org/team`, a huge excerpt | Sanitized; mentions neutralized; capped |
| S8 (T8) | Registry fixture with malicious description and long fields | Never decisive; truncated; escaped |
| S9 (T9) | Publisher asked to post on a SHA ≠ the job's `head_sha` | Refused |
| S10 (T10) | 200 MB log; 500 webhooks/min burst across 3 tenants | Completed within caps; no tenant starved (each gets ≥1 job/min) |
| S11 (T11) | Time-travel retention; purge | Policy honored; zero tenant rows after purge; tombstone exists |
| S12 (T12) | Opt-out installation; captured LLM request content | Zero LLM calls; payload holds only catalog excerpts |
| S13 (T13) | `pip-audit` | No high-severity CVEs |

## 6. Quality gates

### G-INT: internal MVP complete (after T5.04 and T6.12)

| Metric (definition in R-04 §3) | Synthetic benchmark (32 scored runs: 16 cases × C1/C2) | Real held-out (100 runs) |
|---|---|---|
| **False-blame rate**: a commit is named outside `acceptable_suspects` | **≤ 2%** (target 0) | **≤ 5%** (report 95% CI) |
| Attribution accuracy: category in `acceptable_categories` **and** subject matches | ≥ 80% | ≥ 70% |
| Coverage: not `UNATTRIBUTED` | report | ≥ 50% |
| Abstention quality on B-13 and B-14: no `supported` blame | 100% | — |
| Evidence-support rate: published claims passing the validator, then a human spot check of 20 | 100% / 20 of 20 | 100% / 20 of 20 |
| Primary-error accuracy (parser) | ≥ 95% on goldens | ≥ 85% |
| Latency p50 / p95, delivery → Check Run | ≤ 60 s / ≤ 180 s | — |
| GitHub requests per analysis, p95 | ≤ 40 | ≤ 40 |
| LLM cost (only if enabled) | mean ≤ $0.05; max ≤ $0.30 | Same |

**If a gate fails:**

- A false-blame failure **blocks** progress. Fix the rules, or restrict the categories (e.g. disable `CHANGE_IN_RANGE` and ship only `PRE_EXISTING` / `DEPENDENCY` / `FLAKY` / `UNATTRIBUTED`).
- An accuracy or coverage shortfall → NARROW scope (e.g. Python only) and record it in OPEN-QUESTIONS.

### LLM gate (4B)

On the held-out set, compared with deterministic only:

- false blame Δ ≤ 0;
- **and** (correct resolution of ≥30% of `MULTIPLE` cases **or** partner-rated clarity improves);
- **and** mean cost ≤ $0.05.

Otherwise the LLM stays off.

## 7. Release criteria

### Staging release (each deploy)

1. CI green, including offline benchmark replay.
2. Migrations are expand-only (reviewed).
3. Deploy smoke passes.
4. E2E smoke passes on `tracewise-staging`.
5. No new Sentry error types after 1 h.

### Production release (first pilot and thereafter)

1. **G-PILOT:**
   - S1–S13 green;
   - RLS suite green;
   - deletion runbook executed on staging;
   - 14-day soak with zero duplicate Check Runs, zero unhandled job failures and zero cross-tenant failures;
   - privacy notice live;
   - runbooks written.
2. G-INT passed on its latest run (synthetic and real).
3. The live benchmark (`make bench-live`) on staging matches offline results (no regressions).
4. Rollback drill performed at least once (`fly deploy --image <prev>`).
5. Partner written terms in place (G-PAY) before installing on their org.
6. Any later change to rules, parsers or the LLM must re-pass the offline benchmark and real held-out gates before production.

## 8. Reporting template (`bench/results/<date>/REPORT.md`)

- Commit SHA of tracewise, engine version, model (if any).
- Per case and run: expected, actual, pass/fail, band, latency, API calls.
- Aggregates with CIs.
- Failures with root cause and fix task IDs.
- **Statement of what was not run.**
