"""Builders for GitHub-shaped job logs and jobs-API fixtures (offline)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tracewise.prepass.envelope import JobInfo

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC)


def fixture(name: str) -> str:
    return (FIXTURES / "logs" / name).read_text()


def _ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}0Z"


def build_job(
    job_id: int,
    job_name: str,
    step_name: str,
    command: str,
    output: str,
    *,
    exit_code: int = 1,
    pre_output: str = "",
) -> tuple[JobInfo, list[str]]:
    """Job with steps 'Set up job' (1s), 'Checkout' (1s), the failing step (10s), 'Post' (1s).

    `pre_output` is printed during Checkout (before the failing step).
    """
    lines: list[str] = []

    def emit(t: datetime, text: str) -> None:
        lines.append(f"{_ts(t)} {text}")

    s1, s2, s3, s4 = T0, T0 + timedelta(seconds=2), T0 + timedelta(seconds=4), T0 + timedelta(seconds=16)
    emit(s1 + timedelta(milliseconds=10), "Current runner version: '2.320.0'")
    emit(s1 + timedelta(milliseconds=20), "##[group]Operating System")
    emit(s1 + timedelta(milliseconds=30), "Ubuntu 24.04")
    emit(s1 + timedelta(milliseconds=40), "##[endgroup]")
    emit(s2 + timedelta(milliseconds=10), "##[group]Run actions/checkout@v4")
    emit(s2 + timedelta(milliseconds=20), "##[endgroup]")
    for i, text in enumerate(pre_output.splitlines()):
        emit(s2 + timedelta(milliseconds=30 + i), text)
    emit(s3 + timedelta(milliseconds=1), f"##[group]Run {command}")
    emit(s3 + timedelta(milliseconds=2), f"\x1b[36;1m{command}\x1b[0m")
    emit(s3 + timedelta(milliseconds=3), "shell: /usr/bin/bash -e {0}")
    emit(s3 + timedelta(milliseconds=4), "##[endgroup]")
    out_lines = output.splitlines()
    step = timedelta(seconds=9) / max(1, len(out_lines) + 1)
    for i, text in enumerate(out_lines):
        emit(s3 + timedelta(milliseconds=5) + step * i, text)
    if exit_code:
        emit(s3 + timedelta(seconds=9, milliseconds=900), f"##[error]Process completed with exit code {exit_code}.")
    emit(s4 + timedelta(milliseconds=10), "Post job cleanup.")
    emit(s4 + timedelta(milliseconds=20), "Cleaning up orphan processes")

    def step_json(n: int, name: str, a: datetime, b: datetime, concl: str) -> dict[str, object]:
        return {
            "name": name,
            "number": n,
            "status": "completed",
            "conclusion": concl,
            "started_at": a.isoformat().replace("+00:00", "Z"),
            "completed_at": b.isoformat().replace("+00:00", "Z"),
        }

    job = JobInfo.model_validate(
        {
            "id": job_id,
            "name": job_name,
            "conclusion": "failure",
            "started_at": T0.isoformat(),
            "completed_at": (s4 + timedelta(seconds=1)).isoformat(),
            "steps": [
                step_json(1, "Set up job", s1, s1 + timedelta(seconds=1), "success"),
                step_json(2, "Checkout", s2, s2 + timedelta(seconds=1), "success"),
                step_json(3, step_name, s3, s3 + timedelta(seconds=10), "failure" if exit_code else "success"),
                step_json(4, "Post Run actions/checkout@v4", s4, s4 + timedelta(seconds=1), "success"),
            ],
        }
    )
    return job, lines
