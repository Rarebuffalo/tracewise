"""Publication reconciliation under job takeover and retry: the latest job attempt's report is what the updatable
surfaces show, and the write-once commit comment, which GitHub lets an App edit only with Contents write (not
requested), is never left showing an earlier attempt's report without the Check Run saying so.

Offline: disposable PostgreSQL, the real queue, handler and publisher, scripted providers and fake GitHub. Takeovers
happen at fixed points (right after a GitHub write returns, i.e. while the request was "in flight" for the database)."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import hashlib
import logging
from typing import Any

from tests.db.test_analyze_worker import World, call, final, head, server  # noqa: F401 - module fixtures
from tests.db.test_attempt_fencing import SLOW_BEAT, claim_as, expire, make_world
from tests.github_state import APP_ID
from tracewise.github.client import RepoClient
from tracewise.github.publish import Publisher, PublishTarget
from tracewise.jobs.queue import Fence
from tracewise.report.render import SUPERSEDED_NOTE, SUPERSEDED_SUMMARY, CheckOutput

FIRST = "First attempt says the tax rate replaces the total"
LATEST = "Latest attempt says the subtotal is dropped from the total"


def answer(root_cause: str) -> list[Any]:
    return [call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), final(root_cause=root_cause)]


def world(pool: Any, owner: Any, server: Any, tmp_path: Any, head: str, tenant_pool: Any, *roots: str) -> World:
    return make_world(pool, owner, server, tmp_path, head, tenant_pool, scripts=[answer(r) for r in roots])


def takeover_after(monkeypatch: Any, owner: Any, pool: Any, jid: int, operation: str) -> list[bool]:
    """Let the first `operation` reach (fake) GitHub, then hand the job to another worker before the caller can
    record it: the in-flight boundary, made deterministic."""
    real = RepoClient.request
    done: list[bool] = []

    def request(self: RepoClient, name: str, **kw: Any) -> Any:
        out = real(self, name, **kw)
        if name == operation and not done:
            done.append(True)
            expire(owner, jid)
            claim_as(pool, "wB")
        return out

    monkeypatch.setattr(RepoClient, "request", request)
    return done


def events(caplog: Any, name: str) -> list[dict[str, Any]]:
    return [r.tw for r in caplog.records if isinstance(getattr(r, "tw", None), dict) and r.tw.get("event") == name]


def check_text(w: World) -> str:
    (cr,) = w.state.check_runs
    return str(cr["output"]["text"])


def finish_with_a_new_owner(w: World, owner: Any, jid: int) -> dict[str, Any]:
    expire(owner, jid)  # wB never runs; a later attempt takes over and finishes
    assert w.worker("wC", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded"
    return j


# ------------------------------------------------------------------ A: stale in-flight commit comment


def test_a_a_stale_in_flight_commit_comment_is_adopted_and_the_same_report_completes(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch, caplog
) -> None:
    """A persisted its validated report, its commit comment reached GitHub, then the job was taken over. F1: the new
    owner publishes A's persisted report (no second investigation), so the commit comment it adopts is the current
    report: GitHub and the database agree, and no "earlier attempt" note is needed."""
    caplog.set_level(logging.DEBUG)
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST)
    jid = w.enqueue()
    took = takeover_after(monkeypatch, owner, pool, jid, "create_commit_comment")
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()  # A's comment reached GitHub; A could not record it
    assert owner.execute("SELECT count(*) FROM publication WHERE state = 'published'").fetchone() == (0,)
    assert took and w.state.count("POST", "cr") == 0  # A stopped: no Check Run from the stale attempt

    j = finish_with_a_new_owner(w, owner, jid)
    assert j["result"]["resumed"] is True and w.provider_calls == 1  # the report was not regenerated
    (cc,) = w.all_ccs()  # one comment, never a duplicate
    assert j["result"]["publications"]["commit_comment"] == "adopted" and FIRST in cc["body"]
    (digest,) = owner.execute("SELECT content_digest FROM publication WHERE surface = 'commit_comment'").fetchone()
    assert digest == hashlib.sha256(cc["body"].encode()).hexdigest()
    assert FIRST in check_text(w) and SUPERSEDED_NOTE not in check_text(w)
    assert analysis_root_cause(owner) == FIRST and events(caplog, "analysis.publication_resumed")


def test_a_a_publication_failure_after_diagnosis_resumes_the_same_report(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    """F1: attempt 1 diagnosed and published the commit comment, then its Check Run failed transiently. Attempt 2
    finishes publishing attempt 1's validated report: no second model call, no divergent report, no note."""
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST)
    jid = w.enqueue()
    w.state.fault("POST", "cr", 503)
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert w.jobrow(jid)["status"] == "retry_wait" and len(w.all_ccs()) == 1
    assert owner.execute("SELECT publish_result FROM analysis").fetchone() == (None,)  # publication incomplete
    owner.execute("UPDATE job SET run_after = now() WHERE id = %s", (jid,))
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert (j["status"], j["result"]["publications"]) == (
        "succeeded",
        {"commit_comment": "already_published", "check_run": "published"},
    )
    assert w.provider_calls == 1 and len(w.all_ccs()) == 1 and FIRST in check_text(w)
    assert owner.execute("SELECT publish_result IS NOT NULL FROM analysis").fetchone() == (True,)


