"""End to end through the real worker and handler: a source that stays unreachable, and a defect inside a tool, are
retried and then reported as "could not complete". Neither is ever published as a completed analysis (no commit
comment, never `diagnosed` or a completed `inconclusive`). Offline: disposable PostgreSQL, fake GitHub, local git."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

from typing import Any

from tests.db.test_analyze_worker import call, final, head, server  # noqa: F401 - module fixtures
from tests.db.test_attempt_fencing import make_world
from tests.investigate.factory import B02_ANSWER
from tracewise.context.gitfetch import GitObjectSource
from tracewise.context.source import TransientReadError
from tracewise.report.render import REASON_TEXT

ABSTAIN = {"category": "unknown", "problem_location": None, "fix": None}


def abstain() -> list[Any]:
    return [call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), final(**ABSTAIN)]


def last_attempt(owner: Any, jid: int) -> None:
    # No retry backoff fits any more: the next attempt is the final one (as test_phase50_reliability A1).
    owner.execute("UPDATE job SET deadline_at = now() + interval '90 seconds', run_after = now() WHERE id = %s", (jid,))


def test_a_source_that_stays_unreachable_is_retried_then_could_not_complete(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    def outage(self: Any, entry: Any) -> Any:
        raise TransientReadError("synthetic 502")

    monkeypatch.setattr(GitObjectSource, "_read_blob", outage)
    monkeypatch.setattr("tracewise.context.source.time.sleep", lambda s: None)
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[abstain(), abstain()])
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["last_error"]) == ("retry_wait", "RetryableError: infrastructure failure (source_unavailable)")
    assert w.state.check_runs == [] and w.all_ccs() == []  # nothing published from an incomplete investigation
    last_attempt(owner, jid)
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["result"]["outcome"]) == ("succeeded", "could_not_complete")  # not "inconclusive"
    (cr,) = w.state.check_runs
    assert "a temporary GitHub failure that outlasted the retries" in cr["output"]["text"]  # REASON_TEXT, not a verdict
    assert "source_unavailable" in REASON_TEXT
    assert w.all_ccs() == []  # FS-ERR-1 / D-8: never the commit comment


def test_a_defect_inside_a_tool_is_never_published_as_an_analysis(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    def defect(self: Any, entry: Any) -> Any:
        raise TypeError("'NoneType' object is not subscriptable")  # before D-C: answered "invalid arguments"

    monkeypatch.setattr(GitObjectSource, "_read_blob", defect)
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[abstain(), abstain()])
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "retry_wait" and "internal error in tool read_file (TypeError)" in j["last_error"]
    assert "NoneType" not in j["last_error"] and w.state.check_runs == []
    last_attempt(owner, jid)
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "dead"  # never `succeeded` with a diagnosis
    (cr,) = w.state.check_runs  # FS-ERR-1: the user is told it could not complete
    assert "could not complete" in cr["output"]["title"].lower() and w.all_ccs() == []
    assert owner.execute("SELECT count(*) FROM analysis WHERE status IN ('diagnosed', 'inconclusive')").fetchone() == (0,)


def test_a_validated_answer_is_not_regenerated_for_a_transient_validation_read(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    """The model answered; the validator's read hits one transient failure: retried in place, one model call."""
    real = GitObjectSource._read_blob
    state = {"validation": 0}

    def flaky(self: Any, entry: Any) -> Any:
        if state["validation"] == 1:
            state["validation"] = 2
            raise TransientReadError("synthetic 502")
        return real(self, entry)

    def answered(req: Any) -> Any:
        state["validation"] = 1  # the next read is the validator's
        return final(**{k: B02_ANSWER[k] for k in ("category", "root_cause")})

    monkeypatch.setattr(GitObjectSource, "_read_blob", flaky)
    monkeypatch.setattr("tracewise.context.source.time.sleep", lambda s: None)
    w = make_world(
        pool,
        owner,
        server,
        tmp_path,
        head,
        tenant_pool,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), answered]],
    )
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 1, "diagnosed")
    assert w.provider_calls == 1 and state["validation"] == 2
