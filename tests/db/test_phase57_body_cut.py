"""Phase 57: a connection cut while reading a GitHub response body on the final attempt must not bypass the
partial-publication guard (D-14 as implemented). Before the fix the raw httpx error reached the generic handler,
which published "could not complete" over the already-published PR comment report. Offline: fake GitHub."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401

CR = re.compile(r"^/repos/acme/coffee/check-runs$")


class CutBody(httpx.SyncByteStream):
    def __iter__(self) -> Any:
        yield b'{"id"'
        raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]
    return World(pool, owner, server, tmp_path / "ws", head)


@pytest.mark.parametrize("fault", ["status_502", "body_cut"])
def test_a_published_report_is_never_replaced_by_a_notice_when_a_later_surface_fails(world: World, fault: str) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    posts = {"n": 0}

    def check_run_post(req: httpx.Request) -> httpx.Response:
        posts["n"] += 1
        if fault == "status_502":
            return httpx.Response(502, json={"message": "Server Error"})
        return httpx.Response(201, headers={"content-type": "application/json"}, stream=CutBody())

    world.gh.routes.insert(0, ("POST", CR, check_run_post))
    jid = world.enqueue()
    for _ in range(3):
        if not world.worker().run_once():
            break
        world.ready(jid)
    j = world.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("dead", 3)
    (prc,) = world.state.pr_comments[12]
    assert "could not complete" not in prc["body"].lower()  # the published diagnosis stands
    assert posts["n"] == 3  # one POST per attempt; no extra notice attempt
    assert world.owner.execute("SELECT status FROM analysis").fetchone()[0] != "could_not_complete"
