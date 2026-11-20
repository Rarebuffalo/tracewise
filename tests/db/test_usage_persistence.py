"""Usage breakdown persistence (migration 0014): provider-reported counts only, NULL for "not reported", and a source
that tells a measured run from one without any provider call or with a failed step. Offline: disposable PostgreSQL,
fake GitHub, scripted provider."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.db.test_analyze_worker import call, head, server  # noqa: F401 - module fixtures
from tests.db.test_attempt_fencing import make_world
from tests.investigate.factory import B02_ANSWER
from tracewise.investigate.loop import InvestigationResult
from tracewise.investigate.provider import ProviderError, StepResponse, StepUsage
from tracewise.investigate.validate import UsageDetail

COLS = "tokens_in, tokens_out, cached_input_tokens, reasoning_output_tokens, usage_source"


def answer(usage: StepUsage) -> StepResponse:
    return StepResponse(text=json.dumps(B02_ANSWER), usage=usage)


def read(usage: StepUsage) -> StepResponse:
    r = call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41)
    return StepResponse(tool_calls=r.tool_calls, usage=usage)


def analysed(
    pool: Any, owner: Any, server: Any, tmp_path: Any, head: str, tenant_pool: Any, script: list[Any]
) -> tuple[Any, ...]:
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[script, script, script])
    w.enqueue()
    w.run()
    row = owner.execute(f"SELECT {COLS} FROM analysis").fetchone()  # noqa: S608
    assert row is not None
    return tuple(row)


def test_a_reported_breakdown_is_summed_and_stored(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    script = [read(StepUsage(50, 10, 20, 4)), answer(StepUsage(80, 60, 30, 0))]
    assert analysed(pool, owner, server, tmp_path, head, tenant_pool, script) == (130, 70, 50, 4, "provider")


def test_an_unreported_breakdown_is_null_not_zero(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    script = [read(StepUsage(50, 10, 20, None)), answer(StepUsage(80, 60, None, 0))]
    assert analysed(pool, owner, server, tmp_path, head, tenant_pool, script) == (
        130,
        70,
        None,
        None,
        "provider",
    )  # reasoning: one step did not report it


def test_a_failed_step_marks_the_totals_partial(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    def outage(req: Any) -> Any:
        raise ProviderError("synthetic outage")

    script = [read(StepUsage(50, 10, 0, 0)), outage]
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[list(script) for _ in range(3)])
    jid = w.enqueue()
    w.run()  # attempt 1 fails and is retried: nothing persisted
    assert owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,)
    owner.execute("UPDATE job SET deadline_at = now() + interval '90 seconds', run_after = now() WHERE id = %s", (jid,))
    w.run()  # no retry fits: the final attempt records could_not_complete with what was measured
    assert owner.execute(f"SELECT status, {COLS} FROM analysis").fetchone() == ("could_not_complete", 50, 10, 0, 0, "partial")  # noqa: S608


def test_no_provider_call_is_recorded_as_such() -> None:
    assert UsageDetail.of(None) == UsageDetail("no_call", None, None)
    inv = InvestigationResult("no_error_line", None, "fake", None)
    assert UsageDetail.of(inv) == UsageDetail("no_call", None, None)


@pytest.mark.parametrize(
    ("values", "ok"),
    [
        ((100, 40, 60, 25, "provider"), True),
        ((100, 40, None, None, None), True),  # a legacy or notice row: no measurement record
        ((0, 0, None, None, "no_call"), True),
        ((100, 40, 101, None, "provider"), False),  # cached is part of the input total
        ((100, 40, None, 41, "provider"), False),  # reasoning is part of the output total
        ((None, 40, 1, None, "provider"), False),  # a subset without its total
        ((0, 0, 0, None, "no_call"), False),  # no call, yet a measured subset
        ((1, 1, None, None, "estimated"), False),  # only the three sources exist
    ],
)
def test_the_schema_refuses_an_impossible_breakdown(pool, owner, values, ok) -> None:  # type: ignore[no-untyped-def]
    from tracewise.db import repositories as repo
    from tracewise.db.session import transaction

    with transaction(pool) as c:
        repo.upsert_installation(c, 9, "acme")
        repo.upsert_repository(c, 7, 9, "acme/coffee")
        run = repo.insert_workflow_run(
            c,
            installation_id=9,
            repo_id=7,
            run_id=55,
            attempt=1,
            workflow_id=3,
            head_sha="c" * 40,
            head_branch="main",
            head_repo_id=7,
            event="push",
            conclusion="failure",
        )

    def write() -> None:
        with transaction(pool) as c:
            t_in, t_out, cached, reasoning, source = values
            repo.upsert_analysis(
                c,
                installation_id=9,
                run_pk=run,
                status="diagnosed",
                category=None,
                confidence_band=None,
                diagnosis=None,
                tokens_in=t_in,
                tokens_out=t_out,
                cached_input_tokens=cached,
                reasoning_output_tokens=reasoning,
                usage_source=source,
            )

    if ok:
        write()
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            write()


def test_the_report_never_double_counts_subsets_and_separates_completeness(
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:  # type: ignore[no-untyped-def]
    from tracewise import ops

    script = [read(StepUsage(50, 10, 20, 4)), answer(StepUsage(80, 60, 30, 0))]
    analysed(pool, owner, server, tmp_path, head, tenant_pool, script)
    r = ops.report(pool)
    t = r["tokens"]
    assert (t["in"], t["out"]) == (130, 70)  # totals as reported; cached and reasoning are parts of them, not added
    assert t["cached_in"] == {"total": 50, "reported": 1, "not_reported": 0}
    assert t["reasoning_out"] == {"total": 4, "reported": 1, "not_reported": 0}
    assert t["usage"] == {"provider": 1, "partial": 0, "no_call": 0, "unknown": 0}
    assert r["cost_usd"]["unpriced_with_cached_input"] == 1  # unpriced, and would stay so even with prices configured


def test_cached_input_makes_the_cost_unavailable_instead_of_overstated(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    from decimal import Decimal

    from tests.context.conftest import make_fetcher
    from tests.github_state import APP_ID
    from tracewise import ops
    from tracewise.jobs.handlers.analyze import AnalyzeDeps, make_analyze_handler
    from tracewise.jobs.worker import Worker

    w = make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[[answer(StepUsage(80, 60, 30, 0))]])
    deps = AnalyzeDeps(
        tenant_pool,
        w.http,
        w.tokens,
        APP_ID,
        provider_factory=w.provider,
        fetcher_factory=lambda: make_fetcher(server, tmp_path / "ws"),
        price_input_per_mtok=Decimal("3"),
        price_output_per_mtok=Decimal("15"),
    )
    w.enqueue()
    assert Worker(pool, {"analyze": make_analyze_handler(deps)}, "wp").run_once()
    assert owner.execute("SELECT cost_usd, cached_input_tokens FROM analysis").fetchone() == (None, 30)
    assert ops.report(pool)["cost_usd"]["unpriced_with_cached_input"] == 1


def test_the_backfill_marks_only_provably_modelless_legacy_rows(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    from tests.pg import OWNER
    from tracewise.db import repositories as repo
    from tracewise.db.migrate import downgrade, upgrade
    from tracewise.db.session import transaction

    rows = {  # (provider, status, inconclusive_reason, tokens) -> expected usage_source after 0016
        ("none", "inconclusive", "attempt_deadline_exhausted", 0): "no_call",
        ("fake", "logs_unavailable", None, 0): "no_call",
        ("fake", "inconclusive", "no_error_line", 0): "no_call",
        ("fake", "inconclusive", "provider_failed", 0): None,  # a failed first step may have spent tokens
        ("fake", "diagnosed", None, 0): None,  # zero alone proves nothing
        ("fake", "inconclusive", "no_error_line", 12): None,  # contradicting totals: left unknown
        (None, "could_not_complete", None, None): None,  # a notice: no measurement record
    }
    with transaction(pool) as c:
        repo.upsert_installation(c, 9, "acme")
        repo.upsert_repository(c, 7, 9, "acme/coffee")
        ids = {}
        for n, (prov, status, reason, tok) in enumerate(rows):
            run = repo.insert_workflow_run(
                c,
                installation_id=9,
                repo_id=7,
                run_id=100 + n,
                attempt=1,
                workflow_id=3,
                head_sha="c" * 40,
                head_branch="main",
                head_repo_id=7,
                event="push",
                conclusion="failure",
            )
            diag = {"inconclusive_reason": reason} if reason else None
            ids[(prov, status, reason, tok)] = repo.upsert_analysis(
                c,
                installation_id=9,
                run_pk=run,
                status=status,
                category=None,
                confidence_band=None,
                diagnosis=diag,
                provider=prov,
                tokens_in=tok,
                tokens_out=tok,
            )
    downgrade(pg.url(OWNER), "0015")
    upgrade(pg.url(OWNER))
    for key, want in rows.items():
        got = owner.execute("SELECT usage_source, tokens_in FROM analysis WHERE id = %s", (ids[key],)).fetchone()
        assert got == (want, key[3]), key  # totals untouched
