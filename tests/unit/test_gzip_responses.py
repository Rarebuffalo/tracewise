"""Compressed responses (found in the first live GitHub check, 2026-10-23): httpx asks for `gzip` by default and GitHub
compresses JSON. `GitHubHTTP._send` reads the body decoded (`iter_bytes`) and rebuilt the response with the original
`Content-Encoding` header, so httpx tried to decode plain JSON again and raised `httpx.DecodingError` for every
compressed response. The fakes never compressed, so no test saw it. Every response here is gzip-encoded, like
GitHub's. Offline: in-process transports only."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.github_fake import FakeGitHub, jresp
from tests.unit.test_github_client import BLOB, LOGS, setup
from tracewise.github import errors as err
from tracewise.github.client import AnonymousGitHub, RepoClient
from tracewise.github.endpoints import ENDPOINTS

RUN = r"^/repos/pallets/flask/actions/runs/5$"


def gz(r: httpx.Response, request: httpx.Request | None = None) -> httpx.Response:
    """The same response, gzip-encoded on the wire as GitHub sends it."""
    r.read()
    headers = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "content-encoding")}
    headers["content-encoding"] = "gzip"
    return httpx.Response(r.status_code, headers=headers, content=gzip.compress(r.content), request=request)


def gzip_all(gh: FakeGitHub) -> None:
    """Wrap every registered route (the token mint included) so its response is gzip-encoded."""

    def wrap(h: Callable[[httpx.Request], httpx.Response]) -> Callable[[httpx.Request], httpx.Response]:
        return lambda req: gz(h(req), req)

    gh.routes = [(m, p, wrap(h)) for m, p, h in gh.routes]


def compressed_setup(**limits: Any) -> tuple[FakeGitHub, RepoClient]:
    gh, rc = setup(**limits)
    return gh, rc


def test_compressed_success_including_the_installation_token_mint() -> None:
    gh, rc = setup()
    gh.route("GET", RUN, jresp(200, {"id": 5, "run_attempt": 1}))
    gzip_all(gh)
    assert rc.request("get_run", run_id=5) == {"id": 5, "run_attempt": 1}
    assert gh.minted == 1  # the token request's response was compressed too


def test_the_rebuilt_response_carries_no_stale_content_encoding() -> None:
    gh = FakeGitHub()
    gh.route("GET", RUN, jresp(200, {"id": 5}))
    gzip_all(gh)
    http = gh.http()
    resp = http.call(ENDPOINTS["get_run"], "/repos/pallets/flask/actions/runs/5", "t")
    assert resp.json() == {"id": 5} and "content-encoding" not in resp.headers
    assert resp.headers["content-length"] == str(len(resp.content))


@pytest.mark.parametrize(
    ("status", "headers", "exc"),
    [
        (404, {}, err.NotFound),
        (422, {}, err.GitHubPermanent),
        (401, {}, err.GitHubPermanent),
        (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"}, err.GitHubRetryable),
        (500, {}, err.GitHubRetryable),
    ],
    ids=["404", "422", "401", "403-rate-limit", "500"],
)
def test_compressed_error_bodies_map_to_github_errors_never_a_decoding_error(
    status: int, headers: dict[str, str], exc: type[Exception]
) -> None:
    gh, rc = setup()
    gh.route("GET", RUN, jresp(status, {"message": "nope"}, headers))
    gzip_all(gh)
    with pytest.raises(exc):
        rc.request("get_run", run_id=5)


def test_compressed_pagination_follows_link_headers() -> None:
    gh, rc = setup()
    nxt = '<https://api.github.com/repos/pallets/flask/actions/runs?page=2>; rel="next"'
    gh.route(
        "GET",
        r"^/repos/pallets/flask/actions/runs$",
        lambda req: (
            jresp(200, {"workflow_runs": [{"id": 2}]})
            if req.url.params.get("page") == "2"
            else jresp(200, {"workflow_runs": [{"id": 1}]}, {"link": nxt})
        ),
    )
    gzip_all(gh)
    assert [r["id"] for r in rc.paginate_limited("list_workflow_runs", "workflow_runs", 10)] == [1, 2]


def test_a_small_compressed_body_that_expands_past_the_cap_is_refused() -> None:
    gh, rc = setup(max_json_bytes=4096)
    bomb = {"pad": "0" * 1_000_000}  # ~1 MB decoded, ~1 KB on the wire: the cap applies to the decoded size
    gh.route("GET", RUN, jresp(200, bomb))
    gzip_all(gh)
    with pytest.raises(err.ResponseTooLarge):
        rc.request("get_run", run_id=5)


def test_compressed_log_download_is_decoded_line_by_line() -> None:
    gh, rc = setup()
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh.route("GET", r"^//productionresultssa1\.blob\.core\.windows\.net/", httpx.Response(200, text="line 1\nline 2\nlast"))
    gzip_all(gh)
    assert list(rc.job_log_lines(99)) == ["line 1", "line 2", "last"]


def test_the_anonymous_client_reads_compressed_json() -> None:
    gh = AnonymousGitHub(httpx.Client(transport=httpx.MockTransport(lambda r: gz(httpx.Response(200, json={"id": 1}), r))))
    assert gh.get("get_run", repo="pallets/flask", run_id=1) == {"id": 1}


def test_the_model_adapter_reads_compressed_responses() -> None:
    from tests.investigate.factory import answer
    from tests.investigate.test_http_adapter import Server, provider, req, wire_doc

    s = Server(gz(httpx.Response(200, json=wire_doc(answer(category="ok")))))
    p, _ = provider(s)
    assert json.loads(p.step(req()).text or "")["category"] == "ok"


def test_a_retry_after_a_compressed_5xx_resends_the_original_request_headers() -> None:
    """Rebuilding the response must never touch the request headers reused by the retry loop."""
    gh, rc = setup()
    gh.route("GET", RUN, [jresp(502, {"message": "bad gateway"}, {"x-github-request-id": "R1"}), jresp(200, {"id": 5})])
    gzip_all(gh)
    assert rc.request("get_run", run_id=5) == {"id": 5}
    first, second = [r for r in gh.requests if r.url.path.endswith("/runs/5")]
    for name in ("authorization", "accept", "x-github-api-version", "user-agent"):
        assert second.headers.get(name) == first.headers.get(name), name
    assert second.headers["authorization"].startswith("Bearer ") and "x-github-request-id" not in second.headers
    assert "content-encoding" not in second.headers
