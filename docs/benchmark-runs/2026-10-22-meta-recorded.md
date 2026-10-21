# META cases from recorded public metadata (2026-10-22; Track D, separate from the synthetic benchmark)

**Command:** `uv run python -m tracewise.bench meta --recorded research/final-evidence-review/evidence/public-ci`
(exit 0). Read in place; nothing was copied, written or fetched. No network, no credentials.

**Evidence:** the anonymous, read-only fetch of 2026-10-17 (`research/final-evidence-review/evidence/FETCH-LOG.tsv`).
Job lists came from `/runs/{id}/jobs` (latest attempt); the runner checked that every job is attempt 1.

| Case | Status | Label derived from metadata | Documents |
|---|---|---|---|
| P-01 | pass | Development Versions / `… tox run` already failed at run 34252544596 (the first red of the streak, found by the lane logic) | Tests-on-main run list (40 runs), jobs of 37632626982 and 34252544596 |
| P-02 | pass | Job `typing` first fails at 37633292268 (it passed in the previous lane run 37632626982); the next lane run 37633458715 is green | Run list, jobs of 37633292268 and 37632626982 |
| P-03 | pass | "No implicated file was identified, so the relevance of this push is unknown." No causal wording | Commit d73fa1cd |

**Limits.** These are 3 cases. The case logic (`bench/meta.py`) was written with the BENCHMARK §3.2 labels known, so
this is a consistency check of the lane foundation on real metadata, **not held-out evidence** and not a basis for
surfacing lane history in reports (ADR-13; owner decision in OWNER-DECISION-PACKET §4a). P-02's "fixed by the next
commit" is checked at run level (the next lane run is green). No score from this run is merged with the synthetic
benchmark, and the truth lock is unchanged.
