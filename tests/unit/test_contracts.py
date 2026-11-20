"""Diagnosis v2 schema rules (T-103). AT-DX-12 schema half: band + >=1 basis always."""

import pytest
from pydantic import ValidationError

from tracewise.contracts import AnalysisJob, Diagnosis, RepoRef, WorkflowRunEvent

SHA = "a" * 40
RUN = {"repo_id": 1, "repo": "o/r", "run_id": 2, "attempt": 1, "head_sha": SHA, "event": "push"}


def diag(**kw: object) -> Diagnosis:
    base: dict[str, object] = {"run": RUN, "status": "diagnosed", "confidence": {"band": "medium", "basis": ["x"]}}
    base.update(kw)
    return Diagnosis.model_validate(base)


def test_confidence_needs_basis() -> None:
    with pytest.raises(ValidationError):
        diag(confidence={"band": "low", "basis": []})


def test_inconclusive_shape() -> None:
    with pytest.raises(ValidationError):
        diag(status="inconclusive")  # no next steps
    d = diag(
        status="inconclusive", next_steps=["Re-run with debug logging"], confidence={"band": "low", "basis": ["no error line"]}
    )
    assert d.fix is None
    with pytest.raises(ValidationError):
        diag(status="inconclusive", next_steps=["x"], confidence={"band": "high", "basis": ["x"]})


def test_fix_rules() -> None:
    fix = {
        "description": "Multiply by (1 + TAX_RATE)",
        "size": "trivial",
        "replacement": {
            "path": "coffee_shop/pricing.py",
            "line_start": 41,
            "line_end": 41,
            "new_text": "    return round(subtotal_ * (1 + TAX_RATE), 2)",
        },
    }
    assert diag(category="code_regression", fix=fix).fix is not None
    with pytest.raises(ValidationError):
        diag(category="dependency", fix=fix)  # non-code category
    with pytest.raises(ValidationError):
        diag(category="code_regression", fix=fix, confidence={"band": "low", "basis": ["x"]})
    big = {**fix, "replacement": {**fix["replacement"], "line_end": 61}}  # type: ignore[dict-item]
    with pytest.raises(ValidationError):
        diag(category="code_regression", fix=big)


def test_paths_and_limits() -> None:
    for bad in ("/etc/passwd", "../x", "a/../../b"):
        with pytest.raises(ValidationError):
            diag(problem_location={"path": bad, "line_start": 1, "line_end": 1})
    with pytest.raises(ValidationError):
        diag(root_cause="x" * 301)
    with pytest.raises(ValidationError):
        diag(next_steps=["a", "b", "c", "d"])
    with pytest.raises(ValidationError):
        diag(
            primary_errors=[{"log_ref": {"job_id": 1, "line_start": 1, "line_end": 1}, "excerpt": "e", "fingerprint": "0" * 16}]
            * 4
        )
    with pytest.raises(ValidationError):
        diag(surprise=1)


def _event(conclusion: str, action: str = "completed", head_repo_id: int = 1) -> WorkflowRunEvent:
    return WorkflowRunEvent.model_validate(
        {
            "action": action,
            "installation": {"id": 9},
            "repository": {"id": 1, "full_name": "o/r"},
            "workflow_run": {
                "id": 5,
                "run_attempt": 2,
                "head_sha": SHA,
                "head_branch": "feat",
                "event": "pull_request",
                "status": "completed",
                "conclusion": conclusion,
                "repository": {"id": 1, "full_name": "o/r"},
                "head_repository": {"id": head_repo_id, "full_name": "fork/r"},
                "pull_requests": [],
            },
        }
    )


def test_event_filter_and_job_payload() -> None:
    for c in ("failure", "timed_out"):
        assert _event(c).should_analyse()
    for c in ("success", "cancelled", "skipped", "neutral", "action_required", "stale", "startup_failure"):
        assert not _event(c).should_analyse()
    assert not _event("failure", action="requested").should_analyse()
    job = AnalysisJob.from_event(_event("failure", head_repo_id=77), "d-1")
    assert (job.run_id, job.attempt, job.installation_id, job.conclusion) == (5, 2, 9, "failure")
    assert _event("failure", head_repo_id=77).is_fork and not _event("failure").is_fork
    with pytest.raises(ValueError):
        AnalysisJob.from_event(_event("success"), "d-2")


@pytest.mark.parametrize("bad", ["../evil", "acme", "acme/app/extra", "-acme/app", "acme/a b", "acme/" + "x" * 101, ""])
def test_workflow_run_repository_names_are_shape_checked(bad: str) -> None:
    """M-9: webhook repository names reach URLs, git and logs; only GitHub's `owner/repo` shape is accepted (the same
    pattern the lifecycle events already enforced)."""
    from pydantic import ValidationError

    from tracewise.contracts import HeadRepoRef, RepoRef

    for model in (RepoRef, HeadRepoRef):
        with pytest.raises(ValidationError):
            model(id=1, full_name=bad)
    assert RepoRef(id=1, full_name="pallets/flask.git-mirror_2").full_name == "pallets/flask.git-mirror_2"


@pytest.mark.parametrize(
    "name",
    [
        "octocat/hello-world",
        "a/b",
        "x" * 39 + "/r",  # the 39-character owner limit
        "legacy--name-/r",  # legacy accounts may have dashes anywhere after the first character
        "mona-cat_octo/repo",  # Enterprise Managed User: <name>_<shortcode>
        "a" * 30 + "_abcdefgh/r",  # 39 characters including the underscore and an 8-character shortcode
        "m_abc/r",  # 3-character shortcode
    ],
)
def test_standard_and_enterprise_managed_owner_names_are_accepted(name: str) -> None:
    """4B: GitHub docs (username considerations for external authentication, retrieved 2026-11-01): managed user
    names are `<normalized name>_<shortcode>`, shortcode 3-8 alphanumerics, 39 characters at most in total. Such users
    may install an app requesting no organization permissions on a repository they administer (Tracewise's are
    repository-only). The same rule applies to the webhook contracts and to the git/contents path checks."""
    from tracewise.context.paths import validate_owner_repo

    assert RepoRef(id=1, full_name=name).full_name == name
    assert validate_owner_repo(name) == tuple(name.split("/"))


@pytest.mark.parametrize(
    "name",
    [
        "a_b/r",  # shortcode too short
        "mona_abcdefghi/r",  # shortcode too long
        "mona_cat_octo/r",  # one underscore only
        "a" * 31 + "_abcdefgh/r",  # 40 characters with the suffix
        "x" * 40 + "/r",
        "_abc/r",
        "-a/r",
        "a__abc/r",
        "mona_oct-o/r",  # the shortcode has no special characters
        "a/b/c",
        "a b/r",
        "a:r",
        "a/",
        "../r",
    ],
)
def test_malformed_owner_names_and_references_are_refused(name: str) -> None:
    from pydantic import ValidationError

    from tracewise.context.paths import UnsafePath, validate_owner_repo

    with pytest.raises(ValidationError):
        RepoRef(id=1, full_name=name)
    with pytest.raises(UnsafePath):
        validate_owner_repo(name)
