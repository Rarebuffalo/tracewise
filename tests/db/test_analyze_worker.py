"""T-502/T-503 + worker wiring, OFFLINE: the registered `analyze` handler run by the real Worker against
a disposable Postgres, the local git http-backend, a stateful fake GitHub API and a scripted provider.

Each test asserts fake-GitHub state, external write counts, publication/analysis rows and the job state.
These are REPLAY-level checks; GitHub's real behaviour (permissions, limits, attribution fields) is LIVE-gated.
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.context.conftest import make_fetcher
from tests.context.test_collect import api_job
from tests.git_server import GitServer, git_server
from tests.github_fake import FakeGitHub, jresp
from tests.github_state import APP_ID, GitHubState
from tests.helpers import fixture
from tests.investigate.factory import B02_ANSWER, PRICING, TESTS
from tracewise.contracts import AnalysisJob
from tracewise.db import repositories as repo
from tracewise.db.session import DatabaseUnavailable, transaction
from tracewise.github.publish import CHECK_NAME, Publisher, PublishTarget
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.provider import ProviderTimeout, StepResponse, StepUsage, ToolCallRequest
from tracewise.jobs import queue
from tracewise.jobs.handlers import analyze as analyze_mod
from tracewise.jobs.handlers.analyze import AnalyzeDeps, make_analyze_handler
from tracewise.jobs.worker import Worker
from tracewise.report.render import CheckOutput

C0 = "0" * 40
BLOB = "https://productionresultssa1.blob.core.windows.net/logs/{job}.txt?sig=x"


@pytest.fixture(scope="module")
def server() -> Iterator[GitServer]:
    s = git_server(secrets.token_hex(20))
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture(scope="module")
def head(server: GitServer) -> str:
    return server.make_repo(
        "acme",
        "coffee",
        {
            "coffee_shop/__init__.py": "",
            "coffee_shop/pricing.py": PRICING,
            "tests/test_pricing.py": TESTS,
            "README.md": "# Coffee\n",
        },
    )


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """No connections except loopback; personal tokens in the environment must never be used."""
    real = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if isinstance(address, tuple) and host not in ("127.0.0.1", "::1"):
            raise AssertionError(f"unexpected network connection to {host}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setenv("GITHUB_TOKEN", "personal-token-must-not-be-used")
    monkeypatch.setenv("GH_TOKEN", "personal-token-must-not-be-used")


def call(name: str, cid: str = "c", **args: Any) -> StepResponse:
    return StepResponse(tool_calls=(ToolCallRequest(cid, name, args),), usage=StepUsage(50, 10))


def final(**over: Any) -> StepResponse:
    return StepResponse(text=json.dumps({**B02_ANSWER, **over}), usage=StepUsage(80, 60))


def known() -> list[Any]:
    return [call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), final()]


class World:
    """One installation (9), one repository (7, acme/coffee), one failed run (55).

    `pool` is the system plane (queue, ingress); the analyze handler runs on `tenant_pool` (RLS, T-705)."""

    tenant_pool: Any = None
    quota: int | None = None  # T-703: AnalyzeDeps.analysis_quota for the worker this World builds

    def __init__(
        self,
        pool: Any,
        owner: Any,
        server: GitServer,
        ws_root: Path,
        head: str,
        *,
        event: str = "push",
        log_status: int = 302,
        scripts: list[list[Any]] | None = None,
        run_attempt: int = 1,
    ) -> None:
        self.pool, self.owner, self.server, self.head = pool, owner, server, head
        self.gh = FakeGitHub()
        self.gh.add_token_route()
        self.gh.next_tokens = [server.token]
        self.state = GitHubState(self.gh).install()
        doc, lines = api_job(101, "Tests (Python 3.11)", "failure", fixture("pytest_b02.out"))
        self.gh.route("GET", r"^/repos/acme/coffee/actions/runs/55/attempts/\d+/jobs$", jresp(200, {"jobs": [doc]}))
        self.gh.route(
            "GET",
            r"^/repos/acme/coffee/actions/jobs/101/logs$",
            httpx.Response(302, headers={"location": BLOB.format(job=101)})
            if log_status == 302
            else jresp(log_status, {"message": "x"}, {"x-accepted-github-permissions": "actions=read"}),
        )
        self.gh.route(
            "GET", r"^//productionresultssa1\.blob\.core\.windows\.net/logs/101\.txt$", httpx.Response(200, text="\n".join(lines))
        )
        self.gh.route("GET", rf"^/repos/acme/coffee/commits/{head}$", jresp(200, {"sha": head, "parents": [{"sha": C0}]}))
        self.gh.route(
            "GET",
            rf"^/repos/acme/coffee/compare/{C0}\.\.\.{head}$",
            jresp(
                200,
                {
                    "total_commits": 1,
                    "files": [
                        {
                            "filename": "coffee_shop/pricing.py",
                            "status": "modified",
                            "additions": 1,
                            "deletions": 1,
                            "patch": "@@ -40,2 +40,2 @@\n     # B-02 defect\n-    return round(subtotal_ * (1 + TAX_RATE), 2)\n"
                            "+    return round(subtotal_ * TAX_RATE, 2)",
                        }
                    ],
                },
            ),
        )
        self.http = self.gh.http()
        self.tokens = self.gh.provider(self.http, app_id=APP_ID)
        self.scripts = scripts if scripts is not None else [known() for _ in range(5)]
        self.provider_calls = 0
        self.ws_root = ws_root
        self.event = event
        with transaction(pool) as c:
            repo.upsert_installation(c, 9, "acme")
            repo.upsert_repository(c, 7, 9, "acme/coffee")

    def provider(self) -> ScriptedProvider:
        self.provider_calls += 1
        return ScriptedProvider(self.scripts.pop(0))

    def job(self, attempt: int = 1, **over: Any) -> AnalysisJob:
        base = dict(
            installation_id=9,
            repo_id=7,
            repo="acme/coffee",
            run_id=55,
            attempt=attempt,
            workflow_id=3,
            head_sha=self.head,
            head_branch="feature",
            head_repo="acme/coffee",
            head_repo_id=7,
            event=self.event,
            conclusion="failure",
            delivery_id=f"d-{attempt}",
        )
        return AnalysisJob(**{**base, **over})

    def enqueue(self, attempt: int = 1, installation_id: int | None = None, **over: Any) -> int:
        j = self.job(attempt, **over)
        with transaction(self.pool) as c:
            repo.insert_workflow_run(
                c,
                installation_id=9,
                repo_id=7,
                run_id=55,
                attempt=attempt,
                workflow_id=3,
                head_sha=self.head,
                head_branch="feature",
                head_repo_id=7,
                event=self.event,
                conclusion="failure",
            )
            jid = queue.enqueue(
                c,
                kind="analyze",
                installation_id=installation_id or j.installation_id,
                dedupe_key=f"analyze:{j.repo_id}:{j.run_id}:{attempt}:{secrets.token_hex(2)}",
                payload=j.model_dump(mode="json"),
                run_key="7:55",
            )
        assert jid is not None
        return jid

    def worker(self, name: str = "w1", **kw: Any) -> Worker:
        deps = AnalyzeDeps(
            self.tenant_pool or self.pool,
            self.http,
            self.tokens,
            APP_ID,
            provider_factory=self.provider,
            fetcher_factory=lambda: make_fetcher(self.server, self.ws_root),
            analysis_quota=self.quota,
        )
        return Worker(self.pool, {"analyze": make_analyze_handler(deps)}, name, heartbeat_s=kw.pop("heartbeat_s", 5), **kw)

    def run(self, n: int = 1) -> None:
        for _ in range(n):
            assert self.worker().run_once()

    def ready(self, jid: int) -> None:
        self.owner.execute("UPDATE job SET run_after = now() - interval '1 second' WHERE id = %s", (jid,))

    def jobrow(self, jid: int) -> dict[str, Any]:
        r = self.owner.execute("SELECT status, attempts, result, last_error FROM job WHERE id = %s", (jid,)).fetchone()
        return {"status": r[0], "attempts": r[1], "result": r[2], "last_error": r[3]}

    def pubs(self) -> dict[str, tuple[str, int | None]]:
        return {s: (st, g) for s, st, g in self.owner.execute("SELECT surface, state, github_id FROM publication").fetchall()}

    def all_ccs(self) -> list[dict[str, Any]]:
        return [c for cs in self.state.commit_comments.values() for c in cs]

    def all_prcs(self) -> list[dict[str, Any]]:
        return [c for cs in self.state.pr_comments.values() for c in cs]


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]
    return World(pool, owner, server, tmp_path / "ws", head)


def assert_neutral(state: GitHubState) -> None:
    for c in state.check_runs:
        assert (c["name"], c["status"], c["conclusion"]) == (CHECK_NAME, "completed", "neutral")  # never gating
        assert len(c["output"]["annotations"]) <= 10 and len(c["output"]["text"]) <= 65535


# ---------------------------------------------------------------- 1, 2, 3: surfaces


def test_01_push_failure_commit_comment_and_neutral_check_run(world: World) -> None:
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    assert j["status"] == "succeeded" and j["result"]["outcome"] == "diagnosed"
    (cc,) = world.all_ccs()
    assert cc["commit_id"] == world.head and "<!-- tracewise:cc:wf3 -->" in cc["body"]
    assert "coffee_shop/pricing.py:41" in cc["body"] and "E   assert 0.21 == 1.21" in cc["body"]
    (cr,) = world.state.check_runs
    assert cr["external_id"] == "55" and cr["head_sha"] == world.head
    assert cr["output"]["title"] == "Code regression (medium confidence)"
    assert (
        cr["output"]["title"].startswith("Code regression") and cr["output"]["annotations"][0]["path"] == "coffee_shop/pricing.py"
    )
    assert_neutral(world.state)
    assert world.all_prcs() == [] and (world.state.count("POST", "cc"), world.state.count("POST", "cr")) == (1, 1)
    assert world.pubs() == {"commit_comment": ("published", cc["id"]), "check_run": ("published", cr["id"])}
    status, cat = world.owner.execute("SELECT status, category FROM analysis").fetchone()
    assert (status, cat) == ("diagnosed", "code_regression")


def test_02_pr_failure_pr_comment_and_check_run_no_commit_comment(world: World) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["result"]["association"] == "matched"
    (prc,) = world.state.pr_comments[12]
    assert "<!-- tracewise:pr:wf3 -->" in prc["body"] and "pull request" not in prc["body"].split("### Limits")[0][:50]
    assert world.all_ccs() == [] and len(world.state.check_runs) == 1
    assert set(world.pubs()) == {"pr_comment", "check_run"}


def test_03_ambiguous_pr_association_never_targets_a_pr(world: World) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head), world.state.pr(13, world.head)]
    jid = world.enqueue()
    world.run()
    r = world.jobrow(jid)["result"]
    assert (r["association"], r["candidates"]) == ("ambiguous", [12, 13])
    assert world.all_prcs() == [] and world.state.count("POST", "prc") == 0
    assert len(world.all_ccs()) == 1 and len(world.state.check_runs) == 1  # D-4: push surfaces


# ---------------------------------------------------------------- 4: duplicates


def test_04_duplicate_delivery_and_reexecution_publish_once(world: World) -> None:
    from tracewise.contracts import WorkflowRunEvent
    from tracewise.web.ingest import ingest_workflow_run

    ev = WorkflowRunEvent.model_validate(
        {
            "action": "completed",
            "installation": {"id": 9},
            "repository": {"id": 7, "full_name": "acme/coffee"},
            "workflow_run": {
                "id": 55,
                "run_attempt": 1,
                "workflow_id": 3,
                "head_sha": world.head,
                "head_branch": "feature",
                "event": "push",
                "status": "completed",
                "conclusion": "failure",
                "repository": {"id": 7, "full_name": "acme/coffee"},
                "head_repository": {"id": 7, "full_name": "acme/coffee"},
            },
        }
    )
    outs = [ingest_workflow_run(world.pool, d, ev).outcome for d in ("x-1", "x-1", "x-2")]
    assert outs == ["enqueued", "duplicate_delivery", "duplicate_run"]
    (jid,) = [r[0] for r in world.owner.execute("SELECT id FROM job").fetchall()]
    world.run()
    # Lost completion → the job runs again: nothing new is written.
    world.owner.execute("UPDATE job SET status='retry_wait', finished_at=NULL, run_after=now() WHERE id=%s", (jid,))
    world.run()
    assert (world.state.count("POST", "cc"), world.state.count("POST", "cr"), world.state.count("PATCH", "cr")) == (1, 1, 0)
    assert world.jobrow(jid)["result"]["publications"] == {"commit_comment": "already_published", "check_run": "unchanged"}


# ---------------------------------------------------------------- 5, 6, 7: retries and reconciliation


def test_05_transient_failure_retries_and_completes(world: World) -> None:
    world.state.fault("POST", "cr", 502)
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    assert j["status"] == "retry_wait" and "GitHubRetryable" in j["last_error"]
    assert world.state.count("POST", "cr") == 0 and world.pubs()["commit_comment"][0] == "published"
    world.ready(jid)
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded"
    assert (world.state.count("POST", "cc"), len(world.all_ccs()), len(world.state.check_runs)) == (1, 1, 1)


@pytest.mark.parametrize("kind", ["cc", "cr"])
def test_06_accepted_then_timeout_is_reconciled_not_duplicated(world: World, kind: str) -> None:
    world.state.fault("POST", kind, "accept_then_timeout")
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "retry_wait"
    assert world.state.count("POST", kind) == 1  # the POST was not repeated inline
    world.ready(jid)
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded"
    assert len(world.all_ccs()) == 1 and len(world.state.check_runs) == 1
    surface = "commit_comment" if kind == "cc" else "check_run"
    assert world.jobrow(jid)["result"]["publications"][surface] == "adopted"
    assert world.pubs()[surface][1] == (world.all_ccs()[0]["id"] if kind == "cc" else world.state.check_runs[0]["id"])


def test_07_crash_between_publication_and_db_persistence(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    real = repo.mark_published
    calls = {"n": 0}

    def flaky(conn, pid, *a, **k):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:  # the check run was created on GitHub; its row cannot be written
            raise DatabaseUnavailable("simulated interruption")
        return real(conn, pid, *a, **k)

    monkeypatch.setattr(repo, "mark_published", flaky)
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "retry_wait" and len(world.state.check_runs) == 1
    assert "check_run" not in world.pubs()  # the reservation and its write rolled back together
    monkeypatch.setattr(repo, "mark_published", real)
    world.ready(jid)
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded"
    assert len(world.state.check_runs) == 1 and world.state.count("POST", "cr") == 1
    assert world.pubs()["check_run"] == ("published", world.state.check_runs[0]["id"])


# ---------------------------------------------------------------- 8: concurrency


def test_08_concurrent_publishers_create_one_check_run(world: World) -> None:
    jid = world.enqueue()
    world.run()  # creates analysis + publications
    world.state.check_runs.clear()
    world.owner.execute("DELETE FROM publication WHERE surface='check_run'")
    analysis_id = world.owner.execute("SELECT id FROM analysis").fetchone()[0]
    real = world.state._create_cr

    def slow(req):  # type: ignore[no-untyped-def]
        time.sleep(0.3)
        return real(req)

    world.state.gh.routes.insert(0, ("POST", __import__("re").compile(r"^/repos/acme/coffee/check-runs$"), slow))
    rc = analyze_mod.RepoClient(world.http, world.tokens, installation_id=9, repo_id=7, full_name="acme/coffee", scope="publish")
    t = PublishTarget(9, 7, "acme/coffee", world.head, 55, 1, 3)
    out = CheckOutput("t", "s", "body")
    results: list[str] = []

    def pub() -> None:
        results.append(Publisher(world.pool, rc, app_id=APP_ID, check_lease=lambda: None).check_run(t, analysis_id, out).state)

    threads = [threading.Thread(target=pub) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(30)
    assert sorted(results) == ["published", "unchanged", "unchanged", "unchanged"]
    assert len(world.state.check_runs) == 1
    assert jid


# ---------------------------------------------------------------- 9, 10: logs and permissions


def test_09_logs_unavailable(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head, log_status=410)
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["result"]["outcome"]) == ("succeeded", "logs_unavailable")
    assert w.all_ccs() == []  # D-8: the write-once commit comment is kept for a completed analysis
    (cr,) = w.state.check_runs
    assert cr["output"]["title"] == "Logs unavailable" and "no longer available" in cr["output"]["text"]
    assert w.provider_calls == 1 and owner.execute("SELECT status FROM analysis").fetchone()[0] == "logs_unavailable"


def test_10_permission_denied_reading_logs_no_retry(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head, log_status=403)
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 1, "permission_denied")
    (cr,) = w.state.check_runs
    assert cr["output"]["title"] == "Missing permission" and w.all_ccs() == []


def test_10b_rel05_no_pull_requests_write_check_run_names_it(world: World) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    world.state.fault("POST", "prc", 403)
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 1
    assert j["result"]["publications"]["pr_comment"] == "unpublished_permission"
    assert world.pubs()["pr_comment"][0] == "unpublished_permission"
    (cr,) = world.state.check_runs
    assert "Pull requests: write" in cr["output"]["text"] and world.all_ccs() == []
    perm = world.owner.execute("SELECT missing_permission FROM publication WHERE surface='pr_comment'").fetchone()[0]
    assert perm == "pull_requests=write"


# ---------------------------------------------------------------- 11, 12, 13: provider and diagnosis outcomes


@pytest.mark.parametrize("pr", [False, True])
def test_11_rel01_provider_timeout_retries_then_could_not_complete(pool, owner, server, tmp_path, head, pr) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head, scripts=[[ProviderTimeout("t")] for _ in range(3)])
    if pr:
        w.state.commit_pulls[head] = [w.state.pr(12, head)]
    jid = w.enqueue()
    for expected in ("retry_wait", "retry_wait", "succeeded"):
        w.run()
        assert w.jobrow(jid)["status"] == expected
        w.ready(jid)
    j = w.jobrow(jid)
    assert j["attempts"] == 3 and j["result"]["outcome"] == "could_not_complete" and w.provider_calls == 3
    assert w.all_ccs() == []  # FS-ERR-1: never a commit comment
    (cr,) = w.state.check_runs
    assert "timed out" in cr["output"]["text"] and cr["conclusion"] == "neutral"
    assert len(w.all_prcs()) == (1 if pr else 0)
    assert owner.execute("SELECT status FROM analysis").fetchone()[0] == "could_not_complete"


def test_12_13_invalid_diagnosis_publishes_explicit_uncertainty(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    unsupported = [
        final(
            root_cause="The README push caused a tax bug.",
            problem_location={"path": "coffee_shop/pricing.py", "line_start": 5, "line_end": 5},
        )
    ]
    w = World(pool, owner, server, tmp_path / "ws", head, scripts=[unsupported])
    jid = w.enqueue()
    w.run()
    assert w.jobrow(jid)["result"]["outcome"] == "inconclusive"
    (cc,) = w.all_ccs()
    (cr,) = w.state.check_runs
    for text in (cc["body"], cr["output"]["text"]):
        assert "README push caused" not in text and "could not determine the root cause" in text
        assert "No fix is suggested" in text and "Suggested fix" not in text
    assert cr["output"]["title"] == "Root cause not determined" and cr["output"]["annotations"] == []


# ---------------------------------------------------------------- 14: rate limiting


def test_14_rate_limit_defers_with_backoff(world: World) -> None:
    world.state.fault("POST", "cc", "rate_limit")
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    delay = world.owner.execute("SELECT extract(epoch FROM run_after - now()) FROM job WHERE id=%s", (jid,)).fetchone()[0]
    assert j["status"] == "retry_wait" and float(delay) >= 59 and world.all_ccs() == []
    world.ready(jid)
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded" and len(world.all_ccs()) == 1


# ---------------------------------------------------------------- 15: lease loss


def test_15_lost_lease_stops_before_any_publication(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    def steal(req):  # type: ignore[no-untyped-def]
        owner.execute("UPDATE job SET locked_by = 'other-worker'")
        time.sleep(0.5)  # heartbeat notices
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), steal]],
    )
    jid = w.enqueue()
    assert w.worker(heartbeat_s=0.05).run_once()
    assert w.state.writes == [] and w.jobrow(jid)["status"] == "running"
    assert owner.execute("SELECT count(*) FROM publication").fetchone()[0] == 0


# ---------------------------------------------------------------- 16: authorisation


def test_16_installation_and_repository_mismatch_never_write(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head)
    with transaction(pool) as c:
        repo.upsert_installation(c, 77, "other")
        repo.upsert_repository(c, 8, 77, "other/repo")
    bad_repo = w.enqueue(repo_id=8, repo="other/repo")  # repo belongs to installation 77
    bad_inst = w.enqueue(installation_id=77)  # job row says 77, payload says 9
    w.run(2)
    for jid in (bad_repo, bad_inst):
        j = w.jobrow(jid)
        assert j["status"] == "dead" and j["last_error"].startswith("permanent")
    owner.execute("UPDATE repository SET enabled = false WHERE id = 7")
    disabled = w.enqueue()
    w.run()
    assert w.jobrow(disabled)["status"] == "cancelled"
    assert w.state.writes == [] and w.provider_calls == 0
    rc = analyze_mod.RepoClient(w.http, w.tokens, installation_id=9, repo_id=7, full_name="acme/coffee", scope="publish")
    for t in (
        PublishTarget(9, 8, "other/repo", head, 55, 1, 3),
        PublishTarget(77, 7, "acme/coffee", head, 55, 1, 3),
        PublishTarget(9, 7, "acme/coffee", "z" * 40, 55, 1, 3),
    ):
        with pytest.raises(ValueError):
            Publisher(pool, rc, app_id=APP_ID, check_lease=lambda: None).check_run(t, 1, CheckOutput("t", "s", "x"))


def test_16b_spoofed_marker_comment_is_not_adopted(world: World) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    world.state.pr_comments[12].append({"id": 5, "body": "<!-- tracewise:pr:wf3 --> fake", "user": {"login": "mallory"}})
    world.enqueue()
    world.run()
    assert world.state.pr_comments[12][0]["id"] == 5 and len(world.state.pr_comments[12]) == 2
    assert world.state.pr_comments[12][0]["body"].endswith("fake")  # never edited


# ---------------------------------------------------------------- 17: updates in place, stale attempts


def test_17_rerun_updates_in_place_and_stale_attempt_cannot_overwrite(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    other = [
        call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41),
        final(root_cause="Second attempt: total() drops the subtotal."),
    ]
    w = World(pool, owner, server, tmp_path / "ws", head, scripts=[known(), other, known()])
    w.state.commit_pulls[head] = [w.state.pr(12, head)]
    w.enqueue(attempt=1)
    w.run()
    first = w.state.pr_comments[12][0]["body"]
    w.enqueue(attempt=2)
    w.run()
    (prc,) = w.state.pr_comments[12]
    (cr,) = w.state.check_runs
    assert prc["body"] != first and "Second attempt" in prc["body"] and "Second attempt" in cr["output"]["text"]
    assert (
        w.state.count("POST", "prc"),
        w.state.count("PATCH", "prc"),
        w.state.count("POST", "cr"),
        w.state.count("PATCH", "cr"),
    ) == (1, 1, 1, 1)
    late = w.enqueue(attempt=1)  # an old attempt finishing late
    w.run()
    assert w.jobrow(late)["result"]["publications"] == {"pr_comment": "stale", "check_run": "stale"}
    assert "Second attempt" in w.state.pr_comments[12][0]["body"] and w.all_ccs() == []


# ---------------------------------------------------------------- 18: DB interruption elsewhere


def test_18_db_interruption_at_analysis_persist_recovers(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    real = repo.upsert_analysis
    monkeypatch.setattr(repo, "upsert_analysis", lambda *a, **k: (_ for _ in ()).throw(DatabaseUnavailable("down")))
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "retry_wait" and world.state.writes == []
    monkeypatch.setattr(repo, "upsert_analysis", real)
    world.ready(jid)
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded"
    assert (len(world.all_ccs()), len(world.state.check_runs)) == (1, 1)


def test_unexpected_bug_is_never_success_and_notifies_on_last_attempt(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise KeyError("programming error")

    monkeypatch.setattr(analyze_mod, "diagnose", boom)
    jid = world.enqueue()
    for _ in range(3):
        world.run()
        world.ready(jid)
    j = world.jobrow(jid)
    assert j["status"] == "dead" and "KeyError" in j["last_error"]
    (cr,) = world.state.check_runs
    assert cr["output"]["title"] == "Could not complete the analysis" and "KeyError" not in cr["output"]["text"]
    assert world.all_ccs() == []


def test_no_personal_token_reaches_github(world: World) -> None:
    world.enqueue()
    world.run()
    for r in world.gh.requests:
        assert "personal-token" not in r.headers.get("authorization", "")


# ---------------------------------------------------------------- AT-PUB-04, AT-PUB-05 (push), AT-PUB-06


def test_pub04_two_workflows_on_one_sha_one_report_each(world: World) -> None:
    doc, _ = api_job(101, "Tests (Python 3.11)", "failure", fixture("pytest_b02.out"))
    world.gh.route("GET", r"^/repos/acme/coffee/actions/runs/56/attempts/\d+/jobs$", jresp(200, {"jobs": [doc]}))
    world.enqueue()
    with transaction(world.pool) as c:
        j = world.job(run_id=56, workflow_id=4, delivery_id="d-56")
        repo.insert_workflow_run(
            c,
            installation_id=9,
            repo_id=7,
            run_id=56,
            attempt=1,
            workflow_id=4,
            head_sha=world.head,
            head_branch="feature",
            head_repo_id=7,
            event="push",
            conclusion="failure",
        )
        queue.enqueue(
            c, kind="analyze", installation_id=9, dedupe_key="analyze:7:56:1", payload=j.model_dump(mode="json"), run_key="7:56"
        )
    world.run(2)
    markers = sorted(b for c in world.all_ccs() for b in ("wf3", "wf4") if f"tracewise:cc:{b}" in c["body"])
    assert markers == ["wf3", "wf4"] and len(world.all_ccs()) == 2
    assert sorted(c["external_id"] for c in world.state.check_runs) == ["55", "56"]


def test_pub05_push_reruns_keep_one_commit_comment_and_update_check_run(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    texts = ["Attempt one cause.", "Attempt two cause.", "Attempt three cause."]
    scripts = [[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), final(root_cause=t)] for t in texts]
    w = World(pool, owner, server, tmp_path / "ws", head, scripts=scripts)
    for attempt in (1, 2, 3):
        w.enqueue(attempt=attempt)
        w.run()
    (cc,) = w.all_ccs()
    (cr,) = w.state.check_runs
    assert "Attempt one cause" in cc["body"]  # write-once: never edited (FS-PUB-1/4)
    assert "Attempt three cause" in cr["output"]["text"]
    assert (w.state.count("POST", "cc"), w.state.count("POST", "cr"), w.state.count("PATCH", "cr")) == (1, 1, 2)


@pytest.mark.parametrize("pr_write", [True, False])
def test_pub06_fork_pr_published_or_unpublished_permission(pool, owner, server, tmp_path, head, pr_write) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head, event="pull_request")
    w.state.head_pulls = [w.state.pr(21, head)]  # found only via /pulls?head=contrib:feature (fork)
    if not pr_write:
        w.state.fault("POST", "prc", 403)
    jid = w.enqueue(head_repo="contrib/coffee", head_repo_id=99)
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded" and j["result"]["association"] == "matched"
    q = next(r for r in w.gh.requests if r.url.path == "/repos/acme/coffee/pulls").url.params
    assert q["head"] == "contrib:feature"
    if pr_write:
        assert len(w.state.pr_comments[21]) == 1 and w.pubs()["pr_comment"][0] == "published"
    else:
        assert w.state.pr_comments[21] == [] and w.pubs()["pr_comment"][0] == "unpublished_permission"
        assert "Pull requests: write" in w.state.check_runs[0]["output"]["text"]
    assert w.all_ccs() == [] and "merge of the pull request" in w.state.check_runs[0]["output"]["text"]


def test_jobs_api_forbidden_publishes_missing_permission_notice_without_retry(world: World) -> None:
    world.gh.routes.insert(
        0,
        (
            "GET",
            __import__("re").compile(r"^/repos/acme/coffee/actions/runs/55/attempts/\d+/jobs$"),
            lambda r: jresp(403, {"message": "Resource not accessible"}, {"x-accepted-github-permissions": "actions=read"}),
        ),
    )
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 1, "permission_denied")
    (cr,) = world.state.check_runs
    assert cr["output"]["title"] == "Missing permission" and "Actions: read" in cr["output"]["text"]
    assert len(world.state.pr_comments[12]) == 1 and world.all_ccs() == [] and world.provider_calls == 0
    assert world.owner.execute("SELECT status FROM analysis").fetchone()[0] == "permission_denied"


def test_t705_background_job_runs_as_the_tenant_role_and_cannot_reach_another_tenant(world: World) -> None:
    """AT-SEC-03 under RLS: the handler's pool is `tracewise_app`; a job of installation 9 naming installation 77's
    repository cannot even see that repository, is refused permanently, and no token is minted for 77."""
    with world.tenant_pool.connection() as c:
        assert c.execute("SELECT current_user AS u").fetchone() == {"u": "tracewise_app"}
    with transaction(world.pool) as c:
        repo.upsert_installation(c, 77, "other")
        repo.upsert_repository(c, 8, 77, "other/repo")
    ok, foreign = world.enqueue(), world.enqueue(repo_id=8, repo="other/repo")
    world.run(2)
    assert world.jobrow(ok)["status"] == "succeeded"
    j = world.jobrow(foreign)
    assert j["status"] == "dead" and j["last_error"].startswith("permanent")
    assert [r.url.path for r in world.gh.requests if r.url.path.startswith("/app/installations/77")] == []
    rows = world.owner.execute("SELECT DISTINCT installation_id FROM analysis UNION SELECT installation_id FROM publication")
    assert {r[0] for r in rows} == {9}
