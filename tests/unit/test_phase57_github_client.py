"""Phase 57: GitHub client defects found by an offline audit, reproduced first.

1. A connection cut while READING a response body (after the status and headers arrived) escaped as a raw httpx
   error instead of GitHubRetryable. A GET was then not retried inline, and in the worker it reached the generic
   handler, which bypassed the partial-publication guard (see tests/db/test_phase57_body_cut.py).
3. Job items from the jobs API that are not objects, or lack required fields, raised AttributeError/ValidationError
   (retryable) instead of a permanent GitHub error.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.unit.test_github_client import JOBS, setup
from tracewise.analysis.collect import collect_evidence
from tracewise.contracts import AnalysisJob
from tracewise.github import errors as err


class CutBody(httpx.SyncByteStream):
    def __iter__(self) -> Any:
        yield b'{"jobs"'
        raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")


def test_a_get_whose_body_is_cut_is_retried_inline_then_retryable() -> None:
    gh, rc = setup(sleeps=[])
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=CutBody())

    gh.route("GET", JOBS, handler)
    with pytest.raises(err.GitHubRetryable):
        rc.list_jobs(37632626982, 1)
    assert calls["n"] == 4  # the first try plus max_retries inline retries, exactly as for a cut before the headers


def test_a_get_whose_body_is_cut_once_then_succeeds() -> None:
    gh, rc = setup(sleeps=[])
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, stream=CutBody())
        return httpx.Response(200, json={"total_count": 0, "jobs": []})

    gh.route("GET", JOBS, handler)
    assert rc.list_jobs(37632626982, 1) == [] and calls["n"] == 2


def test_a_post_whose_body_is_cut_is_never_repeated_inline() -> None:
    gh, rc = setup(scope="publish", sleeps=[])
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(201, stream=CutBody())

    gh.route("POST", r"^/repos/pallets/flask/check-runs$", handler)
    with pytest.raises(err.GitHubRetryable):
        rc.request("create_check_run", json_body={"name": "x", "head_sha": "a" * 40})
    assert calls["n"] == 1  # it may have been applied: the publisher reconciles on the next attempt


@pytest.mark.parametrize(
    "items",
    [[5], [{"id": 1, "conclusion": "failure"}], [{"id": "x", "name": "n", "conclusion": "failure"}], ["job"]],
    ids=["number", "missing-name", "id-not-int", "string"],
)
def test_malformed_job_items_are_a_permanent_github_error(items: list[Any]) -> None:
    gh, rc = setup()
    gh.route("GET", JOBS, httpx.Response(200, json={"total_count": len(items), "jobs": items}))
    job = AnalysisJob.model_validate(
        {
            "installation_id": 42,
            "repo_id": 7,
            "repo": "pallets/flask",
            "run_id": 37632626982,
            "attempt": 1,
            "head_sha": "a" * 40,
            "event": "push",
            "conclusion": "failure",
            "delivery_id": "d-1",
        }
    )
    with pytest.raises(err.GitHubPermanent), collect_evidence(job, rc, fetcher=None):
        pass
