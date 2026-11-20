"""Product acceptance of the rendered report for each outcome a developer can receive (MVP: GitHub-native output).
Deterministic: scripted providers, fixture repositories. These check what the report SAYS and does not claim; model
quality itself is a real-model evaluation (BENCHMARK, live stage I), never proven here."""

from __future__ import annotations

from typing import Any

import pytest

from tests.context.memsource import MemSource
from tests.investigate.factory import B02_ANSWER, B02_FILES, answer, evidence, tool
from tracewise.analysis.attempt import AttemptDeadline
from tracewise.analysis.diagnose import diagnose
from tracewise.context.source import TransientReadError, TreeEntry
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.provider import ProviderError
from tracewise.report.render import check_output, render, render_could_not_complete

CAUSE = "Likely root cause"
READ = tool("read_file", path="coffee_shop/pricing.py", start=30, end=41)


class _Outage(MemSource):
    def __init__(self) -> None:
        super().__init__(B02_FILES)
        self._sleep = lambda s: None

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        raise TransientReadError("502")


def _no_time() -> AttemptDeadline:
    return AttemptDeadline(0.0, clock=lambda: 0.0)


def _boom(req: Any) -> Any:
    raise ProviderError("synthetic outage")


CASES: dict[str, tuple[Any, list[Any], dict[str, Any]]] = {
    "diagnosed": (None, [READ, answer(**B02_ANSWER)], {}),
    "abstained": (None, [READ, answer(**{**B02_ANSWER, "category": "unknown", "problem_location": None, "fix": None})], {}),
    "source_unavailable": (
        _Outage,
        [READ, answer(**{**B02_ANSWER, "category": "unknown", "problem_location": None, "fix": None})],
        {},
    ),
    "provider_unavailable": (None, [_boom], {}),
    "deadline_exhausted": (None, [], {"deadline": "none"}),
}


def report(case: str) -> tuple[Any, str]:
    src_cls, script, kw = CASES[case]
    ev = evidence(source=src_cls()) if src_cls else evidence()
    args: dict[str, Any] = {"deadline": _no_time()} if kw.get("deadline") else {}
    vd = diagnose(ev, ScriptedProvider(script), **args)
    return vd, render(vd)


def test_a_diagnosis_names_the_failure_cause_location_fix_and_confidence() -> None:
    vd, text = report("diagnosed")
    assert CAUSE in text and "coffee_shop/pricing.py" in text and "41" in text
    assert "(1 + TAX_RATE)" in text  # the corrective action is concrete, not "re-run CI" or "check the logs"
    out = check_output(vd, text)
    assert "confidence" in out.title and out.annotations and out.annotations[0]["path"] == "coffee_shop/pricing.py"


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("abstained", "the evidence was not sufficient to name a cause"),
        ("source_unavailable", "the repository's code could not be read"),
        ("provider_unavailable", "the AI investigation could not be completed"),
        ("deadline_exhausted", "the analysis ran out of time"),
    ],
)
def test_every_non_diagnosis_says_why_and_never_claims_a_cause(case: str, reason: str) -> None:
    vd, text = report(case)
    assert CAUSE not in text and "could not determine the root cause" in text
    assert reason in text.replace("\\'", "'").replace("&#x27;", "'")
    assert vd.diagnosis.fix is None and vd.diagnosis.root_cause is None
    out = check_output(vd, text)
    assert out.annotations == () and "Root cause not determined" in out.title


@pytest.mark.parametrize("case", list(CASES))
def test_reports_stay_bounded_and_never_dump_a_whole_log(case: str) -> None:
    _, text = report(case)
    assert len(text) <= 60_000 and text.count("\n") < 200
    assert "Traceback (most recent call last)" not in text  # excerpts are short and redacted, never a pasted stack


def test_the_could_not_complete_notice_is_plain_and_content_free() -> None:
    text = render_could_not_complete("acme/coffee", 55, 1, "c" * 40, "could_not_complete")
    assert "could not complete" in text.lower() and CAUSE not in text
    assert "Traceback" not in text and "Error" not in text  # no exception text, no provider error detail (FS-ERR-1)
