# 04 — Failure Benchmark and Evaluation Methodology

Research date: 2026-10-15.

## Status: evaluation plan. **No product was benchmarked by us.**

Why direct testing was not possible:

- `gh` is unauthenticated in this environment, so we could not create an authorized test repository.
- Installing The Plumber, FailBrief or FixSense on a repo requires the account owner's explicit OAuth consent to grant third-party code and log access. That consent was not given.
- The Plumber's free plan covers **public repos only**, so test failures would be publicly visible.

**The only real product output we observed** is The Plumber's own demo (case B-02 below). It was produced by the vendor on its own repo, so it is **not** an independent test.

Every result cell below is `UNTESTED`, except where marked `OBSERVED (vendor demo)`.

---

## 1. Test harness design

Create a fresh repo, `tracewise-bench/<case-id>`, for each case, or one repo with branches and isolated workflows. Hold everything else constant:

- **Stack:** two mini-apps.
  - `py/`: FastAPI, pytest, ruff and mypy, uv/pip.
  - `ts/`: Next.js or Node, vitest/jest, tsc and eslint, npm.
- **Commit pattern per case.** Each case is three commits, so we can measure attribution:
  1. `C0` green baseline.
  2. `C1` injects the fault, or is an unrelated commit when the cause is external.
  3. `C2` is an **unrelated** follow-up commit (README or docs).

  Run CI on **C1 and C2 separately**. A tool should blame C1 on C1's run, and on C2's run it should say the failure **pre-dates** C2.
- **Products under test:** The Plumber, FailBrief, FixSense (only where JUnit reports are configured), GitHub "Explain error" (manual), "Fix with Copilot" (manual, Pro or above), our prototype.
- **Recording:** for each run capture the webhook time, report time, full report text, permissions in use, and any PR or commit created.

## 2. Benchmark cases

| ID | Category | Ground-truth cause (injected) | Key log evidence expected | Source change | Correct remediation | Ambiguity |
|---|---|---|---|---|---|---|
| B-01 | Build | TS: `tsc` error from a renamed export | `error TS2305: Module has no exported member 'X'` | C1 renames the export in `lib.ts` | Update the import | Low |
| B-02 | Unit test | Python: `total = subtotal * TAX_RATE` (the coffee_shop case) | `assert 0.21 == 2.71` ×4 | Introduced in an earlier commit; the run is on a README-only commit | `subtotal * (1 + TAX_RATE)`, **plus** "failure pre-dates this push" | Low |
| B-03 | Unit test | TS jest snapshot mismatch after an intended UI change | `› 1 snapshot failed` | C1 changes a component | Update the snapshot (test defect, not code) | Medium: is it a code bug or the test? |
| B-04 | Flaky | pytest test depending on dict ordering plus `random` without a seed, ~30% failure | Intermittent assertion | None (C2 unrelated) | Seed or sort; mark flaky; **rerun first** | High (single run) |
| B-05 | Dependency | Unpinned transitive dependency: install `foo>=1` where `foo 2.0` (a local index or fake package we publish to a private index) removes an API | `AttributeError: module 'foo' has no attribute 'bar'` | **No repo code change** | Pin `foo<2` or adapt to 2.0; **blame the upstream release, not C1/C2** | Medium |
| B-06 | Dependency resolution | Conflicting pins | `ResolutionImpossible` / npm `ERESOLVE` | C1 bumps one dependency | Align versions | Low |
| B-07 | Env / config | Workflow reads `secrets.DB_URL`, which is unset in a fork or env | `KeyError: 'DB_URL'` / empty env var | C1 adds a code path needing it | Configure the secret; not a code bug | Medium |
| B-08 | Container | `services: postgres` health check fails due to a wrong `POSTGRES_PASSWORD` env name | `connection refused` after retries | C1 edits the workflow YAML | Fix the YAML env var | Medium |
| B-09 | Network / external | Test calls `https://httpbin.org/delay/30` with a 5 s timeout | `ReadTimeout` | None | Mock the external call or rerun; **infra/external, not a regression** | High |
| B-10 | Lint / type | ruff F401 plus a mypy incompatible type | `F401 'os' imported but unused`; `error: Incompatible types` | C1 | Remove the import; fix the type | Low |
| B-11 | Multiple independent | Matrix (py3.11, py3.12): 3.12-only `datetime.utcnow` deprecation-as-error, **and** an unrelated lint failure in a separate job | Two different primary errors | C1 touches both | Report **two** independent causes, ranked | Medium |
| B-12 | Cascading | Build fails → 40 downstream "module not found" test errors | First error buried under noise | C1 deletes a file | Identify the first causal error, not the 40 cascades | Medium |
| B-13 | Inaccessible logs | Job cancelled by timeout (`timeout-minutes: 1`) with a hanging test; truncated log | `The job running on runner … has exceeded the maximum execution time` | C1 adds `while True` | Say evidence is incomplete; suggest the likely hang location | High |
| B-14 | Insufficient evidence | Process exits 137 (OOM) with no stack | `exit code 137` | C1 adds a large fixture | **Abstain or low confidence**, with a diagnostic plan | High |
| B-15 | Recurrence | Re-introduce B-04 a week later | Same fingerprint | — | "Seen before N times; flaky" | Medium |
| B-16 | Wrong-fix loop | Apply the tool's suggested fix for B-05 that only adapts one call site | Still failing, different line | — | Tool should detect "still failing, different failure" | Medium |

