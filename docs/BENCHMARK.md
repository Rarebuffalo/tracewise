# Benchmark Specification (canonical)

Version 2.0, 2026-10-18. This consolidates, without loss:

- `research/archive/2026-10-15-s1-research/04-failure-benchmark.md` §2 ("doc 04": the original case definitions);
- the amendments in `research/archive/2026-10-15-s1-plan/TEST-AND-RELEASE-PLAN.md` §2;
- `research/final-evidence-review/BENCHMARK-AND-GROUND-TRUTH-REVIEW.md` §3–4;
- B-17 from the S3 acceptance tests.

**Rules (decided 2026-10-17/18):**

- Ground truth comes **only** from (1) synthetic cases we construct, with `truth.yaml` committed before any run, and (2) **anonymous** public GitHub metadata.
- **No** authenticated log downloads, personal or CLI credentials, competitor installs, or quarantined S2 R-case content.
- Public metadata supports **job/step-level** labels only: never error-line or root-cause truth.
- Synthetic and metadata results are **never averaged**.
- **No results exist yet.**

## 1. Synthetic case pattern

Each synthetic repo uses three commits:

| Commit | Content |
|---|---|
| C0 | Green baseline |
| C1 | Fault injection, or an unrelated commit for external causes |
| C2 | Unrelated `README.md` change (B-17: a docstring edit) |

A run is analysed on C1 and on C2. The offline harness produces GitHub-like job logs from real local tool runs (pytest, ruff, mypy, tsc, jest/vitest, eslint) plus a jobs-API fixture. Runner-specific cases (B-08, B-13, B-14) use hand-authored log fixtures modelled on GitHub's documented format. They are labelled `synthetic-handwritten`.

## 2. Case catalogue (B-01…B-17)

`touches` = the expected `attribution.touches_implicated` (FS-ATR-1). Categories follow SPEC FS-DX-6.

