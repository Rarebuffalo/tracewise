"""C-3: tool reads and validation reads draw on separate, fixed pools carved out of the global read totals, so a
tool-heavy investigation cannot leave the validator unable to check the model's claims, and neither pool can grow."""

from __future__ import annotations

from typing import Any

import pytest

from tests.context.memsource import MemSource
from tests.investigate.factory import B02_ANSWER, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.context.source import Limits, ReadStatus, TransientReadError, TreeEntry
from tracewise.context.tools import ToolBox
from tracewise.contracts import Status
from tracewise.investigate.fake import ScriptedProvider

FILES = {f"f{i}.py": f"x = {i}\n" for i in range(10)}


def src(**kw: int) -> MemSource:
    return MemSource(FILES, limits=Limits(**kw))


def test_tools_exhausting_their_pool_leave_the_validation_reserve_intact() -> None:
    s = src(max_reads=5, validation_reads=2)  # tool pool: 3 reads
    assert [s.read(f"f{i}.py").status for i in range(4)] == [ReadStatus.ok] * 3 + [ReadStatus.budget_exhausted]
    assert s.read("f5.py", purpose="validation").status is ReadStatus.ok
    assert s.read("f6.py", purpose="validation").status is ReadStatus.ok


def test_the_validator_exhausts_only_its_own_reserve() -> None:
    s = src(max_reads=5, validation_reads=1)
    assert s.read("f0.py", purpose="validation").status is ReadStatus.ok
    assert s.read("f1.py", purpose="validation").status is ReadStatus.budget_exhausted
    assert s.read("f2.py").status is ReadStatus.ok  # the tool pool is untouched


