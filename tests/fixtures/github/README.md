# GitHub API fixtures

| Directory | Kind | Provenance |
|---|---|---|
| `recorded/` | **Recorded, real, anonymous** public responses | Public responses from the `pallets/flask` repository, fetched anonymously on 2026-10-17 and copied unchanged (the original fetch log is kept outside the repository): `GET /repos/pallets/flask/actions/runs/37632626982/jobs?per_page=100` `GET /repos/pallets/flask/commits/7689f98403/pulls` and `GET /repos/pallets/flask/commits/d73fa1cdcb` (META case P-03). No credentials were used. |
| (inline in tests) | **Synthetic** responses | Token, error, rate-limit and redirect responses shaped after the GitHub REST docs. They cannot be recorded without credentials, so they are **not** evidence of live behaviour. LIVE confirmation is Phase 8 (gated on an approved test org). |
