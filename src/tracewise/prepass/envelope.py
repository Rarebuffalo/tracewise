"""GitHub job-log envelope parsing, step slicing and streaming retention (T-201, T-206).

The failed job and step always come from the jobs API (`steps[]`), never from log
markers (FS-LOG-2, FS-SEC-2). Runner-written line timestamps assign lines to steps;
printed `##[group]`/`##[error]` text inside a step cannot move the attribution.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from tracewise.prepass.sanitize import clean

CONTEXT_LINES = 200
DEFAULT_MAX_BYTES = 2 * 1024 * 1024

_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z) ?")
_RUN = re.compile(r"^##\[group\]Run (.{1,500})$")
ERROR_LIKE = re.compile(
    r"##\[error\]|\b\w{0,60}(?:error|exception)s?\b|\b(?:failed|failure|traceback|fatal|panic)\b"
    r"|exit code [1-9]|^E {2}|^\s{0,4}●|^\s{0,2}FAIL\b|\bERR!",
    re.IGNORECASE,
)


class StepInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    name: str
    number: int
    status: str | None = None
    conclusion: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobInfo(BaseModel):
    """Subset of `GET /repos/{o}/{r}/actions/runs/{id}/attempts/{n}/jobs` items."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    id: int
    name: str
    conclusion: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[StepInfo] = []

    def failed_step(self) -> StepInfo | None:
        for s in self.steps:
            if s.conclusion in ("failure", "timed_out", "cancelled"):
                return s
        return None


@dataclass(frozen=True)
class LogLine:
    no: int  # 1-based line number in the original job log
    ts: datetime | None
    text: str  # sanitised and redacted


@dataclass
class RetainedLog:
    job_id: int
    job: str
    step: str | None
    step_number: int | None
    command: str | None
    lines: dict[int, str] = field(default_factory=dict)
    truncated: bool = False
    total_lines: int = 0

    def text(self, start: int, end: int) -> str | None:
        """Exact retained text for a line range, or None if any line is missing (validator rule 1)."""
        out = []
        for n in range(start, end + 1):
            if n not in self.lines:
                return None
            out.append(self.lines[n])
        return "\n".join(out)

    def ordered(self) -> list[tuple[int, str]]:
        return sorted(self.lines.items())


def _parse_ts(raw: str) -> datetime | None:
    # Python parses at most 6 fractional digits; GitHub writes 7.
    head, _, frac = raw.rstrip("Z").partition(".")
    try:
        return datetime.fromisoformat(f"{head}.{(frac + '000000')[:6]}+00:00" if frac else f"{head}+00:00")
    except ValueError:
        return None


def parse_lines(raw_lines: Iterable[str]) -> Iterator[LogLine]:
    last_ts: datetime | None = None
    for i, raw in enumerate(raw_lines, 1):
        m = _TS.match(raw)
        if m:
            last_ts = _parse_ts(m.group(1)) or last_ts
            raw = raw[m.end() :]
        yield LogLine(i, last_ts, clean(raw))


def _in_step(line: LogLine, step: StepInfo | None) -> bool:
    if step is None or step.started_at is None or line.ts is None:
        return True  # no timing data: the whole log is the section
    end = (step.completed_at or datetime.max.replace(tzinfo=step.started_at.tzinfo)) + timedelta(seconds=1)
    return step.started_at <= line.ts < end


_GROUP = re.compile(r"^##\[group\]")
_BOUNDARY_BUFFER = 5000  # lines held while the step's first second is undecided (bounded memory)


