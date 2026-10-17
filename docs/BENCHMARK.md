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

## 6. What results can conclude

| Results | Support | Do not support |
|---|---|---|
| Tracks A–C, E pass on synthetic | The pipeline works on the designed failure types | Real-world accuracy or prevalence |
| Track D (META) | Job/step-level lane logic on real histories | Error-level correctness |
| No track | — | **Superiority over any competitor.** That needs AT-CMP-01 (approval required). |
