"""Phase 57 (F3): step times have one-second resolution, so the previous step's last lines (and the next step's first
lines) could be analysed as the failing step's and become a primary error. Found by an offline audit, reproduced first."""

from __future__ import annotations

from tracewise.prepass.envelope import JobInfo
from tracewise.prepass.primary import run_prepass

# ------------------------------------------------------------------ F3


def ts(s: str) -> str:
    return f"2026-10-17T10:00:{s}Z"


JOB = JobInfo.model_validate(
    {
        "id": 1,
        "name": "test",
        "conclusion": "failure",
        "steps": [
            {"name": "Install", "number": 2, "conclusion": "success", "started_at": ts("02"), "completed_at": ts("05")},
            {"name": "Run tests", "number": 3, "conclusion": "failure", "started_at": ts("05"), "completed_at": ts("09")},
        ],
    }
)


def test_f3_previous_step_output_in_the_shared_second_is_not_the_failing_steps() -> None:
    lines = [
        ts("02.1000000") + " ##[group]Run pip install -r requirements.txt",
        ts("02.2000000") + " ##[endgroup]",
        ts("05.1000000") + " ERROR: pip's dependency resolver does not currently take into account all installed packages.",
        ts("05.3000000") + " ##[group]Run pytest",
        ts("05.3100000") + " ##[endgroup]",
        ts("06.0000000") + " FAILED tests/test_x.py::test_a - assert 1 == 2",
        ts("08.9000000") + " ##[error]Process completed with exit code 1.",
    ]
    r = run_prepass([(JOB, lines)])
    assert r.failed[0].command == "pytest"
    assert [g.primary.tool for g in r.primaries] == ["pytest"]


def test_f3_without_a_step_header_the_first_second_is_kept() -> None:
    lines = [ts("05.1000000") + " FAILED tests/test_y.py::test_b - assert 0", ts("06.0000000") + " more output"]
    r = run_prepass([(JOB, lines)])
    assert [g.primary.tool for g in r.primaries] == ["pytest"]  # no evidence is lost when no header appears


def test_f3_post_step_output_after_completion_is_not_analysed() -> None:
    lines = [
        ts("05.3000000") + " ##[group]Run pytest",
        ts("06.0000000") + " Error: build script failed",
        ts("09.2000000") + " ##[group]Run actions/cache/save",
        ts("09.4000000") + " Error: Cache service responded with 503",
    ]
    r = run_prepass([(JOB, lines)])
    assert [g.primary.message for g in r.primaries] == ["Error: build script failed"]
