"""D-C: tool errors are classified, never all "invalid arguments"; I-3: repeated transient failures end as an
explicit `source_unavailable`, never as a verdict on the repository or on the model's answer. Offline."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from tests.context.memsource import MemSource
from tests.github_fake import FakeGitHub, jresp
from tests.investigate.factory import B02_ANSWER, B02_FILES, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.context.provider import open_code_context
from tracewise.context.source import PermanentReadError, ReadStatus, TransientReadError, TreeEntry, UnavailableSource
from tracewise.context.tools import CATEGORY, ToolBox, ToolInternalError, ToolResult
from tracewise.contracts import Status
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.loop import InvestigationLimits, investigate
from tracewise.investigate.validate import SOURCE_UNAVAILABLE

PRICING = "coffee_shop/pricing.py"
ABSTAIN = {**B02_ANSWER, "category": "unknown", "problem_location": None, "fix": None}


class Broken(MemSource):
    """`raise_on_read`: what `_read_blob` raises for every file (None: reads work)."""

    def __init__(self, files: dict[str, Any], exc: BaseException | None = None) -> None:
        super().__init__(files)
        self.exc, self.blob_calls = exc, 0
        self._sleep = lambda s: None

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        self.blob_calls += 1
        if self.exc is not None:
            raise self.exc
        return super()._read_blob(entry)


def events(caplog: Any, name: str) -> list[dict[str, Any]]:
    return [r.tw for r in caplog.records if isinstance(getattr(r, "tw", None), dict) and r.tw.get("event") == name]


# ------------------------------------------------------------------ the taxonomy, one category each


@pytest.mark.parametrize(
    ("tool_name", "args", "status"),
    [
        ("read_file", {"path": PRICING, "colour": "red"}, "invalid_args"),  # unexpected argument
        ("read_file", {}, "invalid_args"),  # missing argument
        ("read_file", {"path": PRICING, "start": 0}, "invalid_args"),
        ("grep", {"pattern": "("}, "invalid_pattern"),
        ("read_file", {"path": PRICING, "start": 9999}, "beyond_eof"),
    ],
)
def test_malformed_arguments_are_correctable_invalid_arguments(tool_name, args, status, caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.INFO)
    r = ToolBox(MemSource(B02_FILES)).call(tool_name, args)
    assert (r.ok, r.status, r.category) == (False, status, "invalid_arguments")
    assert [(e["tool"], e["category"]) for e in events(caplog, "tool.error")] == [(tool_name, "invalid_arguments")]


def test_an_unknown_tool_is_unsupported() -> None:
    r = ToolBox(MemSource(B02_FILES)).call("write_file", {"path": "x"})
    assert (r.status, r.category) == ("unknown_tool", "unsupported")


@pytest.mark.parametrize(
    ("tool_name", "args", "status"),
    [
        ("read_file", {"path": "coffee_shop/missing.py"}, "not_found"),
        ("read_file", {"path": "coffee_shop"}, "is_directory"),
        ("list_dir", {"path": "nowhere"}, "not_found"),
    ],
)
def test_valid_arguments_naming_a_missing_resource_are_unavailable(tool_name, args, status) -> None:  # type: ignore[no-untyped-def]
    r = ToolBox(MemSource(B02_FILES)).call(tool_name, args)
    assert (r.status, r.category) == (status, "unavailable")


def test_a_transient_github_failure_is_retried_boundedly_then_reported_as_transient() -> None:
    src = Broken(B02_FILES, TransientReadError("502"))
    r = ToolBox(src).call("read_file", {"path": PRICING})
    assert (r.status, r.category) == ("temporarily_unavailable", "transient")
    assert src.blob_calls == 2 and src.transient_failure  # TRANSIENT_READ_TRIES; the source remembers it


def test_a_transient_error_escaping_a_tool_is_transient_not_internal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    box = ToolBox(MemSource(B02_FILES))
    monkeypatch.setattr(box.source, "entries", lambda: (_ for _ in ()).throw(gh_err.GitHubRetryable("tree 502")))
    assert box.call("list_dir", {}).category == "transient"


def test_a_permanent_github_failure_is_an_external_error_and_is_not_retried() -> None:
    src = Broken(B02_FILES, PermanentReadError("422"))
    r = ToolBox(src).call("read_file", {"path": PRICING})
    assert (r.status, r.category) == ("read_failed", "external_error")
    assert src.blob_calls == 1 and not src.transient_failure


@pytest.mark.parametrize(
    "path", ["../etc/passwd", ".git/config", "/etc/passwd", "up"], ids=["traversal", "git-dir", "absolute", "symlink"]
)
def test_security_policy_rejections_fail_closed(path: str) -> None:
    src = MemSource(B02_FILES, symlinks={"up": "../../secret"})
    r = ToolBox(src).call("read_file", {"path": path})
    assert not r.ok and r.category == "security_policy" and "secret" not in r.content
    assert src.skipped.get("up") in (None, ReadStatus.symlink_escapes)


@pytest.mark.parametrize("exc", [TypeError("bug: NoneType"), KeyError("k"), ZeroDivisionError()])
def test_an_unexpected_exception_inside_a_tool_is_an_internal_error_never_invalid_arguments(exc, caplog) -> None:  # type: ignore[no-untyped-def]
    """D-C: before, a TypeError raised anywhere inside a tool was answered `invalid arguments` to the model."""
    caplog.set_level(logging.INFO)
    box = ToolBox(Broken(B02_FILES, exc))
    with pytest.raises(ToolInternalError) as info:
        box.call("read_file", {"path": PRICING})
    assert "NoneType" not in str(info.value) and info.value.__cause__ is None  # no exception text, no chained content
    (ev,) = events(caplog, "tool.internal_error")
    assert ev["tool"] == "read_file" and ev["error_type"] == type(exc).__name__
    assert ev["where"].startswith("test_tool_errors.py:") and ev["where"].endswith(":_read_blob")
    assert events(caplog, "tool.error") == []  # never logged as an argument error either


def test_credential_faults_inside_a_tool_propagate_to_the_job() -> None:
    box = ToolBox(Broken(B02_FILES, gh_err.AppAuthenticationFailed("401")))
    with pytest.raises(gh_err.AppAuthenticationFailed):
        box.call("read_file", {"path": PRICING})


def test_an_unserialisable_tool_result_is_an_internal_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    box = ToolBox(MemSource(B02_FILES), diff_text="diff")
    monkeypatch.setattr(box, "_get_diff", lambda: (ToolResult(True, b"raw bytes"), None))  # type: ignore[arg-type]
    with pytest.raises(ToolInternalError, match="invalid result"):
        box.call("get_diff", {})


def test_every_status_a_tool_can_return_has_a_category() -> None:
    statuses = {s.value for s in ReadStatus if s is not ReadStatus.ok} | {
        "invalid_args",
        "invalid_pattern",
        "beyond_eof",
        "unknown_tool",
        "timeout",
        "grep_failed",
    }
    assert statuses <= set(CATEGORY)


# ------------------------------------------------------------------ inside the investigation


def test_an_internal_tool_error_ends_the_investigation_and_never_yields_a_diagnosis() -> None:
    src = Broken(B02_FILES, TypeError("bug"))
    p = ScriptedProvider([tool("read_file", path=PRICING, start=30, end=41), answer(**B02_ANSWER)])
    with pytest.raises(ToolInternalError):
        diagnose(evidence(source=src), p)
    assert len(p.requests) == 1  # the model was not asked again with a misleading "invalid arguments"


def test_the_model_sees_the_category_specific_message_and_can_correct_its_arguments() -> None:
    p = ScriptedProvider(
        [tool("read_file", path=PRICING, start=0), tool("read_file", "c2", path=PRICING, start=30, end=41), answer(**B02_ANSWER)]
    )
    d = diagnose(evidence(source=MemSource(B02_FILES)), p).diagnosis
    assert d.status is Status.diagnosed
    seen = [m.content for m in p.requests[1].messages if m.role == "tool"]
    assert len(seen) == 1 and "start/end must be positive integers" in seen[0]


def test_deadline_exhaustion_during_tool_calls_is_a_budget_outcome() -> None:
    t = [0.0]

    def clock() -> float:
        t[0] += 50.0  # each look at the clock costs 50 s of a 120 s investigation
        return t[0]

    p = ScriptedProvider([tool("read_file", path=PRICING), tool("list_dir", "c2"), answer(**B02_ANSWER)])
    res = investigate(evidence(source=MemSource(B02_FILES)), p, InvestigationLimits(), clock=clock)
    assert res.outcome == "budget_exhausted" and res.draft is None


def test_a_short_deadline_stops_transient_retries_without_waiting() -> None:
    src = Broken(B02_FILES, TransientReadError("502"))
    slept: list[float] = []
    src._sleep = slept.append
    src.time_left = lambda: 0.5  # less than the 1 s pause
    assert ToolBox(src).call("read_file", {"path": PRICING}).status == "temporarily_unavailable"
    assert slept == [] and src.blob_calls == 1


# ------------------------------------------------------------------ I-3: source unavailable, never a verdict


def test_collection_a_transiently_unreachable_source_skips_the_model_and_says_source_unavailable(  # type: ignore[no-untyped-def]
    caplog,
) -> None:
    caplog.set_level(logging.INFO)
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http(sleeps=[])
    rc = RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name="acme/app", scope="analysis")
    gh.route("GET", r"/git/trees/", jresp(502, {"message": "Bad gateway"}))
    with open_code_context(rc, "c0ffee" + "0" * 34, fetcher=None) as src:
        assert not src.available and src.transient_failure
    assert [e["stage"] for e in events(caplog, "context.source_unavailable")] == ["collect"]

    p = ScriptedProvider([answer(**B02_ANSWER)])
    d = diagnose(evidence(source=UnavailableSource("a" * 40, "contents API: GitHubRetryable", transient=True)), p).diagnosis
    assert (d.status, d.inconclusive_reason) == (Status.inconclusive, SOURCE_UNAVAILABLE)
    assert p.requests == []  # no model call on a bundle known to be incomplete


def test_collection_a_permanently_unavailable_source_is_unchanged() -> None:
    p = ScriptedProvider([answer(**ABSTAIN)])
    d = diagnose(evidence(source=UnavailableSource("a" * 40, "contents API: PermissionDenied")), p).diagnosis
    assert d.inconclusive_reason == "model_abstained" and len(p.requests) == 1


def test_tools_an_inconclusive_answer_after_transient_read_failures_is_source_unavailable() -> None:
    src = Broken(B02_FILES, TransientReadError("502"))
    p = ScriptedProvider([tool("read_file", path=PRICING), answer(**ABSTAIN)])
    d = diagnose(evidence(source=src), p).diagnosis
    assert (d.status, d.inconclusive_reason) == (Status.inconclusive, SOURCE_UNAVAILABLE)  # not "model_abstained"
    assert "inconclusive_before:model_abstained" in d.validation_flags and PRICING in d.limits.files_skipped


def test_tools_a_validated_diagnosis_stands_despite_an_earlier_transient_failure() -> None:
    src = Broken(B02_FILES, None)
    calls = [0]
    real = src._read_blob

    def first_read_fails(entry: TreeEntry) -> bytes | None:
        calls[0] += 1
        if entry.path == "README.md":
            raise TransientReadError("502")
        return real(entry)

    src._read_blob = first_read_fails  # type: ignore[method-assign]
    script = [tool("read_file", path="README.md"), tool("read_file", "c2", path=PRICING, start=30, end=41), answer(**B02_ANSWER)]
    d = diagnose(evidence(source=src), ScriptedProvider(script)).diagnosis
    assert d.status is Status.diagnosed and d.problem_location is not None  # the evidence it needed was read
    assert "README.md" in d.limits.files_skipped


def test_tools_a_permanent_read_failure_is_not_source_unavailable() -> None:
    src = Broken(B02_FILES, PermanentReadError("422"))
    d = diagnose(evidence(source=src), ScriptedProvider([tool("read_file", path=PRICING), answer(**ABSTAIN)])).diagnosis
    assert d.inconclusive_reason == "model_abstained"