class _Section:
    """Which lines belong to the failing step (Phase 57, F3).

    Step times from the jobs API have one-second resolution and steps run back to back, so the failing step's first
    second can also hold the previous step's last lines, and the last second the next step's first lines. Lines of
    that first second are held until the step's own `##[group]Run …` header shows which ones precede it (dropped).
    If no header appears, nothing is dropped. After the step's completion time, a new `##[group]` header (the
    next step) ends the section. Without timing data the whole log is the section, as before."""

    def __init__(self, step: StepInfo | None) -> None:
        self.step = step
        self.held: list[LogLine] = []
        self.header_seen = False
        self.ended = False

    def feed(self, ln: LogLine) -> list[LogLine]:
        step = self.step
        if step is None or step.started_at is None:
            return [ln]
        if self.ended:
            return []
        if ln.ts is None:  # an untimed line follows the state of its neighbours
            if self.held:
                return self._hold(ln)
            return [ln]
        if not _in_step(ln, step):
            return self.flush() if ln.ts >= step.started_at else []
        if ln.ts < step.started_at + timedelta(seconds=1) and not self.header_seen:
            if _RUN.match(ln.text):
                self.header_seen = True
                self.held = []  # what came before our header in the shared second was the previous step's
                return [ln]
            return self._hold(ln)
        if step.completed_at is not None and ln.ts >= step.completed_at and self.header_seen and _GROUP.match(ln.text):
            self.ended = True  # the next step started
            return self.flush()
        out = self.flush() if self.held else []
        return [*out, ln]

    def _hold(self, ln: LogLine) -> list[LogLine]:
        self.held.append(ln)
        return self.flush() if len(self.held) > _BOUNDARY_BUFFER else []

    def flush(self) -> list[LogLine]:
        out, self.held = self.held, []
        if out:
            self.header_seen = True  # undecided lines are kept; the boundary is settled
        return out


def retain(job: JobInfo, raw_lines: Iterable[str], max_bytes: int = DEFAULT_MAX_BYTES) -> RetainedLog:
    """Stream a job log once, keeping (in priority order) the window around the first
    error-like line, the step tail, further error windows and the step head, within
    `max_bytes` (FS-LOG-4). Memory stays O(max_bytes)."""
    step = job.failed_step()
    out = RetainedLog(job.id, job.name, step.name if step else None, step.number if step else None, None)
    budget_first = max_bytes // 4
    budget_windows = max_bytes // 2
    budget_head = max_bytes // 8
    tail_cap = max_bytes - budget_first - budget_windows - budget_head

    used = {"first": 0, "windows": 0, "head": 0}
    before: deque[LogLine] = deque(maxlen=CONTEXT_LINES)
    tail: deque[LogLine] = deque()
    tail_bytes = 0
    after_left = 0
    after_bucket = ""
    first_seen = False
    in_section_count = 0
    dropped = False

    def keep(ln: LogLine, bucket: str, cap: int) -> bool:
        nonlocal dropped
        if ln.no in out.lines:
            return True
        size = len(ln.text.encode()) + 1
        if used[bucket] + size > cap:
            dropped = True
            return False
        used[bucket] += size
        out.lines[ln.no] = ln.text
        return True

    caps = {"first": budget_first, "windows": budget_windows, "head": budget_head}
    section = _Section(step)

    def section_lines() -> Iterator[LogLine]:
        for raw in parse_lines(raw_lines):
            out.total_lines = raw.no
            yield from section.feed(raw)  # other steps (setup, post) are not analysed
        yield from section.flush()

    for ln in section_lines():
        in_section_count += 1
        if out.command is None:
            m = _RUN.match(ln.text)
            if m:
                out.command = m.group(1).strip()
        if in_section_count <= CONTEXT_LINES:
            keep(ln, "head", caps["head"])
        if after_left > 0:
            keep(ln, after_bucket, caps[after_bucket])
            after_left -= 1
        if ERROR_LIKE.search(ln.text):
            bucket = "windows" if first_seen else "first"
            first_seen = True
            for b in before:
                keep(b, bucket, caps[bucket])
            keep(ln, bucket, caps[bucket])
            after_left, after_bucket = CONTEXT_LINES, bucket
        before.append(ln)
        tail.append(ln)
        tail_bytes += len(ln.text.encode()) + 1
        while tail_bytes > tail_cap or len(tail) > CONTEXT_LINES:
            old = tail.popleft()
            tail_bytes -= len(old.text.encode()) + 1
    for ln in tail:
        out.lines.setdefault(ln.no, ln.text)
    out.truncated = dropped or in_section_count > len(out.lines)
    return out
