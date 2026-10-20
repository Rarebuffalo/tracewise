# Testing

Tracewise is tested **offline**. Every automated test runs without credentials and without reaching GitHub, a model
provider or any other external host. A passing suite shows what Tracewise does against fakes and recorded
responses; it does **not** show how GitHub or a real model behaves. That is the separate, not yet executed
[LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md).

## Commands

| Command | Scope |
|---|---|
| `make check` | ruff lint and format check, strict mypy (package and `scripts/`), pytest without `slow` and `live`, docs consistency |
| `make test` | pytest `-m "not live and not slow"` |
| `make test-all` | pytest `-m "not live"` (slow included) |
| `make ci` | **Everything CI runs**, locally: lint, typing, docs, the truth lock, and the CI test command below, failing on any skipped test |
| `PYTHONPATH=. uv run pytest -q -p no:cacheprovider -p tests.netguard -m "not live" -rs` | **The CI test command**: all non-live tests under the network guard |
| `uv run python -m tracewise.bench verify` | Benchmark truth set matches `TRUTH.lock` |
| `uv run python -m tracewise.bench run --provider oracle --reps 3 --include-slow --out .bench-results/<name>` | Full offline benchmark with scripted providers |

Focused runs use normal pytest selection, for example `uv run pytest tests/db/test_d10.py -q`.

## Markers

| Marker | Meaning |
|---|---|
| `slow` | Large inputs (200 MB logs, 50 MB fuzzing). Run in CI and `make test-all`. |
| `live` | Needs an approved test organisation. **Never** run by default or in CI; `--strict-markers` is on. |

## Test layout

| Directory | What it covers |
|---|---|
| `tests/unit/` | Extractors, primary ranking, redaction, logging, GitHub client, fuzzing, CI workflow, network guard |
| `tests/db/` | Queue, worker, ingest, lifecycle, D-10 re-checks, RLS, roles, migrations, retention, recovery, backup/restore, end-to-end flows against a fake GitHub |
| `tests/investigate/` | Investigation loop, validator, provider boundary, OpenAI codec (offline), the smoke harness (offline) |
| `tests/context/` | Read-only code context, tools, trigger diff, local `git http-backend` |
| `tests/report/` | Rendering and escaping |
| `tests/bench/` | Benchmark harness and scorer integrity |

**Fakes:** `tests/github_fake.py` and `tests/github_state.py` (GitHub API with fault injection), `tests/git_server.py`
(local git), `tests/pg.py` (disposable PostgreSQL clusters), scripted model providers.

## Offline guarantees

- **Network guard** (`tests/netguard.py`, `-p tests.netguard`): only loopback and Unix sockets are allowed. Any
  other connection is refused and counted, and it fails the session even if the test swallows the error. The run
  prints `NETGUARD external connection attempts: N`.
- **No skipped tests in CI.** The database tests skip themselves when `initdb` is missing, so CI puts the
  PostgreSQL binaries on `PATH` and fails on any skip.
- **Benchmark integrity.** The truth set is frozen by `TRUTH.lock`. Scores are never improved by changing truth,
  expected answers or scoring. A product change motivated by a benchmark case is logged in
  [BENCHMARK.md](BENCHMARK.md) §8 and needs held-out confirmation.
- **Held-out evidence.** Diagnostic changes are developed against development fixtures and checked against
  separate evaluation fixtures (for example `tests/unit/test_installer_grouping_dev.py` and
  `tests/unit/test_installer_eval_phase52.py`).

## Writing tests

- Write the regression test first and see it fail for the defect's reason.
- Use synthetic values for anything secret-shaped, and make tests check that they never appear in output.
- Database tests use the fixtures in `tests/db/conftest.py` (`pool` is the system plane, `tenant_pool` the RLS
  plane, `owner` the owner connection for setup and assertions).
- Never add a test that needs the internet, a real token or a real model. A live check belongs to the `live`
  marker and the staged plan.