| ID | Ground truth (doc 04 + amendments) | Expected on the C1 run (MVP) | Expected on the C2 run (MVP) | Must NOT | Difficulty | Source type |
|---|---|---|---|---|---|---|
| B-01 | TS `tsc` TS2305 from a renamed export in `lib.ts` (C1) | `code_regression`; location = the import site or `lib.ts`; names the export; `touches=true` | Same category; `touches=false`, "likely pre-dates this push" | Blame C2 | Low | synthetic |
| B-02 | Python `total = subtotal * TAX_RATE` in `coffee_shop/pricing.py:41` (C1); `assert 0.21 == 2.71` ×4 | `code_regression`; `pricing.py:41`; fix `subtotal * (1 + TAX_RATE)`; siblings = 3; `touches=true` | `touches=false`; "changed only README.md; not implicated; likely pre-dates this push" | Say C2 caused it | Low | synthetic (re-implementation of the public demo defect) |
| B-03 | jest snapshot mismatch after an intended UI change (C1) | `test_defect` **or** `code_regression` + next step "update snapshot if intended" (ambiguous: both accepted); `touches=true` | `touches=false` | Blame C2 | Medium (ambiguous) | synthetic |
| B-04 | Flaky test. **Amended:** fails when `GITHUB_RUN_ATTEMPT == 1`, passes on rerun (deterministic). Doc 04 version: dict ordering + unseeded `random`, ~30% failure. | Attempt 1 only: ≤`medium` confidence, no `high`. With attempt-2 metadata: `flaky_suspect` (P2). | Same | `high`-confidence code blame | High | synthetic |
| B-05 | Upstream `foo` 1.9.3 → 2.0.0 removes `bar` (controlled local index); `AttributeError: module 'foo' has no attribute 'bar'`; no repo change | `dependency`; no code fix; `next_steps` include pinning `foo<2`; `touches=false` | Same; `touches=false` | Name C1 or C2 as the cause | Medium | synthetic |
| B-06 | Conflicting pins after a C1 dependency bump (`ResolutionImpossible` / `ERESOLVE`) | `dependency`; next step "align versions"; `touches=true` (manifest) | `touches=false` | Blame C2 | Low | synthetic |
| B-07 | Missing secret `DB_URL` used by a new C1 code path (`KeyError: 'DB_URL'`) | `config_secret` naming `DB_URL`; no code fix | `touches=false` | Blame C2 | Medium | synthetic |
| B-08 | `services: postgres` health check fails after a C1 workflow env rename (`connection refused`) | `config_secret` **or** `code_regression` located in `.github/workflows/*.yml`; `touches=true` | `touches=false` | Blame C2 | Medium | synthetic-handwritten |
| B-09 | External HTTP timeout (`ReadTimeout`), no code cause | `infra_runner` or `flaky_suspect`; first step "re-run"; no code fix | Same | Any commit blame | High | synthetic |
| B-10 | ruff F401 (`'os' imported but unused`) + mypy incompatible type (C1) | `code_regression`; both locations | `touches=false` | Blame C2 | Low | synthetic |
| B-11 | Two independent failures: py3.12 `datetime.utcnow` DeprecationWarning as error (**amended:** `-W error::DeprecationWarning`) + a lint job failure (C1) | Two primaries, each `code_regression` | `touches=false` | Report only one cause | Medium | synthetic |
| B-12 | Deleted file → `tsc` error + 40 jest "Cannot find module" cascades (C1) | Exactly 1 primary (tsc); `code_regression`; `touches=true` | `touches=false` | >1 primary | Medium | synthetic |
| B-13 | Hanging test → job timeout ("exceeded the maximum execution time"), truncated log (C1 adds `while True`) | `inconclusive`, **or** a hang location at `low` | `touches=false` | `high` confidence; `flaky_suspect` | High | synthetic-handwritten |
| B-14 | OOM, exit 137, no stack (C1 adds a large fixture) | `inconclusive`; no fix; diagnostic next steps | Same | Any causal claim at ≥`medium` | High | synthetic-handwritten |
| B-15 | Recurrence of B-04 one week later (same fingerprint) | P2 (FS-ATR-3): `flaky_suspect` from history | Same | Commit blame | Medium | synthetic |
| B-16 | **Amended** (no fix generation): after B-05, C3 adapts one call site only, C4 pins `foo<2` | P2 (FS-PUB-6): C3 run → outcome `different_failure`; C4 run → `resolved` | — | Claim "fix verified" | Medium | synthetic |
| B-17 | Upstream `foo 2.0` breaks a function (C1, index change only); C2 edits a **docstring in the module that appears in the traceback** | `dependency`; `touches=false` | `touches=true` reported **as evidence only**; statement must not say C2 caused the failure | "Caused by" C2 | Hard (trap) | synthetic |

### 2.1 Consolidation check against doc 04

| Doc 04 case | Present above | Ground truth preserved | Change |
|---|---|---|---|
| B-01 | ✓ | ✓ | Expectations re-expressed in the parity categories |
| B-02 | ✓ | ✓ | Same |
| B-03 | ✓ | ✓ | Same |
| B-04 | ✓ | ✓ (both versions recorded) | Attempt-based determinism (TEST-AND-RELEASE amendment) |
| B-05 | ✓ | ✓ | — |
| B-06 | ✓ | ✓ | — |
| B-07 | ✓ | ✓ | — |
| B-08 | ✓ | ✓ | Marked `synthetic-handwritten` |
| B-09 | ✓ | ✓ | — |
| B-10 | ✓ | ✓ | — |
| B-11 | ✓ | ✓ | `-W error` (amendment) |
| B-12 | ✓ | ✓ | — |
| B-13 | ✓ | ✓ | Marked `synthetic-handwritten` |
| B-14 | ✓ | ✓ | Marked `synthetic-handwritten` |
| B-15 | ✓ | ✓ | P2 |
| B-16 | ✓ | ✓ | Redefined as outcome tracking (amendment; no fix generation in scope) |

This check is also automated by `scripts/check_docs.py` (case IDs and key ground-truth phrases).

## 3. Tracks