def test_a_a_new_investigation_after_a_completed_publication_says_the_comment_is_superseded(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    """The remaining superseded case: everything was published and recorded, but the job's completion was lost, so
    it runs again and investigates afresh (nothing is pending). The write-once commit comment keeps the first report;
    the Check Run carries the new one and says so."""
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST)
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    owner.execute("UPDATE job SET status = 'retry_wait', finished_at = NULL, run_after = now() WHERE id = %s", (jid,))
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert (j["status"], j["result"]["publications"]["commit_comment"]) == ("succeeded", "superseded")
    assert len(w.all_ccs()) == 1 and LATEST in check_text(w) and SUPERSEDED_NOTE in check_text(w)
    (cr,) = w.state.check_runs  # the summary, shown first on GitHub, says it before the result
    assert cr["output"]["summary"].startswith(SUPERSEDED_SUMMARY) and LATEST in cr["output"]["summary"]


def test_a_an_identical_report_is_adopted_without_any_note(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, FIRST)
    jid = w.enqueue()
    takeover_after(monkeypatch, owner, pool, jid, "create_commit_comment")
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = finish_with_a_new_owner(w, owner, jid)
    assert j["result"]["publications"]["commit_comment"] == "adopted"
    assert len(w.all_ccs()) == 1 and SUPERSEDED_NOTE not in check_text(w)
    assert SUPERSEDED_SUMMARY not in w.state.check_runs[0]["output"]["summary"]


# ------------------------------------------------------------------ B: repeated publication by the same attempt


def test_b_the_same_attempt_publishing_again_writes_nothing_new_a_later_one_reasserts(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST)
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    (aid,) = owner.execute("SELECT id FROM analysis").fetchone()
    owner.execute(
        "UPDATE job SET status = 'running', locked_by = 'wP', locked_until = now() + interval '1 hour', finished_at = NULL"
        " WHERE id = %s",
        (jid,),
    )
    rc = RepoClient(w.http, w.tokens, installation_id=9, repo_id=7, full_name="acme/coffee", scope="publish")
    t = PublishTarget(9, 7, "acme/coffee", w.head, 55, 1, 3, pr_number=12)
    out, body = CheckOutput("t", "s", "report"), "<!-- tracewise:pr:wf3 -->\nreport"

    def publisher(generation: int) -> Publisher:
        owner.execute("UPDATE job SET attempts = %s WHERE id = %s", (generation, jid))
        return Publisher(w.tenant_pool, rc, app_id=APP_ID, check_lease=lambda: None, fence=Fence(jid, 9, "wP", generation))

    p = publisher(1)
    assert [p.check_run(t, aid, out).state for _ in range(3)] == ["updated", "unchanged", "unchanged"]
    assert [p.pr_comment(t, aid, body).state for _ in range(3)] == ["published", "unchanged", "unchanged"]
    assert [p.commit_comment(t, aid, "anything").state for _ in range(2)] == ["superseded", "superseded"]

    def counts() -> tuple[int, ...]:
        kinds = (("POST", "cc"), ("POST", "cr"), ("PATCH", "cr"), ("POST", "prc"), ("PATCH", "prc"))
        return tuple(w.state.count(m, k) for m, k in kinds)

    assert counts() == (1, 1, 1, 1, 0)  # one object per surface; repeats are digest-skipped
    p = publisher(2)  # a later generation does not trust the stored digest: rewrite in place, never a new object
    assert (p.check_run(t, aid, out).state, p.pr_comment(t, aid, body).state) == ("reconciled", "reconciled")
    assert counts() == (1, 1, 2, 1, 1)


# ------------------------------------------------------------------ C: takeover during Check Run publication


def test_c_an_in_flight_check_run_create_is_adopted_by_the_new_owner(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST)
    jid = w.enqueue()
    takeover_after(monkeypatch, owner, pool, jid, "create_check_run")
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert FIRST in check_text(w)  # applied by GitHub, never recorded by the stale attempt
    assert owner.execute("SELECT count(*) FROM publication WHERE surface = 'check_run' AND state = 'published'").fetchone() == (
        0,
    )
    j = finish_with_a_new_owner(w, owner, jid)
    assert j["result"]["publications"]["check_run"] == "adopted"
    assert w.state.count("POST", "cr") == 1  # adopted, not duplicated
    assert FIRST in check_text(w) and analysis_root_cause(owner) == FIRST  # the persisted report, on GitHub and in the DB
    assert {e["surface"] for e in events(caplog, "publication.reconciled")} >= {"check_run"}


