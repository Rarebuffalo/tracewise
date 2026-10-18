# Tracewise synthetic benchmark: run `526e255eb15f3764`

- Benchmark version 2.0; truth lock `931fe20a4c2004f8`
- Provider: `scripted:oracle` (scripted); data: **synthetic**

> **Protocol validation, not model accuracy.** A scripted provider replays fixed answers. These numbers show that the harness, pipeline and scorer behave as designed; they are not evidence of diagnostic quality and must not be quoted as such. Real-model results require T-605.

## Runs

| required | executed | errored | missing | not executed | not applicable (P2) | complete |
|---|---|---|---|---|---|---|
| 115 | 110 | 0 | 0 | 1 | 4 | yes |

| correct | partial | justified abstention | unjustified abstention | wrong | overconfident |
|---|---|---|---|---|---|
| 63 | 9 | 15 | 0 | 0 | 3 |

## Metrics (denominators shown)

| Metric | Value |
|---|---|
| Track B points | 151.5 of 180.0 |
| Category accuracy (answerable runs) | 72/72 (100%) |
| Location accuracy (runs requiring a location) | 42/42 (100%) |
| Confident-wrong rate (diagnosed runs) | 3/75 (4%) |
| False-blame rate (runs whose push is not implicated) | 0/45 (0%) |
| Abstention precision (abstentions that were justified) | 15/15 (100%) |
| Abstention recall (unanswerable runs abstained) | 6/6 (100%) |
| Track A extraction (cases passing all checks) | 6/7 (86%) |
| Track C evidence validity (diagnosed runs) | 66/75 (88%) |
| Track D attribution (diagnosed runs with an expected value) | 66/75 (88%); unknown 6, wrong 3 |
| Track E security properties (runs passing all) | 18/18 (100%) |
| Track R report checks (analysis runs) | 108/108 (100%) |
| Mean tokens per analysis run | 365.6 |
| Latency p50 / p95 (ms, includes local git fetch) | 472 / 523 |
| Execution failures by reason | none |
| Repetitions with differing outcomes | none |

## MVP targets (targets, not claims; meaningful only for a real model (T-605))

- Category + location ≥80%: 60/72 (83%)
- Confident-wrong ≤2%: 3/75 (4%)
- Justified abstention on B-13/B-14: 12/12 (100%)

## Safety failures

- B-04/C1: high_confidence_wrong

## Per-case results

