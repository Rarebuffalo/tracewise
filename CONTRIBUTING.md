# Contributing to Tracewise

Thanks for your interest. Tracewise diagnoses failed GitHub Actions runs and publishes evidence-backed reports. It
handles other people's code, logs and credentials, so the bar for correctness and safety is high. This guide
explains how to work on it without lowering that bar.

## Architectural principles

Keep these in mind for every change:

1. **Evidence before claims.** A diagnosis must be supported by evidence the system examined. When it is not, the
   correct output is "inconclusive", never a guess.
2. **Read-only investigation.** The investigator has exactly four tools: `read_file`, `grep`, `list_dir` and
   `get_diff`. Do not add tools that execute code, write files, apply patches or reach the network.
3. **Untrusted input everywhere.** Logs, repository files, PR text and model output are data. They must never
   become instructions, links, mentions, report markers or SQL.
4. **Fail closed.** Missing configuration, a wrong database role, an unknown response shape or a failed
   authorisation check stops the operation with a classified, value-free error.
5. **Tenant isolation.** Tenant data is read and written on the row-level-security role with the job's
   installation id. Cross-tenant work belongs only to the system plane.
6. **Idempotent side effects.** Every GitHub write can be retried or re-run without duplicating anything.
7. **Offline tests.** Automated tests never need the internet, a real token or a real model.

The specification is [docs/SPEC.md](docs/SPEC.md) and the design is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Setting up

Follow [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): Python ≥ 3.12, uv, and PostgreSQL server binaries on `PATH`.
Then:

```bash
uv sync
```

```bash
make check
```

The database tests start their own disposable PostgreSQL clusters; you do not need a running database to test.

## Before you open a pull request

The quickest way is `make ci`, which runs exactly what CI runs. Equivalently, run each of these and make sure
they all pass:

```bash
make check
```

```bash
PYTHONPATH=. uv run pytest -q -p no:cacheprovider -p tests.netguard -m "not live" -rs
```

```bash
uv run python -m tracewise.bench verify
```

```bash
git diff --check
```

The second command is CI's test command (slow tests included, under the network guard). It must report
`NETGUARD external connection attempts: 0` and no skipped tests.

## Conventions

- **Formatting and lint:** ruff, line length 130 (`uv run ruff format src tests scripts`).
- **Typing:** mypy `strict` for `src/tracewise` and `scripts/`. Do not add `type: ignore` without a reason in the
  comment.
- **Style:** match the surrounding code, including its comment density and naming. Comments explain *why*, and
  cite spec items (`FS-…`, `AT-…`) or decisions (`D-…`) where relevant.
- **Errors and logs:** messages name settings, classes and ids, never values, tokens, URLs or log content. Use
  `tracewise.observe.event` for structured events.
- **Documentation:** update the canonical docs in `docs/` when behaviour changes, and add a `docs/CHANGELOG.md`
  entry for notable changes. `python3 -I scripts/check_docs.py` (part of `make check`) checks links and
  consistency.

## Tests

- **Regression first.** For a bug, write the test that fails for the bug's reason, see it fail, then fix.
- **Placement:** `tests/unit/` for pure logic, `tests/db/` for anything touching PostgreSQL, the queue, the worker
  or publication, `tests/investigate/` for the loop, the validator and providers. See
  [docs/TESTING.md](docs/TESTING.md).
- **Fakes, not services:** use `tests/github_fake.py` / `tests/github_state.py` (with fault injection),
  `tests/git_server.py` and scripted providers. **Never weaken or bypass the network guard**, and never add a
  test that needs a real host. Live checks belong to the `live` marker and
  [docs/LIVE-VALIDATION-PLAN.md](docs/LIVE-VALIDATION-PLAN.md).
- **Benchmark integrity:** never change `TRUTH.lock`, the truth files, expected answers or scoring to make a
  result pass. A product change motivated by a benchmark case is logged in [docs/BENCHMARK.md](docs/BENCHMARK.md)
  §8 and confirmed on held-out fixtures.

## Sensitive areas

Changes in these areas need extra care, extra tests, and an explicit note in the pull request.

**Migrations** (`src/tracewise/db/migrations/versions/`):
- Add a new numbered revision; never edit an applied one. Write both `upgrade` and `downgrade`.
- If a downgrade could lose data, it must refuse instead of deleting (see 0010).
- New tables carrying `installation_id` need RLS and the tenant policy. `tests/db/test_db_security.py` and
  `tests/db/test_privilege_matrix.py` enforce this; update the documented privilege matrix if grants change.
- Bump the head expected by `tests/db/test_fresh_install.py` and `tests/db/test_process_entrypoints.py`.

**Tenant isolation and authorisation:**
- Tenant reads and writes go through `transaction(pool, tenant=installation_id)` on the tenant pool.
- Publication must keep the per-surface re-check (`_recheck`) before every GitHub write.

**Retries and idempotency:**
- New GitHub writes reconcile before creating (find by app identity and first-line marker), record state in
  `publication`, and are safe to repeat.
- Respect the job deadline and attempt limits in `jobs/queue.py`.

**Secrets and evidence:**
- Never commit real credentials, `.env` files, keys, signed URLs or private logs. Use synthetic, obviously fake
  values in tests.
- Content sent to a model provider goes through `provider_view` (redaction).
- `research/` holds dated evidence. Do not edit it, and do not open the quarantined evidence directories.

**Model providers:**
- `LLM_PROVIDER=openai` stays disabled until it is validated and approved. Do not wire a real provider into product
  code.
- The OpenAI smoke harness (`scripts/openai_smoke.py`) must never run in tests or CI.

## Commits and pull requests

- Keep commits small and focused: one logical change, with its tests, per commit.
- Write commit subjects in the existing style, for example `fix(prepass): …`, `feat(db): …`, `test: …`,
  `docs: …`. Explain *why* in the body.
- Fill in the pull request template: what changed and why, the checks you ran, security and tenant-isolation
  impact, migration or configuration impact, documentation updates, and confirmation that no secrets or private
  evidence are included.

## Reporting bugs and proposing features

Use the issue forms (**Bug report**, **Feature request**). Remove secrets, tokens, private code and private logs
before posting. **Security vulnerabilities must not go in issues:** follow [SECURITY.md](SECURITY.md).

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
