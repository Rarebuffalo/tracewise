"""T-302 REST client against an in-process fake (no network).

Recorded = real anonymous responses (tests/fixtures/github/recorded). Everything else is synthetic,
shaped after the GitHub REST docs; LIVE behaviour is unverified until Phase 8."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import httpx
import pytest

from tests.github_fake import FakeGitHub, jresp, recorded
from tracewise.github import errors as err
from tracewise.github.client import RepoClient
from tracewise.github.endpoints import ANALYSIS_SCOPE, APP_PERMISSIONS, ENDPOINTS, PUBLISH_SCOPE, covered

SRC = Path(__file__).resolve().parents[2] / "src" / "tracewise"
JOBS = r"^/repos/pallets/flask/actions/runs/37632626982/attempts/1/jobs$"


def setup(scope: str = "analysis", sleeps: list[float] | None = None, **limits):  # type: ignore[no-untyped-def]
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http(sleeps, **limits)
    rc = RepoClient(http, gh.provider(http), installation_id=42, repo_id=7, full_name="pallets/flask", scope=scope)
    return gh, rc


# ---------------------------------------------------------------- AT-SEC-01 (static)


def test_sec01_every_endpoint_is_permitted_and_none_writes_forbidden_resources() -> None:
    for ep in ENDPOINTS.values():
        assert covered(ep.permission, ep.access, APP_PERMISSIONS), ep.name
        assert ep.permission in (None, *APP_PERMISSIONS)
        if ep.method != "GET":
            assert ep.permission in (None, "pull_requests", "checks") or ep.name == "create_commit_comment", ep.name
            assert "/contents" not in ep.path and "/git/" not in ep.path and "/workflows" not in ep.path
            assert not ep.path.startswith("/repos/{owner}/{repo}/issues/{number}") or ep.permission == "pull_requests"
    analysis = [e for e in ENDPOINTS.values() if e.method == "GET" and e.permission in ("actions", "contents")]
    assert all(covered(e.permission, e.access, ANALYSIS_SCOPE) for e in analysis)
    publish = [e for e in ENDPOINTS.values() if e.method != "GET" and e.auth == "installation"]
    assert all(covered(e.permission, e.access, PUBLISH_SCOPE) for e in publish)


def test_sec01_no_http_or_github_urls_outside_the_client() -> None:
    allowed = {SRC / "github" / "client.py"}
    for f in SRC.rglob("*.py"):
        if f in allowed:
            continue
        text = f.read_text()
        tree = ast.parse(text)
        imported = {
            a.name.split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])
        }
        assert not imported & {"httpx", "requests", "urllib3", "aiohttp", "http"}, f
        assert "api.github.com" not in text, f


# ---------------------------------------------------------------- jobs, pagination (recorded fixture)


def test_list_jobs_recorded_response_and_failed_filter() -> None:
    gh, rc = setup()
    gh.route("GET", JOBS, jresp(200, recorded("flask-run-37632626982-jobs.json")))
    jobs = rc.list_jobs(37632626982, 1)
    assert len(jobs) == 12
    failed = rc.failed_jobs(37632626982, 1)
    assert [j["name"] for j in failed] == ["Development Versions"]
    req = gh.calls("GET", JOBS)[0]
    assert req.url.params["per_page"] == "100"
    assert req.headers["authorization"].startswith("Bearer ghs_fake")
    assert req.headers["x-github-api-version"] == "2022-11-28"


def test_pagination_follows_next_only_on_api_host_and_is_capped() -> None:
    gh, rc = setup()
    jobs = recorded("flask-run-37632626982-jobs.json")["jobs"]
    nxt = "https://api.github.com/repos/pallets/flask/actions/runs/37632626982/attempts/1/jobs?per_page=100&page=2"

    def page(req: httpx.Request) -> httpx.Response:
        if req.url.params.get("page") == "2":
            return jresp(200, {"total_count": 12, "jobs": jobs[6:]})
        return jresp(200, {"total_count": 12, "jobs": jobs[:6]}, {"link": f'<{nxt}>; rel="next"'})

    gh.route("GET", JOBS, page)
    assert len(rc.list_jobs(37632626982, 1)) == 12

    gh2, rc2 = setup()
    gh2.route("GET", JOBS, jresp(200, {"jobs": []}, {"link": '<https://evil.example/x>; rel="next"'}))
    with pytest.raises(err.UnsafeRedirect):
        rc2.list_jobs(37632626982, 1)

    gh3, rc3 = setup(max_pages=3)
    gh3.route("GET", JOBS, jresp(200, {"jobs": [{"id": 1}]}, {"link": f'<{nxt}>; rel="next"'}))
    assert len(rc3.list_jobs(37632626982, 1)) == 3


# ---------------------------------------------------------------- logs (FS-LOG-1, AT-LOG-01/03 client half)

LOGS = r"^/repos/pallets/flask/actions/jobs/99/logs$"
BLOB = "https://productionresultssa1.blob.core.windows.net/actions-results/abc/logs.txt?sig=SIGNED&se=2026"


def test_log_redirect_followed_without_token() -> None:
    gh, rc = setup()
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh.route("GET", r"^//productionresultssa1\.blob\.core\.windows\.net/", httpx.Response(200, text="line 1\nline 2\nlast"))
    assert list(rc.job_log_lines(99)) == ["line 1", "line 2", "last"]
    blob_req = gh.requests[-1]
    assert blob_req.url.host.endswith("blob.core.windows.net")
    assert "authorization" not in blob_req.headers  # token never sent to storage


@pytest.mark.parametrize(
    "location",
    [
        "http://productionresultssa1.blob.core.windows.net/x",  # not https
        "https://user:pw@pipelines.actions.githubusercontent.com/x",  # credentials
        "https://evil.example/logs",  # host not allowed
        "https://blob.core.windows.net.evil.example/x",  # suffix trick
        "",
    ],
)
def test_unsafe_log_redirects_refused_and_not_fetched(location) -> None:  # type: ignore[no-untyped-def]
    gh, rc = setup()
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": location}))
    with pytest.raises(err.UnsafeRedirect):
        list(rc.job_log_lines(99))
    assert all(r.url.host == "api.github.com" for r in gh.requests)


@pytest.mark.parametrize(("status", "exc"), [(404, err.NotFound), (410, err.Gone), (403, err.PermissionDenied)])
def test_log_unavailable_statuses(status, exc) -> None:  # type: ignore[no-untyped-def]
    gh, rc = setup()
    gh.route("GET", LOGS, jresp(status, {"message": "x"}))
    with pytest.raises(exc):
        list(rc.job_log_lines(99))


def test_expired_signed_url_is_retryable_and_log_cap() -> None:
    gh, rc = setup()
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh.route("GET", r"^//productionresultssa1", httpx.Response(403, text="AuthenticationFailed"))
    with pytest.raises(err.GitHubRetryable):
        list(rc.job_log_lines(99))
    gh2, rc2 = setup(max_log_bytes=1000)
    gh2.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh2.route("GET", r"^//productionresultssa1", httpx.Response(200, text="x" * 99 + "\n" + "y" * 5000))
    assert list(rc2.job_log_lines(99)) == ["x" * 99]


# ---------------------------------------------------------------- rate limits, retries (FS-ERR-2)


def test_primary_rate_limit_beyond_inline_budget_defers_to_queue() -> None:
    sleeps: list[float] = []
    gh, rc = setup(sleeps=sleeps)
    reset = str(int(gh.now) + 60)
    gh.route(
        "GET",
        JOBS,
        jresp(403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset}),
    )
    with pytest.raises(err.GitHubRetryable) as ei:
        rc.list_jobs(37632626982, 1)
    assert ei.value.retry_after_s is not None and 60 <= ei.value.retry_after_s <= 62
    assert sleeps == []  # not blocking a worker for a minute


def test_short_retry_after_waits_inline_then_succeeds() -> None:
    sleeps: list[float] = []
    gh, rc = setup(sleeps=sleeps)
    gh.route("GET", JOBS, [jresp(429, {"message": "slow down"}, {"retry-after": "2"}), jresp(200, {"jobs": []})])
    assert rc.list_jobs(37632626982, 1) == []
    assert sleeps == [2.0]


def test_secondary_rate_limit_without_headers_waits_at_least_a_minute() -> None:
    gh, rc = setup()
    gh.route("GET", JOBS, jresp(403, {"message": "You have exceeded a secondary rate limit."}))
    with pytest.raises(err.GitHubRetryable) as ei:
        rc.list_jobs(37632626982, 1)
    assert ei.value.retry_after_s == 60


def test_permission_403_is_not_retried_and_names_permission() -> None:
    gh, rc = setup()
    gh.route(
        "GET",
        JOBS,
        jresp(403, {"message": "Resource not accessible by integration"}, {"x-accepted-github-permissions": "actions=read"}),
    )
    with pytest.raises(err.PermissionDenied) as ei:
        rc.list_jobs(37632626982, 1)
    assert ei.value.permission == "actions=read"
    assert len(gh.calls("GET", JOBS)) == 1


def test_5xx_and_transport_errors_retry_with_backoff() -> None:
    sleeps: list[float] = []
    gh, rc = setup(sleeps=sleeps)
    gh.route("GET", JOBS, [jresp(502), jresp(503), jresp(200, {"jobs": [{"id": 1}]})])
    assert rc.list_jobs(37632626982, 1) == [{"id": 1}]
    assert len(sleeps) == 2 and 0.8 <= sleeps[0] <= 1.2 and 1.6 <= sleeps[1] <= 2.4

    gh2, rc2 = setup()
    gh2.route("GET", JOBS, jresp(502))
    with pytest.raises(err.GitHubRetryable):
        rc2.list_jobs(37632626982, 1)
    assert len(gh2.calls("GET", JOBS)) == 4  # 1 + 3 retries

    gh3, rc3 = setup()
    state = {"n": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectTimeout("timeout", request=req)
        return jresp(200, {"jobs": []})

    gh3.route("GET", JOBS, flaky)
    assert rc3.list_jobs(37632626982, 1) == []


def test_rel02_rate_limit_then_502_then_success_across_attempts() -> None:
    """AT-REL-02 client half: attempt 1 defers ≥60 s; attempt 2 rides out a 502. Queue half: test_queue."""
    gh, rc = setup()
    reset = str(int(gh.now) + 60)
    seq = [
        jresp(403, {}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset}),
        jresp(502),
        jresp(200, {"jobs": [{"id": 5, "conclusion": "failure"}]}),
    ]
    gh.route("GET", JOBS, seq)
    with pytest.raises(err.GitHubRetryable) as ei:
        rc.failed_jobs(37632626982, 1)
    assert ei.value.retry_after_s >= 60  # type: ignore[operator]
    gh.now += 61
    assert rc.failed_jobs(37632626982, 1) == [{"id": 5, "conclusion": "failure"}]


# ---------------------------------------------------------------- auth, bounds, binding


def test_401_remints_once_then_gives_up() -> None:
    gh, rc = setup()
    gh.route("GET", JOBS, [jresp(401, {"message": "Bad credentials"}), jresp(200, {"jobs": []})])
    assert rc.list_jobs(37632626982, 1) == []
    assert gh.minted == 2
    gh2, rc2 = setup()
    gh2.route("GET", JOBS, jresp(401, {"message": "Bad credentials"}))
    with pytest.raises(err.InstallationUnavailable):
        rc2.list_jobs(37632626982, 1)
    assert gh2.minted == 2


def test_response_size_cap_and_invalid_json() -> None:
    gh, rc = setup(max_json_bytes=1000)
    gh.route("GET", JOBS, httpx.Response(200, content=b'{"jobs": [' + b" " * 2000 + b"]}"))
    with pytest.raises(err.ResponseTooLarge):
        rc.list_jobs(37632626982, 1)
    gh2, rc2 = setup()
    gh2.route("GET", r"/commits/abc$", httpx.Response(200, content=b"<html>"))
    with pytest.raises(err.GitHubPermanent, match="invalid JSON"):
        rc2.request("get_commit", sha="abc")


def test_client_is_bound_to_one_repository() -> None:
    _, rc = setup()
    with pytest.raises(ValueError, match="bound"):
        rc.request("get_commit", owner="victim", repo="secret", sha="abc")
    for bad in ("../../orgs/x", "/etc/passwd", "a//b", "a\\b", ""):
        with pytest.raises(ValueError, match="contents path"):
            rc.request("get_contents", path=bad)


def test_path_params_are_encoded() -> None:
    gh, rc = setup()
    gh.route("GET", r"/contents/", jresp(200, {"type": "file"}))
    rc.request("get_contents", path="src/my file#1.py", query={"ref": "a" * 40})
    req = gh.calls("GET", r"/contents/")[0]
    assert req.url.raw_path.startswith(b"/repos/pallets/flask/contents/src/my%20file%231.py")


def test_logs_have_no_tokens_or_bodies(caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    gh, rc = setup()
    gh.route("GET", JOBS, jresp(200, recorded("flask-run-37632626982-jobs.json")))
    rc.list_jobs(37632626982, 1)
    raw = caplog.text + json.dumps([str(getattr(r, "tw", "")) for r in caplog.records])
    assert "ghs_fake" not in raw and "Development Versions" not in raw
    assert "list_jobs_for_attempt" in raw


def test_scope_is_enforced_locally_before_any_request() -> None:
    gh, analysis = setup("analysis")
    for name, params in (
        ("create_pr_comment", {"number": 1}),
        ("create_check_run", {}),
        ("update_check_run", {"check_run_id": 1}),
        ("create_commit_comment", {"sha": "a" * 40}),
    ):
        if name == "create_commit_comment":
            continue  # Contents read is in both scopes; commit comments are published with the publish token
        with pytest.raises(ValueError, match="outside the 'analysis' token scope"):
            analysis.request(name, json_body={}, **params)
    _, publish = setup("publish")
    with pytest.raises(ValueError, match="outside the 'publish' token scope"):
        list(publish.job_log_lines(99))
    assert gh.minted == 0 and not gh.requests  # refused before minting or calling