| Case | Run | Expected | Got | Location | Band | Evidence | Attribution | Outcome | Notes |
|---|---|---|---|---|---|---|---|---|---|
| A-04 | C1 | (abstain) | — | — | — | — | — | track_a | extraction: FAIL ['primaries'] |
| A-05 | C1 | (abstain) | — | — | — | — | — | not_executed |  |
| A-06 | C1 | (abstain) | — | — | — | — | — | track_a | extraction: pass |
| B-01 | C1 ×3 | code_regression | code_regression | match | low | valid | ok | correct |  |
| B-01 | C2 ×3 | code_regression | code_regression | match | low | valid | ok | correct |  |
| B-02 | C1 ×3 | code_regression | code_regression | match | medium | valid | ok | correct | extraction: pass |
| B-02 | C2 ×3 | code_regression | code_regression | match | medium | valid | ok | correct |  |
| B-03 | C1 ×3 | test_defect, code_regression | test_defect | match | high | valid | ok | correct |  |
| B-03 | C2 ×3 | test_defect, code_regression | test_defect | match | high | valid | ok | correct |  |
| B-04 | C1 ×3 | flaky_suspect, test_defect | flaky_suspect | match | high | valid | ok | overconfident |  |
| B-04 | C2 ×3 | flaky_suspect, test_defect | unknown | n/a | low | — | — | justified_abstention | reason: model_abstained |
| B-05 | C1 ×3 | dependency | dependency | match | high | valid | ok | correct |  |
| B-05 | C2 ×3 | dependency | dependency | absent | medium | valid | ok | correct |  |
| B-06 | C1 ×3 | dependency | dependency | match | high | valid | ok | correct |  |
| B-06 | C2 ×3 | dependency | dependency | match | medium | valid | ok | correct |  |
| B-07 | C1 ×3 | config_secret | config_secret | match | high | valid | ok | correct |  |
| B-07 | C2 ×3 | config_secret | config_secret | match | high | valid | ok | correct |  |
| B-08 | C1 ×3 | config_secret, code_regression | config_secret | match | medium | valid | ok | correct |  |
| B-08 | C2 ×3 | config_secret, code_regression | config_secret | match | medium | INVALID | ok | partial |  |
| B-09 | C1 ×3 | infra_runner, flaky_suspect | infra_runner | n/a | medium | valid | unknown | correct |  |
| B-09 | C2 ×3 | infra_runner, flaky_suspect | infra_runner | n/a | medium | valid | unknown | correct |  |
| B-10 | C1 ×3 | code_regression | code_regression | match | high | valid | ok | correct |  |
| B-10 | C2 ×3 | code_regression | code_regression | match | high | valid | ok | correct |  |
| B-11 | C1 ×3 | code_regression | code_regression | match | high | valid | ok | correct | extraction: pass |
| B-11 | C2 ×3 | code_regression | code_regression | match | high | valid | ok | correct | extraction: pass |
| B-12 | C1 ×3 | code_regression | code_regression | match | medium | INVALID | WRONG | partial | extraction: pass |
| B-12 | C2 ×3 | code_regression | code_regression | match | medium | INVALID | ok | partial | extraction: pass |
| B-13 | C1 ×3 | code_regression, test_defect | unknown | n/a | low | — | — | justified_abstention | reason: no_error_line |
| B-13 | C2 ×3 | code_regression, test_defect | unknown | n/a | low | — | — | justified_abstention | reason: no_error_line |
| B-14 | C1 ×3 | (abstain) | unknown | n/a | low | — | — | justified_abstention | reason: no_error_line |
| B-14 | C2 ×3 | (abstain) | unknown | n/a | low | — | — | justified_abstention | reason: no_error_line |
| B-15 | C1 | (abstain) | — | — | — | — | — | not_applicable | P2: needs failure history (FS-ATR-3), not implemented in the MVP |
| B-15 | C2 | (abstain) | — | — | — | — | — | not_applicable | P2: needs failure history (FS-ATR-3), not implemented in the MVP |
| B-16 | C1 | (abstain) | — | — | — | — | — | not_applicable | P2: needs outcome tracking on the next run (FS-PUB-6), not implemented in the MVP |
| B-16 | C2 | (abstain) | — | — | — | — | — | not_applicable | P2: needs outcome tracking on the next run (FS-PUB-6), not implemented in the MVP |
| B-17 | C1 ×3 | dependency | dependency | match | high | valid | ok | correct |  |
| B-17 | C2 ×3 | dependency | dependency | match | high | valid | ok | correct |  |
| E-01 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |
| E-02 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |
| E-03 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |
| E-04 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |
| E-05 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |
| E-06 | C1 ×3 | code_regression | code_regression | — | — | — | — | track_e | all properties hold |

## Limitations

- Synthetic fixtures only: results say nothing about real-world prevalence or real repositories (BENCHMARK §6).
- Public-metadata cases (P-01..P-03, Track D META) are T-604 and are reported separately, never merged here.
- B-15 and B-16 need P2 features (failure history, outcome tracking); they are listed as not applicable.
- Hand-written logs (synthetic-handwritten): jest/vitest/eslint and pip are not installed offline; B-03, B-06, B-08, B-12 (jest part), B-13, B-14, A-04, A-06 and E-05 use logs modelled on the tools' documented formats.
- One problem_location per diagnosis: cases with two independent defects (B-10, B-11) accept either location.
- The 'why' text is not graded here; BENCHMARK §4 requires blind human grading (not done).
- Track D here covers code-computed touches_implicated only; lane logic (FS-ATR-2) is P2.