| Track | Purpose | Cases | Env |
|---|---|---|---|
| **A: extraction** | Failed step, first error, siblings, cascades, truncation, control sequences | A-01 (B-02 log), A-02 (B-12), A-03 (B-11), A-04 misleading tail, A-05 200 MB log, A-06 ANSI/OSC/CR | UNIT/BENCH |
| **B: diagnosis** | Category, location, fix, abstention | B-01…B-14, B-17 | BENCH |
| **C: evidence validity** | Log refs resolve, location in examined range, snippet identical, paths exist, URLs code-built, `files_examined` equals the tool log | All B cases | BENCH |
| **D: attribution** | `touches_implicated` (MVP); lane logic (P2) | C1/C2 runs of B cases; **META P-01…P-03** | BENCH + META |
| **E: security** | E-01 injection in test output; E-02 injection in source + symlink to `/etc/passwd`; E-03 fake `##[error]`/`##[group]`; E-04 fake `Successfully installed`; E-05 secrets in the log; E-06 hostile model output | UNIT/BENCH |
| **F: platform** | G-PLAT-1…7 | LIVE (**gated**) |

### 3.1 Track A, additional cases

| ID | Input | Expected |
|---|---|---|
| A-04 | Real install failure mid-log, then a later unrelated "No module named X" | Primary = the earlier install failure |
| A-05 | 200 MB log, error at line 3,000,000 | Error retained; `log_truncated=true` |
| A-06 | ANSI SGR, OSC 8, C1 controls, CR overwrites | Clean extraction |

### 3.2 Track D, public-metadata cases

Anonymous REST, fetched 2026-10-17; artifacts in `research/final-evidence-review/evidence/public-ci/`.

| ID | Lane | Label (job/step level only) | Supports |
|---|---|---|---|
| P-01 | pallets/flask `Tests` on `main`, run 37632626982 | The same job and step ("Development Versions" / `tox run`) already failed at run 34252544596 → pre-existing at job/step level | Lane logic (P2) |
| P-02 | Run 37633292268 → commit d086db856b green | Job "typing" first fails here; fixed by the next commit | Lane logic (P2) |
| P-03 | Run 34252544596; trigger d73fa1cdcb edits `src/flask/app.py` (+2/−2); only "Development Versions" fails | **Cause unknown** (no logs). Expected: no unsupported causal claim about the trigger. | False-blame guard |

**Adding META cases:** each case records endpoint, anonymous access, fetch time, `granularity: job/step`, and rationale. Run IDs from the quarantined S2 index may be used only as pointers (`pointer_from_quarantine: true`), with labels re-derived from anonymous metadata.

## 4. Grading (fixed before any run)

**Per case, Tracks B and D:**

| Outcome | Score |
|---|---|
| Correct category + location (±3) + valid evidence | **+2** |
| Correct category, wrong or missing location | +0.5 |
| Justified abstention where the truth is "unanswerable" (B-14, P-03) | **+2** |
| Abstention on an answerable case | 0 |
| Wrong at `low`/`medium` | −1 |
| **Wrong at `high`** | **−3** |
| **Blaming the trigger for a pre-existing or external failure** | **additional −2** |

**Raw metrics reported per track:**

- category accuracy;
- location accuracy;
- confident-wrong rate;
- false-blame rate;
- abstention precision and recall;
- evidence validity;
- tokens and cost per case;
- p50/p95 latency.

**Protocol:**

- Each case runs 3×.
- `truth.yaml` is hashed and committed before the first run.
- Blind human grading for "why" text.

**Synthetic MVP targets** (targets, not results): category + location ≥80%; confident-wrong ≤2%; justified abstention on B-13 and B-14.

### 4.1 Scoring rules as implemented (`src/tracewise/bench/score.py`, T-603)

The §4 table is applied per run (case × commit × repetition). Rules §4 left implicit are fixed here:

| Rule | Definition |
|---|---|
| Location match | Same path, and the truth line within `[line_start − tolerance, line_end + tolerance]` (default 3) of any accepted alternative |
| Valid evidence | Re-checked against the fixture, not taken from the validator: each primary-error excerpt line exists in that job's log; the snippet equals the file at that commit; every examined range exists; no `unverified_path`, `unverified_line`, `url_removed` or `causal_claim_removed` flag |
| `correct` (+2) | Category in the accepted set, location match (or no location when none is required), valid evidence, confidence within `max_band` |
| `partial` (+0.5) | Category correct, but location mismatch/absent-when-required or evidence invalid |
| `overconfident` | Otherwise correct but above `max_band`; scored as wrong at that band (−1, or −3 at high) |
| Abstention | `answerable: false` or `"either"` → justified (+2); `answerable: true` → unjustified (0) |
| False blame (−2 extra) | Truth says the push is not implicated, and the run says `touches_implicated = true` or makes a causal claim about the push |
| Not scored | `error`, `missing`, `not_executed` (slow case excluded) and `not_applicable` (P2): no points, outside every denominator, always listed, never success. A suite with a missing, errored **or not-executed required** run is `complete: false` (CLI exit 1). A default run that excludes the slow A-05 is therefore incomplete by design; use `--include-slow` for a complete run. |
| Denominators | Category accuracy: answerable runs. Location accuracy: answerable runs whose truth requires a location. Confident-wrong: diagnosed runs. False blame: runs whose truth says not implicated. Abstention precision: all abstentions. Abstention recall: unanswerable runs. Evidence validity (Track C): diagnosed runs. Attribution (Track D): diagnosed runs with an expected value; `unknown` is reported separately and is neither ok nor false blame. |
| Tracks | A: pre-pass facts (A-04…A-06, plus A-01…A-03 from the B-02/B-12/B-11 C1 runs). E: per-case `must_not` security properties. R: report checks on every analysis run (GitHub-only links, no raw HTML, no unescaped mentions, inconclusive reports carry no fix, no causal claim). |
| Overlap | A B-02/B-11/B-12 C1 run counts once in Track B and once in Track A (different questions). E runs are scored only on security properties and report checks. |

## 5. `truth.yaml` schema

```yaml
case: B-02
source_type: synthetic            # synthetic | synthetic-handwritten | meta
runs:
  C1:
    category: [code_regression]   # accepted set
    location: {path: coffee_shop/pricing.py, line: 41, tolerance: 3}
    touches_implicated: true
    siblings_count: 3
    fix_check: "pytest tests/test_pricing.py passes after replacement"
    must_not: [high_confidence_wrong]
  C2:
    category: [code_regression]
    touches_implicated: false
    statement_contains: ["README.md", "likely pre-dates"]
    must_not: [trigger_caused]
```

### 5.1 Schema as implemented (`src/tracewise/bench/model.py`)

Minimal extensions to §5, needed to express the catalogue:

- `location` is a **list** of accepted alternatives (B-01 import site or `lib.ts`; B-03; B-10/B-11 two defects).
- `answerable: true | false | either` makes the abstention policy explicit (B-04, B-13: `either`; B-14: `false`).
- `max_band` caps confidence (B-04 ≤ medium, B-13 ≤ low).
- `evidence` lists facts that must exist in the fixture; the integrity check verifies them.
- `primaries`, `cascades`, `failed_step`, `first_error_contains` and `log_truncated` hold the Track A facts.
- Cases carry `version`; `TRUTH.lock` holds the SHA-256 of every `truth.yaml`, and the harness refuses to run on a mismatch. The lock was committed (d4745aa) before the first harness run.

## 6. What results can conclude

| Results | Support | Do not support |
|---|---|---|
| Tracks A–C, E pass on synthetic | The pipeline works on the designed failure types | Real-world accuracy or prevalence |
| Track D (META) | Job/step-level lane logic on real histories | Error-level correctness |
| No track | — | **Superiority over any competitor.** That needs AT-CMP-01 (approval required). |

## 7. Implementation notes and deviations (T-601…T-603)

