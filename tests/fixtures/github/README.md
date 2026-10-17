# GitHub API fixtures

| Directory | Kind | Provenance |
|---|---|---|
| `recorded/` | **Recorded, real, anonymous** public responses | Copied unchanged from `research/final-evidence-review/evidence/public-ci/`. Fetched anonymously on 2026-10-17 (see that folder's `FETCH-LOG.tsv`): `GET /repos/pallets/flask/actions/runs/37632626982/jobs?per_page=100` and `GET /repos/pallets/flask/commits/7689f98403/pulls`. No credentials were used. |
| (inline in tests) | **Synthetic** responses | Token, error, rate-limit and redirect responses shaped after the GitHub REST docs. They cannot be recorded without credentials, so they are **not** evidence of live behaviour. LIVE confirmation is Phase 8 (gated on an approved test org). |
