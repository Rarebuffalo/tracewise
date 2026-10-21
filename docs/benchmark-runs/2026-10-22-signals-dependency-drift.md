# P2 signal evaluation: dependency drift (T-903) on the frozen benchmark (2026-10-22)

**Command:** `uv run python -m tracewise.bench signals` (exit 0). Offline; reads the frozen cases, writes nothing; truth
lock unchanged. Pinned by `tests/unit/test_signals_eval.py`. **Not surfaced in reports (ADR-13).**

**Inputs per run:** the trigger diff between the previous and the run's snapshot (the same snapshots the harness
commits) and the run's raw job logs. **Label:** `dependency` in the run's accepted category set. Unlabelled
(unanswerable) runs are excluded. The fixtures contain no install output, so upstream drift can only ever be
`flagged` (uncorroborated) here.

| Split | Runs scored | Dependency runs | TP (corroborated) | FP | FN | TN | Flagged, uncorroborated | Inconclusive | Excluded |
|---|---|---|---|---|---|---|---|---|---|
| Development (B-05, B-06: read while writing T-903) | 4 | 4 | 1 (B-06 C1) | 0 | 0 | 0 | 3 (on dependency runs) | 0 | 0 |
| Unseen (24 other cases; not used to develop the signal) | 30 | 2 | 0 | **0** | **2** (B-17 C1, C2) | 28 | 0 | 0 | 9 unlabelled, 1 skipped (A-05: log generated at run time) |

**What this shows:** on 28 non-dependency runs the signal never claimed or even flagged drift (no false positive).
It detected neither unseen dependency run: B-17's error is `TypeError: parse() got an unexpected keyword argument`,
which names a function, not a package, so nothing can be attributed (a recall limit, recorded in
`tests/unit/test_drift.py`; deliberately **not** tuned on B-17, which would spoil it as unseen evidence).

**What this does not show:** accuracy. Two unseen dependency runs and one corroborated development run are far too
few for a rate. "Unseen" means not used during development; the truths are public in this repository, so this is not
an independent held-out set.

**Lane history (T-901): no valid evaluation exists.** The benchmark has no run histories; META P-01/P-02 pass from
recorded metadata (2026-10-22-meta-recorded.md) but were known while the logic was written.

## Smallest safe procedure to close both gaps (needs your approval; nothing has been fetched)

1. **Freeze the rule first:** commit the selection rule and expected-label rule below before looking at any data.
2. **Lane history:** one anonymous, read-only fetch (AT-SEC-14 client; needs the run-list endpoint added to its
   allowlist) of the 100 most recent `push` runs on the default branch of 3–5 public repositories you approve, plus
   the jobs of each failed run. Label each failed run mechanically from metadata only: "pre-existing" when the same
   job/step failed in the previous red run of an unbroken red streak. Evaluate `lane.py` against those labels.
3. **Dependency drift:** select failed runs from the same fetch whose logs are public and contain install output;
   two reviewers label `dependency` or not **before** running `drift.assess`. Without public logs (they need
   authentication), this part needs the test organisation instead.
4. Report TP/FP/FN/inconclusive per repository, keep the data outside the frozen benchmark, and decide surfacing
   (OWNER-DECISION-PACKET §4a) from that report.
