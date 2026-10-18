"""Phase 13: recovery under injected GitHub faults (local fakes only). A fault in one repository must not stop
the others, and a pass with an unrecovered fault is reported as incomplete, not as success."""

from __future__ import annotations

import re

import httpx
import pytest

from tests.db.test_recovery import NOW, Hub, delivery, redeliver, run_obj, setup_tenants, sweep
from tests.github_fake import jresp

RUNS = re.compile(r"^/repos/[^/]+/[^/]+/actions/runs$")


def _faulty(hub: Hub, fault: str) -> None:
    orig = hub._runs

    def runs(req: httpx.Request) -> httpx.Response:
        if "/acme/coffee/" in req.url.path:  # repo 7 is broken; repos 8 and 70 are fine
            if fault == "timeout":
                raise httpx.ReadTimeout("timed out", request=req)
            if fault == "badjson":
                return httpx.Response(200, content=b"{not json")
            if fault == "shape":
                return jresp(200, {"workflow_runs": "not-a-list"})
            return jresp(int(fault), {"message": "x"})
        return orig(req)

    hub.gh.routes.insert(0, ("GET", RUNS, runs))


@pytest.mark.parametrize(
    ("fault", "error"),
    [
        ("422", "GitHubPermanent"),
        ("badjson", "GitHubPermanent"),
        ("shape", "GitHubPermanent"),
        ("500", "GitHubRetryable"),
        ("timeout", "GitHubRetryable"),
    ],
)
def test_one_broken_repository_does_not_block_the_others(pool, owner, fault, error) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.runs[8] = [run_obj(81, repo_id=8, name="acme/lib")]
    hub.runs[70] = [run_obj(701, repo_id=70, name="other/app")]
    _faulty(hub, fault)
    s = sweep(pool, hub)
    assert s.enqueued == 2 and s.repos_swept == 2, s.as_dict()  # repos 8 and 70 still swept
    assert s.errors[error] == 1 and s.failed_repos == 1
    assert s.completed is False and s.stopped is None  # incomplete (a repo failed), but not a stop
    assert owner.execute("SELECT count(*) FROM job").fetchone() == (2,)
    again = sweep(pool, hub)  # a later pass revisits the failed repository and adds nothing twice
    assert again.enqueued == 0 and again.duplicates == 2 and again.failed_repos == 1


def test_rate_limit_still_stops_the_pass_and_is_labelled_as_such(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.faults["runs"] = ["rate_limit"]
    s = sweep(pool, hub)
    assert (s.stopped, s.completed, s.repos_swept) == ("rate_limited", False, 0)


def test_server_errors_on_the_delivery_list_are_not_called_rate_limits(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.faults["list"] = ["503", "503", "503", "503"]
    assert redeliver(pool, hub).stopped == "github_unavailable"
    hub2 = Hub()
    hub2.faults["list"] = ["rate_limit"]
    assert redeliver(pool, hub2).stopped == "rate_limited"


@pytest.mark.parametrize("bad", ["422", "badjson"])
def test_unexpected_delivery_list_failure_is_reported_not_raised(pool, owner, bad) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    if bad == "badjson":
        hub.gh.routes.insert(0, ("GET", re.compile(r"^/app/hook/deliveries$"), lambda r: httpx.Response(200, content=b"<html>")))
    else:
        hub.faults["list"] = [bad]
    s = redeliver(pool, hub)
    assert (s.stopped, s.completed) == ("list_failed", False) and s.errors["list"] == 1
    assert owner.execute("SELECT count(*) FROM recovery_checkpoint").fetchone() == (0,)  # high-water mark not advanced


def test_interrupted_redelivery_request_counts_towards_the_attempt_cap(pool, owner) -> None:  # type: ignore[no-untyped-def]
    """The POST may have reached GitHub before the connection failed: record the attempt as uncertain."""
    from datetime import timedelta

    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(41, "g-interrupted")]
    hub.faults["redeliver"] = ["502"]
    s = redeliver(pool, hub)
    assert s.stopped == "github_unavailable" and s.redelivered == 0
    row = owner.execute("SELECT attempts, last_status FROM redelivery_request WHERE guid = 'g-interrupted'").fetchone()
    assert row == (1, "uncertain")
    assert redeliver(pool, hub).skipped["cooldown"] == 1  # the cooldown applies to the uncertain attempt
    later = redeliver(pool, hub, now=lambda: NOW + timedelta(hours=1))
    assert later.redelivered == 1 and hub.redelivered == [41]
