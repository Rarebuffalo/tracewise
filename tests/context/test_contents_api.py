"""T-304 Contents-API fallback and provider failover (fake GitHub transport + local git server; offline)."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

import httpx
import pytest

from tests.context.conftest import make_fetcher
from tests.github_fake import FakeGitHub, jresp
from tracewise.context.contents_api import ContentsApiSource
from tracewise.context.provider import open_code_context
from tracewise.context.source import Limits, ReadStatus
from tracewise.github import errors as gh_err
from tracewise.github.auth import REFRESH_MARGIN_S
from tracewise.github.client import RepoClient

SHA = "c0ffee" + "0" * 34


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data, usedforsecurity=False).hexdigest()


FILES: dict[str, bytes] = {"src/app.py": b"x = 1\n", "big.txt": b"y" * 2_000_000}


def tree_doc(truncated: bool = False) -> dict[str, Any]:
    tree = [{"path": p, "mode": "100644", "type": "blob", "sha": blob_sha(d), "size": len(d)} for p, d in FILES.items()]
    tree += [
        {"path": "src", "mode": "040000", "type": "tree", "sha": "d" * 40},
        {"path": "link", "mode": "120000", "type": "blob", "sha": blob_sha(b"src/app.py"), "size": 10},
        {"path": "evil", "mode": "120000", "type": "blob", "sha": blob_sha(b"/etc/passwd"), "size": 11},
        {"path": "vendor/lib", "mode": "160000", "type": "commit", "sha": "e" * 40},
        {"path": "../escape", "mode": "100644", "type": "blob", "sha": "f" * 40, "size": 1},
    ]
    return {"sha": SHA, "tree": tree, "truncated": truncated}


def contents(path: str, data: bytes, sha: str | None = None) -> dict[str, Any]:
    return {
        "type": "file",
        "path": path,
        "encoding": "base64",
        "size": len(data),
        "sha": sha or blob_sha(data),
        "content": base64.b64encode(data).decode(),
    }


def setup(scope: str = "analysis") -> tuple[FakeGitHub, RepoClient]:
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http()
    rc = RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name="acme/app", scope=scope)
    gh.route("GET", rf"^/repos/acme/app/git/trees/{SHA}$", jresp(200, tree_doc()))
    gh.route(
        "GET",
        r"^/repos/acme/app/contents/src/app.py$",
        lambda r: jresp(200, contents("src/app.py", FILES["src/app.py"])) if r.url.params.get("ref") == SHA else jresp(404),
    )
    for target in (b"src/app.py", b"/etc/passwd"):
        gh.route(
            "GET",
            rf"^/repos/acme/app/git/blobs/{blob_sha(target)}$",
            jresp(
                200,
                {
                    "sha": blob_sha(target),
                    "encoding": "base64",
                    "size": len(target),
                    "content": base64.b64encode(target).decode(),
                },
            ),
        )
    return gh, rc


def test_reads_at_exact_sha_with_same_rules() -> None:
    gh, rc = setup()
    src = ContentsApiSource(rc, SHA)
    assert "../escape" not in src.entries() and "src" not in src.entries()  # unsafe names dropped; dirs implicit
    r = src.read("src/app.py")
    assert (r.status, r.text) == (ReadStatus.ok, "x = 1\n")
    assert gh.calls("GET", r"/contents/src/app.py$")[0].url.params["ref"] == SHA
    n = len(gh.requests)
    assert src.read("big.txt").status is ReadStatus.too_large and len(gh.requests) == n  # never requested
    assert src.read("link").path == "src/app.py"
    assert src.read("evil").status is ReadStatus.symlink_escapes
    assert src.read("vendor/lib").status is ReadStatus.submodule
    assert src.read("../escape").status is ReadStatus.invalid_path


def test_blob_sha_mismatch_rejected() -> None:
    gh, rc = setup()
    gh.routes.insert(
        0,
        (
            "GET",
            __import__("re").compile(r"^/repos/acme/app/contents/src/app.py$"),
            lambda r: jresp(200, contents("src/app.py", b"tampered\n", sha=blob_sha(FILES["src/app.py"]))),
        ),
    )
    assert ContentsApiSource(rc, SHA).read("src/app.py").status is ReadStatus.unavailable


def test_truncated_tree_flagged() -> None:
    gh, rc = setup()
    gh.routes.insert(
        0, ("GET", __import__("re").compile(rf"^/repos/acme/app/git/trees/{SHA}$"), lambda r: jresp(200, tree_doc(True)))
    )
    src = ContentsApiSource(rc, SHA)
    src.entries()
    assert src.tree_truncated


def test_provider_falls_back_when_git_fails(ws_root, server) -> None:  # type: ignore[no-untyped-def]
    _gh, rc = setup()
    fetcher = make_fetcher(server, ws_root)  # repo acme/app does not exist on the local git server → fetch fails
    with open_code_context(rc, SHA, fetcher=fetcher) as src:
        assert src.kind == "contents_api" and src.read("src/app.py").status is ReadStatus.ok
    assert not any(ws_root.iterdir())


def test_provider_unavailable_when_both_fail(ws_root, server) -> None:  # type: ignore[no-untyped-def]
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http()
    rc = RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name="acme/app", scope="analysis")
    gh.route("GET", r"/git/trees/", jresp(403, {"message": "Resource not accessible by integration"}))
    with open_code_context(rc, SHA, fetcher=make_fetcher(server, ws_root)) as src:
        assert not src.available and src.kind == "unavailable"
        assert src.read("src/app.py").status is ReadStatus.unavailable
        assert "contents API: PermissionDenied" in src.reason  # type: ignore[attr-defined]
    with open_code_context(rc, "not-a-sha", fetcher=None) as src2:
        assert not src2.available


TOKENS = __import__("re").compile(r"^/app/installations/\d+/access_tokens$")


@pytest.mark.parametrize("with_git", [True, False])
def test_provider_propagates_an_app_authentication_failure(ws_root, server, with_git: bool) -> None:  # type: ignore[no-untyped-def]
    """A 401 on the mint (App JWT rejected) is an operator fault for the job to report, never "context unavailable"."""
    gh, rc = setup()
    gh.routes.insert(0, ("POST", TOKENS, lambda r: jresp(401, {"message": "Bad credentials"})))
    with (
        pytest.raises(gh_err.AppAuthenticationFailed),
        open_code_context(rc, SHA, fetcher=make_fetcher(server, ws_root) if with_git else None),
    ):
        pass
    assert not gh.calls("GET", r"/git/trees/") and not (ws_root.exists() and any(ws_root.iterdir()))


def test_provider_propagates_an_app_authentication_failure_on_a_mid_job_token_refresh(ws_root, server) -> None:  # type: ignore[no-untyped-def]
    """The analysis token was minted earlier in the job (cached); it reaches its refresh point before the context
    step, and the re-mint is refused with 401 (for example the key was deleted meanwhile)."""
    gh, rc = setup()
    rc.git_fetch_token()  # minted and cached, as by the job's first GitHub call
    gh.now += gh.token_ttl_s - REFRESH_MARGIN_S + 1
    gh.routes.insert(0, ("POST", TOKENS, lambda r: jresp(401, {"message": "Bad credentials"})))
    with pytest.raises(gh_err.AppAuthenticationFailed), open_code_context(rc, SHA, fetcher=make_fetcher(server, ws_root)):
        pass
    assert len(gh.calls("POST", r"/access_tokens$")) == 2


def test_provider_still_falls_back_when_the_installation_refuses_the_mint(ws_root, server) -> None:  # type: ignore[no-untyped-def]
    """Unchanged: an ordinary permanent refusal (404, InstallationUnavailable) still gives an unavailable source."""
    gh, rc = setup()
    gh.routes.insert(0, ("POST", TOKENS, lambda r: jresp(404, {"message": "Not Found"})))
    with open_code_context(rc, SHA, fetcher=make_fetcher(server, ws_root)) as src:
        assert not src.available and "contents API: InstallationUnavailable" in src.reason  # type: ignore[attr-defined]


def test_provider_prefers_git_and_propagates_caller_errors(ws_root, server) -> None:  # type: ignore[no-untyped-def]
    head = server.make_repo("acme", "gitok", {"a.py": "print(1)\n"})
    gh = FakeGitHub()
    gh.token_ttl_s = 3600
    http = gh.http()

    class _Tok:  # the local git server accepts its own generated token
        def token(self, *a: object) -> Any:
            return type("T", (), {"value": server.token})()

        def invalidate(self, *a: object) -> None: ...

    rc = RepoClient(http, _Tok(), installation_id=1, repo_id=7, full_name="acme/gitok", scope="analysis")
    with open_code_context(rc, head, fetcher=make_fetcher(server, ws_root)) as src:
        assert src.kind == "git" and src.read("a.py").text == "print(1)\n"
    assert not gh.requests  # no API calls when git works
    with pytest.raises(LookupError), open_code_context(rc, head, fetcher=make_fetcher(server, ws_root)):
        raise LookupError("caller failure")
    assert not any(ws_root.iterdir())


def test_publish_scope_cannot_fetch_code() -> None:
    _, rc = setup("publish")
    with pytest.raises(ValueError, match="analysis-scope"):
        rc.git_fetch_token()


def test_aggregate_budget_applies_to_api_source() -> None:
    _, rc = setup()
    src = ContentsApiSource(rc, SHA, Limits(max_total_read_bytes=3, validation_read_bytes=1))
    assert src.read("src/app.py").status is ReadStatus.budget_exhausted


# ------------------------------------------------------------------ I-3 / D-A / D-B: read errors by class


def _contents_route(gh: FakeGitHub, handler) -> None:  # type: ignore[no-untyped-def]
    gh.routes.insert(0, ("GET", re.compile(r"^/repos/acme/app/contents/src/app.py$"), handler))


@pytest.mark.parametrize(
    "resp",
    [lambda r: jresp(422, {"message": "Unprocessable"}), lambda r: httpx.Response(200, content=b"{not json")],
    ids=["422", "invalid-json"],
)
def test_a_permanent_error_on_one_file_is_that_file_unreadable_not_a_dead_job(resp) -> None:  # type: ignore[no-untyped-def]
    """D-A: it used to raise out of the tool call and end the whole job `dead` with no notice. D-C: its own status,
    `read_failed`, distinct from absence (`not_found`) and from a transient failure; one request, no retry."""
    gh, rc = setup()
    _contents_route(gh, resp)
    src = ContentsApiSource(rc, SHA)
    r = src.read("src/app.py")
    assert r.status is ReadStatus.read_failed and src.skipped["src/app.py"] is ReadStatus.read_failed
    assert len(gh.calls("GET", r"/contents/src/app.py$")) == 1 and not src.transient_failure


def test_a_transient_failure_is_retried_in_place_then_reported_as_temporary() -> None:
    gh, rc = setup()
    _contents_route(gh, lambda r: jresp(502, {"message": "Bad gateway"}))
    src = ContentsApiSource(rc, SHA)
    sleeps: list[float] = []
    src._sleep = sleeps.append
    r = src.read("src/app.py", purpose="validation")
    assert r.status is ReadStatus.temporarily_unavailable and sleeps == [1.0]  # TRANSIENT_READ_TRIES = 2
    assert len(gh.calls("GET", r"/contents/src/app.py$")) == 2 * 4  # each try: one request + 3 client retries
    assert src.skipped["src/app.py"] is ReadStatus.temporarily_unavailable


def test_a_transient_failure_that_clears_reads_normally() -> None:
    gh, rc = setup()
    n = {"calls": 0}

    def flaky(r):  # type: ignore[no-untyped-def]
        n["calls"] += 1
        if n["calls"] <= 4:  # the client's inline retries are used up once: one source-level retry follows
            return jresp(503, {"message": "unavailable"})
        return jresp(200, contents("src/app.py", FILES["src/app.py"]))

    _contents_route(gh, flaky)
    src = ContentsApiSource(rc, SHA)
    src._sleep = lambda s: None
    assert src.read("src/app.py").status is ReadStatus.ok and "src/app.py" not in src.skipped


def test_transient_retries_stop_at_the_attempt_deadline() -> None:
    gh, rc = setup()
    _contents_route(gh, lambda r: jresp(502, {"message": "Bad gateway"}))
    src = ContentsApiSource(rc, SHA)
    src.time_left = lambda: 0.5  # less than the 1 s pause: no second try
    src._sleep = lambda s: (_ for _ in ()).throw(AssertionError("slept past the deadline"))
    assert src.read("src/app.py").status is ReadStatus.temporarily_unavailable
    assert len(gh.calls("GET", r"/contents/src/app.py$")) == 4


def test_a_token_scope_failure_is_not_mistaken_for_a_missing_file(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Credential-level faults concern the whole source, not one file: they still propagate."""
    _, rc = setup()
    src = ContentsApiSource(rc, SHA)
    src.entries()

    def refuse(*a, **kw):  # type: ignore[no-untyped-def]
        raise gh_err.TokenScopeError("token repositories differ")

    monkeypatch.setattr(rc, "request", refuse)
    with pytest.raises(gh_err.TokenScopeError):
        src.read("src/app.py")
