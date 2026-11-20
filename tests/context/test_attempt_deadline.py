"""C-4: one deadline for the whole analysis attempt, derived once from the job's durable deadline and passed down.
Offline: scripted providers and in-memory sources; fake clocks."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from tests.investigate.factory import B02_ANSWER, answer, evidence, tool
from tracewise.analysis.attempt import MIN_INVESTIGATION_S, PUBLISH_RESERVE_S, AttemptDeadline
from tracewise.analysis.collect import _LogStream
from tracewise.analysis.diagnose import diagnose
from tracewise.contracts import Status
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.loop import InvestigationLimits
from tracewise.jobs.queue import JOB_DEADLINE_S

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t: float = 1000.0, step: float = 0.0) -> None:
        self.t, self.step = t, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def test_the_deadline_is_the_job_deadline_less_the_publication_reserve() -> None:
    c = Clock()
    d = AttemptDeadline.for_job(NOW + timedelta(seconds=300), NOW, clock=c)
    assert d.remaining() == pytest.approx(300 - PUBLISH_RESERVE_S)
    c.t += 1000
    assert d.remaining() == 0.0 and d.expired  # never negative
    assert AttemptDeadline.for_job(None, NOW, clock=Clock()).remaining() == pytest.approx(JOB_DEADLINE_S - PUBLISH_RESERVE_S)
    assert AttemptDeadline.for_job(NOW - timedelta(seconds=5), NOW, clock=Clock()).expired  # already past
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.at = 1e12  # type: ignore[misc]  # a nested stage cannot extend it


def test_a_stage_limit_is_capped_by_the_time_left_never_reset() -> None:
    c = Clock()
    d = AttemptDeadline.for_job(NOW + timedelta(seconds=PUBLISH_RESERVE_S + 30), NOW, clock=c)
    assert d.cap(120.0) == pytest.approx(30.0) and d.cap(5.0) == 5.0
    c.t += 20
    assert d.cap(120.0) == pytest.approx(10.0)  # the same instant, read later: less left, not a fresh 30


def test_the_investigation_gets_what_is_left_and_provider_requests_are_bounded_by_it() -> None:
    d = AttemptDeadline.for_job(NOW + timedelta(seconds=PUBLISH_RESERVE_S + 30), NOW, clock=Clock())
    p = ScriptedProvider([tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), answer(**B02_ANSWER)])
    vd = diagnose(evidence(), p, limits=InvestigationLimits(timeout_s=120.0), deadline=d)
    assert vd.diagnosis.status is Status.diagnosed
    assert all(r.timeout_s <= 30.0 for r in p.requests)  # never the configured 120 s


def test_too_little_time_left_skips_the_investigation_with_its_own_reason() -> None:
    d = AttemptDeadline.for_job(NOW + timedelta(seconds=PUBLISH_RESERVE_S + MIN_INVESTIGATION_S - 1), NOW, clock=Clock())
    p = ScriptedProvider([answer(**B02_ANSWER)])
    dg = diagnose(evidence(), p, deadline=d).diagnosis
    assert p.requests == []  # no provider spend
    assert dg.status is Status.inconclusive and dg.inconclusive_reason == "attempt_deadline_exhausted"
    assert dg.limits.budget_exhausted and dg.problem_location is None and dg.fix is None  # never complete-looking


def test_time_running_out_between_tool_calls_ends_as_budget_exhausted_not_as_a_diagnosis() -> None:
    clock = Clock(step=4.0)  # every clock read costs 4 s: the 30 s left run out after a few dispatches
    d = AttemptDeadline.for_job(NOW + timedelta(seconds=PUBLISH_RESERVE_S + 30), NOW, clock=clock)
    script = [tool("list_dir", cid=f"c{i}", path=".") for i in range(10)] + [answer(**B02_ANSWER)]
    dg = diagnose(evidence(), ScriptedProvider(script), deadline=d, clock=clock).diagnosis
    assert dg.status is Status.inconclusive and dg.inconclusive_reason == "budget_exhausted"


class _Lines:
    def __init__(self, n: int) -> None:
        self.it, self.closed = iter([f"line {i}" for i in range(n)]), False

    def __iter__(self) -> _Lines:
        return self

    def __next__(self) -> str:
        return next(self.it)

    def close(self) -> None:
        self.closed = True


class _RC:
    def __init__(self, lines: _Lines) -> None:
        self.lines = lines

    def job_log_lines(self, job_id: int) -> _Lines:
        return self.lines


def test_a_log_stream_stops_at_the_deadline_keeps_what_it_read_and_releases_the_stream() -> None:
    c = Clock()
    d = AttemptDeadline(c.t + 3.5, c)
    lines = _Lines(100)
    s = _LogStream(_RC(lines), 7, clock=lambda: 0.0, deadline=d)  # type: ignore[arg-type]
    s.open()
    c.step = 1.0
    got = list(s)
    assert 0 < len(got) < 100 and s.truncated and s.deadline_cut and lines.closed and s.error is None


def test_a_log_stream_without_a_deadline_is_read_in_full() -> None:
    s = _LogStream(_RC(_Lines(100)), 7, clock=lambda: 0.0)  # type: ignore[arg-type]
    s.open()
    assert len(list(s)) == 100 and not s.truncated and not s.deadline_cut