| Item | Note |
|---|---|
| Real tool runs | pytest, ruff, mypy and tsc produce the logs at each fixture commit (`python -m tracewise.bench generate`); `generate --check` reproduces every committed log byte for byte. |
| Hand-written logs | jest, vitest, eslint and pip are not installed offline, and installing them needs the network. B-03 (jest), B-06 (pip), B-12's jest job, A-04, A-06 and E-05 (planted secrets) therefore use hand-written logs, as do B-08, B-13 and B-14 as §1 specifies. They are labelled `synthetic-handwritten` or `mixed`. |
| B-02 values | The replica's tests assert `0.21 == 1.21` (and siblings), not the doc-04 literal `0.21 == 2.71`. The defect (line 41 multiplies by `TAX_RATE` only) is identical. |
| Synthetic secrets | E-05's log holds placeholders; the harness substitutes generated values at run time, so no secret-shaped string is committed. |
| One location per diagnosis | Diagnosis v2 has a single `problem_location`; B-10/B-11 accept either defect location. |
| Not graded | The "why" text (blind human grading per §4) and fix application (AT-DX-06) are not implemented. |
| Repetitions | 3 per Track B/E run (§4); 1 for Track A (deterministic, pre-pass only). |

## 8. Protocol-validation findings (scripted providers; NOT model accuracy)

The scripted `oracle` provider replays hand-written reference answers (`reference.yaml`, written before any run). The findings below concern **the product and the truth set**, and are recorded **without changing the product or the truth**, so the benchmark has not been tuned against itself:

| Case | Finding | Owner |
|---|---|---|
| B-04 C1 | A correct `flaky_suspect` answer is rated **high** (the error cites the line, which the push changed), but §2 and AT-DX-11 require ≤ medium without attempt metadata. Reported as a high-confidence-wrong safety failure. | Product (confidence rule D-5 has no cap for `flaky_suspect`) |
| B-12 | A correct explanation must name the deleted `src/util.ts`; validator rule 4 strips paths absent at `head_sha`, so evidence is marked invalid (partial). Attribution says "not implicated" although the push deleted the imported module. | Product (rule 4; implicated paths do not include resolved module targets) |
| A-04 | The two `ERROR:` lines of one pip failure form two primaries (truth: 1). | Product (fingerprint grouping) |
| B-01 | The cross-file answer (`lib.ts`, where the export was renamed) is downgraded to **low** because tsc names `app.ts` (D-5 conflict rule). | Product (D-5 design choice, for review) |
| B-09 | Attribution is `unknown` (no in-repo implicated path) where the truth says "not implicated". Safe, but incomplete. | Product |
| E-01 (adversarial provider) | A provider that reads `README.md` can still cite it after injected text; the fix and causal text are removed, but the location stands (known AT-SEC-08 limit). | Product, needs real-model evaluation |
| B-08 C2 | The reference answer abbreviates `.github/workflows/ci.yml` to `ci.yml`; the validator correctly flags it (partial). | Reference answer (left unchanged) |
| A-05 | Complete run (2026-10-18, `--include-slow`, ≈60 s): `log_truncated=true`, `primaries=0`, `first_error=None`. The truth requires the needle to be the extracted first error, but the canonical A-05 / AT-LOG-04 criterion is retention plus `log_truncated`, which the product meets. No extractor matches a bare `E   AssertionError` line. | Truth over-specified; a v2 correction is proposed for review, not applied |

**Benchmark-driven changes so far:** none to the product, the truth or the reference answers. Fixes were made only to the scorer and report presentation (location-result field, Track A rows without checks, attribution `unknown` vs `wrong`) and to harness robustness. Any product change motivated by §8 must be logged here, and a held-out case set designed before results are quoted.

**Report history:** `docs/benchmark-runs/2026-10-18-oracle-protocol-validation.md` (default run, A-05 excluded) shows `complete: yes`; that predates the completeness fix above and would now read `no`. `docs/benchmark-runs/2026-10-18-oracle-full-including-slow-protocol-validation.md` is the complete run: 115 required, 111 executed, 4 P2 not applicable, 0 errors, 0 missing, 0 not executed. `docs/benchmark-runs/2026-10-18-phase4-rerun-after-t701-t702-t705.md` repeats the complete run after T-701/T-702/T-705 with an identical result.
