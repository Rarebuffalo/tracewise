"""T-604 META runner and AT-SEC-14 anonymous access. Offline: in-process transports and recorded responses only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tracewise.bench import meta
from tracewise.github import errors as err
from tracewise.github.client import AnonymousGitHub

REC = Path(__file__).resolve().parents[1] / "fixtures" / "github" / "recorded"


def anon(handler: Any) -> tuple[AnonymousGitHub, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    return AnonymousGitHub(httpx.Client(transport=httpx.MockTransport(h))), seen


def test_at_sec_14_requests_are_anonymous_even_with_tokens_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_" + "y" * 36)
    gh, seen = anon(lambda r: httpx.Response(200, json={"sha": "a" * 40}))
    gh.get("get_commit", repo="pallets/flask", sha="a" * 40)
    (req,) = seen
    assert "authorization" not in req.headers and req.url.host == "api.github.com" and req.method == "GET"
    assert gh.requests == ["/repos/pallets/flask/commits/" + "a" * 40]


@pytest.mark.parametrize(
    "call",
    [
        lambda g: g.get("create_check_run", repo="a/b"),
        lambda g: g.get("get_commit", repo="../../etc", sha="a" * 40),
        lambda g: g.get("get_commit", repo="a/b", sha="HEAD"),
        lambda g: g.get("get_run", repo="a/b", run_id=-1),
        lambda g: g.get("get_run", repo="a/b", run_id=True),
    ],
    ids=["write-endpoint", "bad-repo", "bad-sha", "negative-id", "bool-id"],
)
def test_only_the_allowed_public_reads_with_validated_parameters(call: Any) -> None:
    gh, seen = anon(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        call(gh)
    assert seen == []  # refused before any request


@pytest.mark.parametrize(
    ("response", "exc"),
    [
        (httpx.Response(404, json={"message": "Not Found"}), err.NotFound),
        (httpx.Response(403, json={"message": "rate"}, headers={"x-ratelimit-remaining": "0"}), err.GitHubRetryable),
        (httpx.Response(502, text="bad gateway"), err.GitHubRetryable),
        (httpx.Response(401, json={}), err.GitHubPermanent),
        (httpx.Response(200, json=[1, 2]), err.GitHubPermanent),
        (httpx.Response(200, content=b"{not json"), err.GitHubPermanent),
        (httpx.Response(200, content=b"[" * 200_000 + b"]" * 200_000), err.GitHubPermanent),
    ],
    ids=["404", "rate-limited", "5xx", "401", "array", "invalid-json", "deep-nesting"],
)
def test_errors_are_mapped_like_the_authenticated_client(response: httpx.Response, exc: type[Exception]) -> None:
    gh, _ = anon(lambda r: response)
    with pytest.raises(exc):
        gh.get("get_run", repo="pallets/flask", run_id=1)


def test_transport_errors_and_oversized_responses() -> None:
    def broken(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=req)

    gh, _ = anon(broken)
    with pytest.raises(err.GitHubRetryable):
        gh.get("get_run", repo="pallets/flask", run_id=1)
    big = AnonymousGitHub(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"{" + b" " * 5000 + b"}"))),
        max_json_bytes=1024,
    )
    with pytest.raises(err.ResponseTooLarge):
        big.get("get_run", repo="pallets/flask", run_id=1)


# ------------------------------------------------------------------ the runner (synthetic recorded directories)

CUR01, EARLY, MID, GREEN = 37632626982, 34252544596, 37632508911, 31965051447
CUR02, NEXT = 37633292268, 37633458715
DEV = ("Development Versions", "Run uv run --locked --no-default-groups --group dev tox run")


def lane_run_doc(rid: int, conclusion: str, minute: int, sha: str = "c" * 40) -> dict[str, Any]:
    return {
        "id": rid,
        "workflow_id": meta.TESTS_WORKFLOW,
        "run_attempt": 1,
        "event": "push",
        "head_branch": "main",
        "head_sha": sha,
        "conclusion": conclusion,
        "created_at": f"2026-10-07T13:{minute:02d}:00Z",
        "head_repository": {"id": 596892},
        "repository": {"id": 596892},
    }


def jobs_doc(*failing: tuple[str, str], attempt: int = 1, passing: tuple[str, ...] = ("typing",)) -> dict[str, Any]:
    jobs = [
        {
            "id": i,
            "name": j,
            "conclusion": "failure",
            "run_attempt": attempt,
            "steps": [{"name": s, "number": 1, "conclusion": "failure"}],
        }
        for i, (j, s) in enumerate(failing)
    ]
    jobs += [
        {"id": 100 + i, "name": n, "conclusion": "success", "run_attempt": attempt, "steps": []} for i, n in enumerate(passing)
    ]
    return {"total_count": len(jobs), "jobs": jobs}


def world(tmp_path: Path, **over: Any) -> Path:
    """A recorded directory shaped like the 2026-10-17 fetch: the lane, four job lists and the commit."""
    files: dict[str, Any] = {
        "flask-tests-main-runs.json": {
            "total_count": 6,
            "workflow_runs": [
                lane_run_doc(NEXT, "success", 59),
                lane_run_doc(CUR02, "failure", 58),
                lane_run_doc(CUR01, "failure", 57),
                lane_run_doc(MID, "failure", 56),
                lane_run_doc(EARLY, "failure", 10),
                lane_run_doc(GREEN, "success", 1),
            ],
        },
        "flask-run-34252544596-jobs.json": jobs_doc(DEV),
        "flask-run-37633292268-jobs.json": jobs_doc(("typing", "Run tox run -e typing"), passing=("Development Versions",)),
        "flask-run-37632626982-jobs.json": json.loads((REC / "flask-run-37632626982-jobs.json").read_text()),
        "flask-commit-d73fa1cdcb.json": json.loads((REC / "flask-commit-d73fa1cdcb.json").read_text()),
    }
    files.update(over)
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name, doc in files.items():
        if doc is not None:
            (tmp_path / name).write_text(doc if isinstance(doc, str) else json.dumps(doc))
    return tmp_path


def results(root: Path) -> dict[str, meta.MetaResult]:
    return {r.case: r for r in meta.run(meta.RecordedSource(root))}


def test_all_cases_evaluate_from_a_complete_recording_with_provenance(tmp_path: Path) -> None:
    res = results(world(tmp_path))
    assert {c: r.status for c, r in res.items()} == {"P-01": "pass", "P-02": "pass", "P-03": "pass"}
    assert str(EARLY) in res["P-01"].label  # the earlier run is derived from the lane, not copied from the truth
    assert "first fails here" in res["P-02"].label and str(NEXT) in res["P-02"].label
    docs = res["P-01"].provenance["documents"]
    assert [d["operation"] for d in docs] == ["list_lane_runs", "list_jobs_for_attempt", "list_jobs_for_attempt"]
    assert docs[2]["endpoint"] == f"/repos/pallets/flask/actions/runs/{EARLY}/jobs?per_page=100"
    assert res["P-01"].provenance["anonymous"] is True and res["P-01"].provenance["source"] == "recorded"


def test_p01_fails_when_the_first_red_failed_differently(tmp_path: Path) -> None:
    res = results(world(tmp_path, **{"flask-run-34252544596-jobs.json": jobs_doc(("Lint", "ruff"))}))
    assert res["P-01"].status == "fail" and "not pre-existing" in res["P-01"].label


def test_p01_fails_when_this_run_starts_the_streak(tmp_path: Path) -> None:
    runs = {"total_count": 2, "workflow_runs": [lane_run_doc(CUR01, "failure", 57), lane_run_doc(GREEN, "success", 1)]}
    res = results(world(tmp_path, **{"flask-tests-main-runs.json": runs}))
    assert res["P-01"].status == "fail"


def test_p02_fails_when_the_job_already_failed_or_the_next_run_is_red(tmp_path: Path) -> None:
    already = jobs_doc(DEV, ("typing", "Run tox run -e typing"), passing=())
    assert results(world(tmp_path / "a", **{"flask-run-37632626982-jobs.json": already}))["P-02"].status == "fail"
    runs = json.loads((world(tmp_path / "b") / "flask-tests-main-runs.json").read_text())
    runs["workflow_runs"][0]["conclusion"] = "failure"
    res = results(world(tmp_path / "c", **{"flask-tests-main-runs.json": runs}))
    assert res["P-02"].status == "fail" and "is failure" in res["P-02"].label


def test_missing_documents_are_missing_evidence_never_a_pass(tmp_path: Path) -> None:
    res = results(world(tmp_path, **{"flask-run-34252544596-jobs.json": None, "flask-tests-main-runs.json": None}))
    assert res["P-01"].status == "missing_evidence" and "flask-tests-main-runs.json" in (res["P-01"].requires or "")
    assert res["P-02"].status == "missing_evidence" and res["P-03"].status == "pass"
    only_lane = results(world(tmp_path / "x", **{"flask-run-34252544596-jobs.json": None}))
    assert only_lane["P-01"].status == "missing_evidence" and "flask-run-34252544596" in (only_lane["P-01"].requires or "")


def test_a_run_outside_the_recorded_window_is_missing_evidence(tmp_path: Path) -> None:
    runs = {"total_count": 1, "workflow_runs": [lane_run_doc(GREEN, "success", 1)]}
    res = results(world(tmp_path, **{"flask-tests-main-runs.json": runs}))
    assert res["P-01"].status == res["P-02"].status == "missing_evidence"


@pytest.mark.parametrize(
    ("over", "case"),
    [
        ({"flask-tests-main-runs.json": "{not json"}, "P-01"),
        ({"flask-tests-main-runs.json": [1, 2]}, "P-01"),
        ({"flask-run-34252544596-jobs.json": jobs_doc(DEV, attempt=2)}, "P-01"),  # recorded for another attempt
        ({"flask-run-34252544596-jobs.json": {"jobs": [{"name": 5}]}}, "P-01"),
        ({"flask-commit-d73fa1cdcb.json": {"sha": "e" * 40, "parents": [{"sha": "f" * 40}]}}, "P-03"),  # another commit
        ({"flask-commit-d73fa1cdcb.json": {"parents": "x"}}, "P-03"),
    ],
    ids=["invalid-json", "list-not-object", "other-attempt", "bad-job", "unexpected-sha", "bad-parents"],
)
def test_malformed_or_contradicting_recordings_are_errors(tmp_path: Path, over: dict[str, Any], case: str) -> None:
    assert results(world(tmp_path, **over))[case].status == "error"


def test_the_index_accepts_only_plain_file_names() -> None:
    for bad in ("../x.json", "/etc/passwd", "a/b.json", "x.txt"):
        with pytest.raises(ValueError):
            meta.RecordedSource(Path("."), [{"name": "get_commit", "params": {}, "file": bad}])


def test_live_source_never_fetches_outside_the_allowlist() -> None:
    commit = json.loads((REC / "flask-commit-d73fa1cdcb.json").read_text())
    gh, seen = anon(lambda r: httpx.Response(200, json=commit))
    res = {r.case: r for r in meta.run(meta.AnonymousSource(gh))}
    assert res["P-01"].status == res["P-02"].status == "missing_evidence"
    assert "allowlist" in (res["P-01"].requires or "")
    assert res["P-03"].status == "pass" and [r.url.path for r in seen] == [
        "/repos/pallets/flask/commits/" + meta.RECORDED_INDEX[0]["params"]["sha"]
    ]
    assert res["P-03"].provenance["documents"][0]["endpoint"] == seen[0].url.path


def test_report_is_separate_and_counts_every_status(tmp_path: Path) -> None:
    doc = meta.report(meta.run(meta.RecordedSource(world(tmp_path, **{"flask-tests-main-runs.json": None}))))
    assert doc["summary"] == {"pass": 1, "fail": 0, "missing_evidence": 2, "error": 0}
    assert "never merged" in doc["track"] and len(doc["results"]) == 3


def test_cli_meta_reads_in_place_and_writes_only_the_requested_output(tmp_path: Path) -> None:
    from tracewise.bench.__main__ import main

    root = world(tmp_path / "rec")
    before = sorted(p.name for p in root.iterdir())
    out = tmp_path / "meta.json"
    assert main(["meta", "--recorded", str(root), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["summary"]["pass"] == 3
    assert sorted(p.name for p in root.iterdir()) == before
