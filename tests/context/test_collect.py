"""T-307 evidence collection end to end, OFFLINE: fake GitHub API (jobs, log redirect + blob, commit,
compare) + local git http-backend (code). Not a LIVE test: GitHub's real behaviour is gated (Phase 8)."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.context.conftest import make_fetcher
from tests.github_fake import FakeGitHub, jresp
from tests.helpers import build_job, fixture
from tracewise.analysis.collect import collect_evidence
from tracewise.context.trigger import relevance
from tracewise.contracts import AnalysisJob
from tracewise.github.client import RepoClient

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "gen_python_fixtures.py")
assert _spec and _spec.loader
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
PRICING, TESTS = _gen.PRICING, _gen.TESTS
C0 = "0" * 40
BLOB = "https://productionresultssa1.blob.core.windows.net/logs/{job}.txt?sig=x"


@pytest.fixture(scope="module")
def head(server) -> str:  # type: ignore[no-untyped-def]
    return server.make_repo(
        "acme", "coffee", {"coffee_shop/__init__.py": "", "coffee_shop/pricing.py": PRICING, "tests/test_pricing.py": TESTS}
    )


def api_job(job_id: int, name: str, conclusion: str, out: str) -> tuple[dict[str, Any], list[str]]:
    info, lines = build_job(job_id, name, "Run pytest", "pytest --tb=short -v", out)
    doc = info.model_dump(mode="json")
    doc["conclusion"] = conclusion
    return doc, lines


def setup(
    server,
    head: str,
    *,
    log_status: dict[int, int] | None = None,
    blob_status: int = 200,  # type: ignore[no-untyped-def]
    jobs: list[tuple[dict[str, Any], list[str]]] | None = None,
) -> tuple[FakeGitHub, RepoClient, AnalysisJob]:
    gh = FakeGitHub()
    gh.add_token_route()
    gh.next_tokens = [server.token]  # the analysis token the local git server accepts
    jobs = (
        jobs
        if jobs is not None
        else [api_job(101, "Tests (Python 3.11)", "failure", fixture("pytest_b02.out")), api_job(102, "lint", "success", "ok")]
    )
    gh.route("GET", r"^/repos/acme/coffee/actions/runs/55/attempts/1/jobs$", jresp(200, {"jobs": [d for d, _ in jobs]}))
    for doc, lines in jobs:
        jid = doc["id"]
        st = (log_status or {}).get(jid, 302)
        gh.route(
            "GET",
            rf"^/repos/acme/coffee/actions/jobs/{jid}/logs$",
            httpx.Response(302, headers={"location": BLOB.format(job=jid)}) if st == 302 else jresp(st, {"message": "x"}),
        )
        gh.route(
            "GET",
            rf"^//productionresultssa1\.blob\.core\.windows\.net/logs/{jid}\.txt$",
            httpx.Response(blob_status, text="\n".join(lines)),
        )
    gh.route("GET", rf"^/repos/acme/coffee/commits/{head}$", jresp(200, {"sha": head, "parents": [{"sha": C0}]}))
    gh.route(
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
                        "patch": "@@ -41 +41 @@",
                    }
                ],
            },
        ),
    )
    http = gh.http()
    rc = RepoClient(http, gh.provider(http), installation_id=9, repo_id=7, full_name="acme/coffee", scope="analysis")
    job = AnalysisJob(
        installation_id=9,
        repo_id=7,
        repo="acme/coffee",
        run_id=55,
        attempt=1,
        workflow_id=3,
        head_sha=head,
        event="push",
        conclusion="failure",
        delivery_id="d-1",
    )
    return gh, rc, job


def test_b02_end_to_end_evidence(server, ws_root, head, caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    gh, rc, job = setup(server, head)
    with collect_evidence(job, rc, fetcher=make_fetcher(server, ws_root)) as ev:
        assert ev.status == "ok" and [j.id for j in ev.failed_jobs] == [101]
        assert ev.prepass is not None
        (g,) = ev.prepass.primaries
        assert len(g.members) - 1 == 3 and g.primary.test == "tests/test_pricing.py::test_total_single"
        assert (ev.prepass.failed[0].step, ev.prepass.failed[0].command) == ("Run pytest", "pytest --tb=short -v")
        assert ev.trigger.known and ev.trigger.changed_paths() == {"coffee_shop/pricing.py"}
        assert ev.source.kind == "git" and ev.source.head_sha == head
        r = ev.tools.call("read_file", {"path": "coffee_shop/pricing.py", "start": 41, "end": 41})
        assert r.ok and "subtotal_ * TAX_RATE" in r.content
        assert "coffee_shop/pricing.py" in ev.tools.call("get_diff", {}).content
        assert ev.tools.files_examined() == [{"path": "coffee_shop/pricing.py", "start": 41, "end": 41}]
        # Pre-pass alone implicates only the test file; the diagnosis location must be added (T-403).
        assert ev.implicated_paths == {"tests/test_pricing.py"}
        assert relevance(ev.trigger, ev.implicated_paths | {"coffee_shop/pricing.py"}).touches_implicated is True
    # AT-LOG-01: only the failed job's log was requested; the token never reached the blob host.
    assert [r.url.path for r in gh.calls("GET", r"/actions/jobs/\d+/logs$")] == ["/repos/acme/coffee/actions/jobs/101/logs"]
    assert all("authorization" not in r.headers for r in gh.requests if r.url.host != "api.github.com")
    assert not any(ws_root.iterdir())  # workspace gone after the block
    assert server.token not in caplog.text


@pytest.mark.parametrize(
    ("log_status", "blob_status", "status"),
    [
        ({101: 410}, 200, "logs_unavailable"),
        ({101: 404}, 200, "logs_unavailable"),
        ({}, 404, "logs_unavailable"),
        ({101: 403}, 200, "permission_denied"),
    ],
)
def test_log03_unavailable_and_permission(server, ws_root, head, log_status, blob_status, status) -> None:  # type: ignore[no-untyped-def]
    _, rc, job = setup(server, head, log_status=log_status, blob_status=blob_status)
    with collect_evidence(job, rc, fetcher=make_fetcher(server, ws_root)) as ev:
        assert ev.status == status and ev.prepass is None  # never a guessed cause
        assert ev.trigger.known and ev.source.available  # metadata and code are still collected
        if status == "permission_denied":
            assert ev.missing_permission


def test_partial_logs_still_ok_and_job_cap(server, ws_root, head) -> None:  # type: ignore[no-untyped-def]
    jobs = [api_job(200 + i, f"t{i}", "failure", fixture("pytest_b02.out")) for i in range(3)]
    _, rc, job = setup(server, head, log_status={201: 410}, jobs=jobs)
    with collect_evidence(job, rc, fetcher=make_fetcher(server, ws_root), max_jobs=2) as ev:
        assert ev.status == "ok" and ev.logs_missing == [201] and ev.jobs_not_downloaded == [202]
        assert ev.log_truncated


def test_no_failed_jobs_and_scope_guard(server, ws_root, head) -> None:  # type: ignore[no-untyped-def]
    _, rc, job = setup(server, head, jobs=[api_job(5, "ok", "success", "fine")])
    with collect_evidence(job, rc, fetcher=None) as ev:
        assert ev.status == "no_failed_jobs" and ev.prepass is None
    gh = FakeGitHub()
    http = gh.http()
    pub = RepoClient(http, gh.provider(http), installation_id=9, repo_id=7, full_name="acme/coffee", scope="publish")
    with pytest.raises(ValueError, match="analysis-scope"), collect_evidence(job, pub, fetcher=None):
        pass
    other = RepoClient(http, gh.provider(http), installation_id=9, repo_id=8, full_name="acme/other", scope="analysis")
    with pytest.raises(ValueError), collect_evidence(job, other, fetcher=None):
        pass