### 2.1 Results table

| ID | Product | Diagnosis | Remediation | Correct? | Evidence supported? | Uncertainty appropriate? | Fix verified? | Latency |
|---|---|---|---|---|---|---|---|---|
| B-02 | The Plumber | "calculate_total returns only tax", line 41 | `subtotal * (1 + TAX_RATE)` | **Root cause: yes. Attribution: no** (did not note the README-only trigger or the introducing commit) | Yes (assert values, code line) | "High". Justified here, but no basis stated | No (instruction only) | ≈6 m 14 s after run completion |
| B-02 | All others | UNTESTED | | | | | | |
| B-01, B-03 … B-16 | All products | UNTESTED | | | | | | |

> The B-02 row is labelled **OBSERVED (vendor demo)**. The case was chosen and run by the vendor, so it is not a fair sample.

## 3. Metrics

| Metric | Definition | How measured |
|---|---|---|
| **Root-cause accuracy (RCA@1)** | Primary cause matches ground truth: correct category **and** correct location or component | Blind grading against a rubric (§4) |
| **Attribution accuracy** | Correctly names the introducing commit, or "external: upstream / infra / flaky", or "pre-dates this push" | Ground-truth commit graph |
| **Evidence support rate** | % of factual claims that cite log lines or diff hunks that actually exist and support the claim | Automated locator check plus human spot check |
| **False attribution rate** | % of runs where the tool blames the triggering commit (or a specific code change) when the true cause is external, flaky or pre-existing | Cases B-02, B-04, B-05, B-09, B-15 |
| **Calibration / ECE** | Expected calibration error between stated confidence and empirical accuracy | Needs ≥100 graded runs; report reliability bins |
| **Abstention quality** | Precision of "I'm not sure" (it should abstain mainly on B-13 and B-14) and its coverage | Abstain rate on high-ambiguity vs low-ambiguity cases |
| **Actionability** | 0–3 rubric: 0 = generic, 1 = points to an area, 2 = specific step, 3 = applyable patch or command | Two independent graders |
| **Verification success rate** | % of suggested fixes that make the next real CI run green **without** deleting or skipping tests | Apply the fix, rerun CI, diff-check for test removal |
| **Unnecessary remediation rate** | % of runs proposing code changes when the correct action is rerun, pin or configure (B-04, B-07, B-09) | Grading |
| **End-to-end latency** | p50 / p95 from `workflow_run.completed` to report posted | Timestamps |
| **Cost per analysis** | LLM tokens × price plus compute; our own system only | Usage logs |
| **Noise** | Comments posted per failing run; duplicates on re-run | Count |

## 4. Preventing "plausible but wrong" from counting as success

1. **Ground truth is fixed before running.** Each case has a written `truth.yaml` (category, file:line, introducing SHA, acceptable remediations) committed before any tool runs.
2. **Blind grading.** Graders see the report with the product name removed and grade against `truth.yaml`. Two graders resolve disagreements.
3. **Category and location must both match.** A fluent explanation in the right file but the wrong mechanism (for example "test is wrong" when the code is wrong) scores 0.
4. **Evidence must exist.** A claim citing a log line that doesn't contain the stated text, or a function that doesn't exist, is a hallucination. The whole diagnosis scores 0, regardless of the final answer.
5. **Attribution is scored separately.** Blaming C2 (the unrelated docs commit) is a false attribution even if the code diagnosis is right.
6. **Verification is execution-based.** A fix counts as verified only if real CI goes green **and** the diff doesn't delete, skip (`@pytest.mark.skip`, `.only`, `xit`) or weaken assertions. A test-weakening check runs automatically.
7. **Penalize false confidence.** Score = correctness − λ·confidence·wrongness. A confident wrong answer costs more than an abstention.
8. **Repeat runs.** Each case is run 3× per product to measure nondeterminism. Report mean and variance.
9. **Held-out set.** For our own system, tune rules and prompts on B-01 to B-10, then report on B-11 to B-16 plus 20 **real** failures mined from public OSS repos (`gh run list --status failure`) that are labelled by hand **before** looking at our output.

## 5. Execution prerequisites (what the user must authorize)

- [ ] `gh auth login` with a dedicated test org (e.g. `tracewise-bench`).
- [ ] Explicit approval to install each third-party GitHub App on that org only, with the permissions listed in `03`.
- [ ] Acceptance that test repos are **public** (The Plumber free plan) or a paid or trial plan (FailBrief Starter $9, FixSense 30-day Pro trial).
- [ ] A Copilot Pro subscription for "Fix with Copilot".
- [ ] A private package index (or a local `--index-url` stub) for B-05 to avoid publishing to PyPI or npm.

Estimated effort: about 1.5 engineer-days to build the 16 cases, plus about 0.5 day per product to run and grade.
