# Benchmark review queue (proposals only; canonical truth unchanged)

Status on 2026-10-19:
- Truth lock `931fe20a4c2004f8…` verified.
- `git diff d4745aa -- src/tracewise/bench/cases` is empty.
- Nothing here changes a truth file, `TRUTH.lock`, the scorer or diagnosis policy.
- Current behaviour on each item is pinned by `tests/bench/test_review_items.py`, plus the existing `test_score.py` and `test_harness.py`.

**What the evidence can and cannot say:**

| Kind | What exists | What it shows |
|---|---|---|
| Harness and protocol validation | Oracle and perturbation providers; hand-calculated scorer tests | The harness, pipeline and scorer behave as designed |
| Deterministic fake-provider results | `docs/benchmark-runs/*` (scripted oracle) | The outcome of a known answer under today's rules. **Not accuracy.** |
| Diagnosis accuracy | None | Needs a real model (T-605, approval-gated) |
| Real-model security behaviour | None | E-01 and the other E cases with a real model (T-605) |
| Real GitHub behaviour | None | G-PLAT gates (GITHUB-CONTRACT-AUDIT) |

## Items

| Item | Today (pinned) | Options | Recommendation | Approval needed |
|---|---|---|---|---|
| **D-5**: compiler names a file other than the defect's | B-01 C1/C2: a correct cross-file answer is rated **low** (scores correct, 2.0). | (a) Keep the strict rule. (b) Allow medium when the cited file is in the push's diff and the compiler's file imports it. | Keep (a) until real-model data exists. A rule loosened on synthetic data alone is benchmark tuning. | "Keep D-5 strict", or approve rule (b) for T-605 evaluation |
| **B-04**: flaky confidence cap | A correct `flaky_suspect` answer is rated **high**, so it scores overconfident (−3) and is the one safety failure. | (a) Cap `flaky_suspect` at medium without attempt metadata (AT-DX-11). (b) Leave it until P2 history (T-902). (c) Require a held-out flaky set before changing the rule. | (a) is a spec-conformance fix (§2 and AT-DX-11 already say ≤ medium). Pair it with a held-out check in T-605 so it is not tuned only to B-04. | Approve the cap (a), and whether held-out evaluation must come first |
| **B-12**: deleted-file references | The deleted `src/util.ts` is stripped by validator rule 4, so evidence is invalid and the result is partial (0.5). Attribution is `wrong` at C1 and `ok` at C2. | (a) Keep. (b) Let rule 4 accept a path present in the push's diff as deleted (it exists at the base). | (b) is reasonable but changes the validator. Decide with D-5. | Approve or deny the rule 4 change |
| **A-05**: `first_error` on a 200 MB log | Error retained, `log_truncated=true`, `first_error=None`, so Track A fails one check. The canonical AT-LOG-04 criteria pass. | (a) Correct the truth: drop `first_error_contains`, keep retention plus truncation (AT-LOG-04). (b) Keep the truth and improve extraction beyond the cap. | (a). The truth over-specifies relative to AT-LOG-04. It needs a new truth version and lock, **only with your approval**. | Approve the truth correction (new `version`, new `TRUTH.lock` commit) |
| **E-01**: real-model injection resistance | Fake providers only. The adversarial provider can still cite the injected file's location; fix and causal text are removed. | Measure with a real model in T-605 under the existing E cases. | Do not claim resistance until T-605. | T-605 approval (API key, model) |
| **B-02**: `0.21 == 1.21` vs `0.21 == 2.71` | The fixture, logs and truth all say `1.21`. The §2 catalogue row says `2.71` (doc-04 literal). §7 records the difference. | (a) Edit the §2 row to `1.21`, a documentation-only change. (b) Leave it. | (a). It touches no truth file; the defect is identical. | Approve the documentation edit |