def test_c_an_unrecorded_update_of_a_newer_version_is_completed_not_left_half_done(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    """Generation 1 published and recorded X; its completion was lost, so generation 2 investigated again and
    persisted Y (which resets the ops record), then its Check Run update reached GitHub unrecorded at a takeover.
    The next owner finishes publishing Y. Whatever GitHub shows, the stored digest is never trusted on a later
    generation (rule 7); `test_b_*` pins that directly."""
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST, FIRST)
    jid = w.enqueue()
    owner.execute("UPDATE job SET max_attempts = 5 WHERE id = %s", (jid,))  # room for four generations
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()  # generation 1: X published and recorded
    owner.execute("UPDATE job SET status = 'retry_wait', finished_at = NULL, run_after = now() WHERE id = %s", (jid,))
    takeover_after(monkeypatch, owner, pool, jid, "update_check_run")
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()  # generation 2: Y persisted, its update applied, unrecorded
    assert LATEST in check_text(w) and owner.execute("SELECT publish_result FROM analysis").fetchone() == (None,)
    j = finish_with_a_new_owner(w, owner, jid)  # generation 4 (wB held 3): resumes Y
    assert j["result"]["resumed"] is True and j["result"]["publications"]["check_run"] == "updated"
    assert LATEST in check_text(w) and analysis_root_cause(owner) == LATEST
    assert w.state.count("POST", "cr") == 1 and w.provider_calls == 2


# ------------------------------------------------------------------ D: takeover during PR comment publication


def test_d_an_in_flight_pr_comment_is_adopted_by_the_new_owner(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, LATEST)
    w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    jid = w.enqueue()
    takeover_after(monkeypatch, owner, pool, jid, "create_pr_comment")
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    (c,) = w.state.pr_comments[12]
    assert FIRST in c["body"]
    j = finish_with_a_new_owner(w, owner, jid)
    assert j["result"]["publications"]["pr_comment"] == "adopted" and j["result"]["resumed"] is True
    (c,) = w.state.pr_comments[12]  # the same comment, rewritten with the persisted report (its PR is in the record)
    assert FIRST in c["body"] and analysis_root_cause(owner) == FIRST
    assert w.all_ccs() == []  # PR runs never use the commit comment


# ------------------------------------------------------------------ uncertain outcomes


def test_a_transient_failure_on_a_write_is_logged_as_an_uncertain_outcome_and_reconciled_next_attempt(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST, FIRST)
    jid = w.enqueue()
    w.state.fault("POST", "cr", 503)
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert [e["operation"] for e in events(caplog, "publication.outcome_uncertain")] == ["create_check_run"]
    owner.execute("UPDATE job SET run_after = now() WHERE id = %s", (jid,))
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert w.jobrow(jid)["status"] == "succeeded" and w.state.count("POST", "cr") == 1
    attempted = {(e["surface"], e["operation"]) for e in events(caplog, "publication.attempted")}
    assert ("check_run", "create_check_run") in attempted


def analysis_root_cause(owner: Any) -> str:
    (d,) = owner.execute("SELECT diagnosis FROM analysis").fetchone()
    return str(d["root_cause"])


# ------------------------------------------------------------------ O-2: the publication deadline


class _Spent:
    def remaining(self) -> float:
        return 0.0


def test_a_write_that_cannot_start_before_the_deadline_is_not_started_and_never_recorded(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, caplog
) -> None:
    import pytest

    from tracewise.github import errors as gh_err

    caplog.set_level(logging.DEBUG)
    w = world(pool, owner, server, tmp_path, head, tenant_pool, FIRST)
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    (aid,) = owner.execute("SELECT id FROM analysis").fetchone()
    owner.execute(
        "UPDATE job SET status = 'running', locked_by = 'wP', locked_until = now() + interval '1 hour', finished_at = NULL"
        " WHERE id = %s",
        (jid,),
    )
    rc = RepoClient(w.http, w.tokens, installation_id=9, repo_id=7, full_name="acme/coffee", scope="publish", deadline=_Spent())
    p = Publisher(w.tenant_pool, rc, app_id=APP_ID, check_lease=lambda: None, fence=Fence(jid, 9, "wP", 1))
    t = PublishTarget(9, 7, "acme/coffee", w.head, 55, 1, 3, pr_number=12)
    before = len(w.gh.requests)
    with pytest.raises(gh_err.DeadlineExhausted):
        p.pr_comment(t, aid, "<!-- tracewise:pr:wf3 -->\nreport")
    assert len(w.gh.requests) == before  # not even the reconcile listing went out
    assert owner.execute("SELECT count(*) FROM publication WHERE surface = 'pr_comment'").fetchone() == (0,)
    assert events(caplog, "publication.outcome_uncertain") == []
