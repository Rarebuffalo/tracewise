"""Phase 56: GitHub client defects found by an offline audit, reproduced first.

1. A log line with no newline made the download quadratic in time (the whole pending buffer was re-split per chunk)
   and unbounded in memory up to the 512 MiB cap. Only the first 2 * MAX_LINE_CHARS of a raw line are ever used
   (`strip_controls` pre-cuts there), so the stream keeps exactly that, and the output after cleaning is identical.
3. A 200 response whose JSON is not an object (`[]`, empty, null, a scalar) or is nested beyond the parser's
   recursion limit raised AttributeError/RecursionError, which the handler treats as retryable. It is now
   GitHubPermanent.
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.unit.test_github_client import BLOB, JOBS, LOGS, setup
from tracewise.github import errors as err
from tracewise.prepass.sanitize import MAX_LINE_CHARS, clean

# ------------------------------------------------------------------ 1. streaming


def stream(body: bytes, chunk: int = 65536, **limits: int) -> list[str]:
    gh, rc = setup(**limits)
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))

    def chunks() -> object:
        for i in range(0, len(body), chunk):
            yield body[i : i + chunk]

    gh.route("GET", r"^//productionresultssa1", lambda r: httpx.Response(200, content=chunks()))
    return list(rc.job_log_lines(99))


def test_a_huge_line_without_newline_streams_in_linear_time_and_bounded_memory() -> None:
    body = b"x" * (16 * 1024 * 1024) + b"\n" + b"normal line\n" * 1000
    t0 = time.monotonic()
    lines = stream(body)
    assert time.monotonic() - t0 < 5.0  # was ~0.6 s at 16 MiB and quadratic beyond (60 s at 128 MiB)
    assert len(lines) == 1001 and len(lines[0]) == 2 * MAX_LINE_CHARS and lines[1] == "normal line"


@pytest.mark.parametrize("chunk", [1, 7, 4096, 65536])
def test_streamed_lines_are_identical_after_cleaning_whatever_the_chunking(chunk: int) -> None:
    raw = ["short", "é" * 9000 + "tail", "", "a\rb\rc", "z" * (2 * MAX_LINE_CHARS + 3), "last"]
    body = "\n".join(raw).encode()
    got = stream(body, chunk=chunk)
    assert [clean(x) for x in got] == [clean(x) for x in raw]  # bounded buffering never changes what is analysed


def test_the_download_cap_still_drops_the_partial_tail_and_flags_truncation() -> None:
    gh, rc = setup(max_log_bytes=1000)
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh.route("GET", r"^//productionresultssa1", httpx.Response(200, text="x" * 99 + "\n" + "y" * 5000))
    lines = rc.job_log_lines(99)
    assert list(lines) == ["x" * 99] and lines.truncated


# ------------------------------------------------------------------ 3. JSON shape and depth


@pytest.mark.parametrize(
    "body",
    [b"[]", b"", b"null", b"[" * 200_000 + b"]" * 200_000, b'"just a string"'],
    ids=["array", "empty", "null", "deeply-nested", "scalar"],
)
def test_unexpected_json_is_a_permanent_github_error(body: bytes) -> None:
    gh, rc = setup()
    gh.route("GET", JOBS, httpx.Response(200, content=body))
    with pytest.raises(err.GitHubPermanent):
        rc.list_jobs(37632626982, 1)
