"""O-2: every GitHub request made for an attempt respects the attempt's remaining time. Offline: fake transport, a
scripted budget (fake clock), recorded sleeps. Nothing is sent once the budget is spent."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.github_fake import FakeGitHub, jresp
from tracewise.github import errors as err
from tracewise.github.client import MIN_REQUEST_S, RepoClient

CONTENTS = r"^/repos/acme/app/contents/a\.py$"


class Budget:
    """Remaining seconds; `drain` is subtracted on every look (a fake monotonic clock that advances per check)."""

    def __init__(self, left: float, drain: float = 0.0) -> None:
        self.left, self.drain, self.looks = left, drain, 0

    def remaining(self) -> float:
        self.looks += 1
        v = self.left
        self.left = max(0.0, self.left - self.drain)
        return v


def setup(left: float | None, *, drain: float = 0.0, **limits: Any) -> tuple[FakeGitHub, RepoClient, list[float], Budget | None]:
    gh = FakeGitHub()
    gh.add_token_route()
    sleeps: list[float] = []
    http = gh.http(sleeps, **limits)
    b = Budget(left, drain) if left is not None else None
    rc = RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name="acme/app", scope="analysis", deadline=b)
    return gh, rc, sleeps, b


def get(rc: RepoClient) -> Any:
    return rc.request("get_contents", path="a.py", query={"ref": "a" * 40})


def test_no_request_and_no_token_mint_starts_without_enough_time() -> None:
    gh, rc, _, _ = setup(MIN_REQUEST_S - 0.1)
    gh.route("GET", CONTENTS, jresp(200, {}))
    with pytest.raises(err.DeadlineExhausted) as info:
        get(rc)
    assert info.value.sent is False and gh.requests == []  # neither the mint nor the read reached the transport
    assert isinstance(info.value, err.GitHubRetryable)  # the existing transient paths handle it


def test_timeouts_are_cut_to_the_remaining_budget() -> None:
    gh, rc, _, _ = setup(7.5)
    seen: list[dict[str, Any]] = []

    def capture(req: httpx.Request) -> httpx.Response:
        seen.append(req.extensions["timeout"])
        return jresp(200, {"type": "file"})

    gh.route("GET", CONTENTS, capture)
    get(rc)
    (t,) = seen
    assert t["read"] == 7.5 and t["connect"] == 5.0  # read cut from 30 s; connect already below the budget


def test_without_a_budget_the_client_limits_apply_unchanged() -> None:
    gh, rc, _, _ = setup(None)
    seen: list[dict[str, Any]] = []
    gh.route("GET", CONTENTS, lambda req: seen.append(req.extensions["timeout"]) or jresp(200, {}))
    get(rc)
    assert seen[0]["read"] == 30.0


def test_an_inline_retry_happens_only_if_it_ends_with_time_to_spare() -> None:
    gh, rc, sleeps, _ = setup(100.0)
    gh.route("GET", CONTENTS, [jresp(502), jresp(200, {})])
    get(rc)
    assert len(sleeps) == 1  # plenty of time: the usual backoff and retry
    gh, rc, sleeps, _ = setup(MIN_REQUEST_S + 0.5)
    gh.route("GET", CONTENTS, [jresp(502), jresp(200, {})])
    with pytest.raises(err.GitHubRetryable, match="no time left"):
        get(rc)
    assert sleeps == [] and len(gh.calls("GET", CONTENTS)) == 1  # no wait, no second request


def test_a_rate_limit_wait_longer_than_the_budget_is_not_slept() -> None:
    gh, rc, sleeps, _ = setup(8.0)
    gh.route("GET", CONTENTS, [jresp(429, {"message": "slow down"}, {"retry-after": "7"}), jresp(200, {})])
    with pytest.raises(err.GitHubRetryable) as info:
        get(rc)
    assert sleeps == [] and info.value.retry_after_s == 7.0  # the job queue waits instead


def test_a_retry_that_finds_the_budget_spent_reports_that_a_try_was_sent() -> None:
    gh, rc, _sleeps, b = setup(100.0)
    gh.route("GET", CONTENTS, [jresp(502), jresp(200, {})])
    assert b is not None
    real_sleep = rc.http._sleep

    def sleep_spends_budget(s: float) -> None:
        real_sleep(s)
        b.left = 0.0

    rc.http._sleep = sleep_spends_budget
    with pytest.raises(err.DeadlineExhausted) as info:
        get(rc)
    assert info.value.sent is True and len(gh.calls("GET", CONTENTS)) == 1


def test_a_body_still_arriving_at_the_deadline_is_abandoned() -> None:
    gh, rc, sleeps, _b = setup(50.0, drain=25.0)  # each look at the clock costs 25 s: the budget ends mid-request
    gh.route("GET", CONTENTS, jresp(200, {"type": "file"}))
    with pytest.raises(err.GitHubRetryable):
        get(rc)
    assert sleeps == []


def test_writes_are_never_repeated_inline_and_a_cut_write_stays_uncertain() -> None:
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http([])
    b = Budget(50.0, drain=20.0)
    rc = RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name="acme/app", scope="publish", deadline=b)
    gh.route("POST", r"/check-runs$", jresp(201, {"id": 5}))
    with pytest.raises(err.GitHubRetryable) as info:  # the request went out; its response did not arrive in time
        rc.request("create_check_run", json_body={"name": "Tracewise", "head_sha": "a" * 40})
    assert not isinstance(info.value, err.DeadlineExhausted)  # a transport-style failure: the publisher reconciles
    assert len(gh.calls("POST", r"/check-runs$")) == 1


def test_the_log_stream_inherits_the_budget_of_the_request_that_obtained_its_url() -> None:
    gh, rc, _, _ = setup(9.0)
    url = "https://productionresultssa1.blob.core.windows.net/logs/1.txt"
    gh.route("GET", r"/actions/jobs/1/logs$", httpx.Response(302, headers={"location": url}))
    seen: list[dict[str, Any]] = []
    gh.route(
        "GET",
        r"^//productionresultssa1\.blob\.core\.windows\.net/logs/1\.txt$",
        lambda req: seen.append(req.extensions["timeout"]) or httpx.Response(200, text="a\nb\n"),
    )
    assert list(rc.job_log_lines(1)) == ["a", "b"]
    assert seen[0]["read"] == 9.0


def test_repository_reads_with_no_time_left_give_a_transient_unavailable_source_without_requests() -> None:
    from tracewise.context.provider import open_code_context

    gh, rc, _, _ = setup(0.5)
    with open_code_context(rc, "c0ffee" + "0" * 34, fetcher=None) as src:
        assert not src.available and src.transient_failure  # source_unavailable: retried or "could not complete"
    assert gh.requests == []