def test_both_pools_together_never_exceed_the_global_totals() -> None:
    s = src(max_reads=6, validation_reads=2)
    ok = sum(s.read(f"f{i}.py", purpose=p).status is ReadStatus.ok for p in ("tool", "validation") for i in range(10))
    assert ok == 6
    b = MemSource({"a.py": "a" * 600, "b.py": "b" * 600}, limits=Limits(max_total_read_bytes=1000, validation_read_bytes=400))
    assert b.read("a.py").status is ReadStatus.ok  # 600 of the 600-byte tool pool
    assert b.read("b.py").status is ReadStatus.budget_exhausted
    assert b.read("b.py", purpose="validation").status is ReadStatus.budget_exhausted  # 600 > the 400-byte reserve


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"max_reads": 4, "validation_reads": 4}, "validation_reads"),
        ({"validation_reads": 0}, "validation_reads"),
        ({"max_total_read_bytes": 10, "validation_read_bytes": 10}, "validation_read_bytes"),
        ({"validation_read_bytes": 0}, "validation_read_bytes"),
    ],
)
def test_a_reserve_must_be_finite_and_inside_the_totals(kw: dict[str, int], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Limits(**kw)


@pytest.mark.parametrize("purpose", ["tool", "validation"])
def test_path_size_and_link_rules_are_the_same_for_every_purpose(purpose) -> None:  # type: ignore[no-untyped-def]
    s = MemSource(
        {"big.txt": "z" * 2_000_000, "logo.png": b"\x89PNG\x00\x00"},
        symlinks={"up": "../../secret", "passwd": "/etc/passwd"},
        submodules=("vendor/lib",),
    )
    assert s.read("../etc/passwd", purpose=purpose).status is ReadStatus.invalid_path
    assert s.read(".git/config", purpose=purpose).status is ReadStatus.invalid_path
    assert s.read("up", purpose=purpose).status is ReadStatus.symlink_escapes
    assert s.read("passwd", purpose=purpose).status is ReadStatus.symlink_escapes
    assert s.read("vendor/lib", purpose=purpose).status is ReadStatus.submodule
    assert s.read("big.txt", purpose=purpose).status is ReadStatus.too_large
    assert s.read("logo.png", purpose=purpose).status is ReadStatus.binary


def test_oversized_files_are_refused_without_spending_budget() -> None:
    s = MemSource({"big.txt": "z" * 2_000_000, "a.py": "a"}, limits=Limits(max_reads=3, validation_reads=1))
    for _ in range(5):
        assert s.read("big.txt").status is ReadStatus.too_large
    assert [s.read("a.py").status for _ in range(3)] == [ReadStatus.ok, ReadStatus.ok, ReadStatus.budget_exhausted]


class _Flaky(MemSource):
    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        return None if entry.path == "gone.py" else super()._read_blob(entry)


def test_failed_and_budget_denied_reads_are_recorded_as_skipped() -> None:
    s = _Flaky({"gone.py": "x", "a.py": "a", "b.py": "b"}, limits=Limits(max_reads=3, validation_reads=1))
    assert s.read("gone.py").status is ReadStatus.unavailable
    assert s.read("a.py").status is ReadStatus.ok
    assert s.read("b.py").status is ReadStatus.budget_exhausted  # gone.py's attempt counted: 2 tool reads
    assert s.skipped == {"gone.py": ReadStatus.unavailable, "b.py": ReadStatus.budget_exhausted}


def test_grep_after_the_tool_pool_runs_out_says_files_were_not_searched() -> None:
    s = src(max_reads=4, validation_reads=1)
    r = ToolBox(s).call("grep", {"pattern": "never-present"})
    assert r.ok and r.content.startswith("no matches") and "7 file(s) not searched" in r.content


def _tool_heavy(limits: Limits) -> Status:
    files = {
        "coffee_shop/__init__.py": "",
        "coffee_shop/pricing.py": "".join(f"# line {i}\n" for i in range(1, 41)) + "    return round(subtotal_ * TAX_RATE, 2)\n",
        **{f"pad/p{i}.py": "p\n" for i in range(20)},
    }
    ev = evidence(source=MemSource(files, limits=limits))
    script = [
        tool("read_file", path="coffee_shop/pricing.py", start=30, end=41),
        tool("grep", cid="c2", pattern="anything"),  # drains the tool pool
        answer(**B02_ANSWER),
    ]
    return diagnose(ev, ScriptedProvider(script)).diagnosis


def test_a_tool_heavy_investigation_no_longer_starves_the_location_check() -> None:
    """Before C-3 the grep drained the shared budget and the correct location came back `location_unreadable`."""
    d = _tool_heavy(Limits(max_reads=8, validation_reads=2))
    assert d.status is Status.diagnosed and d.problem_location is not None
    assert d.limits.files_skipped  # what the grep could not read stays visible


def test_an_exhausted_validation_reserve_is_inconclusive_with_its_own_reason() -> None:
    d = _tool_heavy(Limits(max_reads=8, validation_reads=2, max_total_read_bytes=100_000, validation_read_bytes=10))
    assert d.status is Status.inconclusive
    assert d.inconclusive_reason == "location_validation_budget_exhausted"  # never "location_unreadable"
    assert "validation_budget_exhausted" in d.validation_flags


# ------------------------------------------------------------------ D-B: validation infrastructure failures


class _FlakyAfterTools(MemSource):
    """Reads fail transiently once `failing` is set (after the tool phase), `fail_for` times in a row."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.failing, self.fail_for = False, 0
        self._sleep = lambda s: None

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        if self.failing and self.fail_for > 0:
            self.fail_for -= 1
            raise TransientReadError("synthetic 502")
        return super()._read_blob(entry)


def _answer_then_break(src: _FlakyAfterTools, fail_for: int) -> Any:
    def step(req: Any) -> Any:
        src.failing, src.fail_for = True, fail_for  # the model has answered; validation reads now hit the outage
        return answer(**B02_ANSWER)

    return step


def test_a_transient_validation_read_is_retried_in_place_without_asking_the_model_again() -> None:
    from tests.investigate.factory import B02_FILES

    src = _FlakyAfterTools(B02_FILES)
    p = ScriptedProvider([tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), _answer_then_break(src, 1)])
    d = diagnose(evidence(source=src), p).diagnosis
    assert d.status is Status.diagnosed and d.problem_location is not None  # the same answer, validated
    assert len(p.requests) == 2  # one tool step, one answer: no repeated model call


def test_a_persistent_validation_outage_is_an_infrastructure_failure_not_an_invalid_answer() -> None:
    from tests.investigate.factory import B02_FILES
    from tracewise.investigate.validate import ValidationUnavailable

    src = _FlakyAfterTools(B02_FILES)
    p = ScriptedProvider([tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), _answer_then_break(src, 99)])
    with pytest.raises(ValidationUnavailable):
        diagnose(evidence(source=src), p)  # never "location_unreadable" or another verdict on the answer
    assert len(p.requests) == 2
