"""Primary-error ranking, cascades, sibling grouping and fingerprints (T-205, FS-DX-1, FS-DX-2).

Rules, in order:
  1. Candidates come from the tool extractors plus the generic fallback, per failed job.
  2. Generic candidates duplicating a tool candidate are dropped. After the first tool
     candidate in a job, generic lines are dropped (they are summaries); installer
     failures and runner timeouts are always kept. `exit code N` is kept only when
     nothing else exists in that job.
  3. Order = (job order, log line).
  4. A missing-module error is a cascade when an earlier compile or install failure exists,
     or when a compile error names the same module.
  5. Remaining candidates are grouped by fingerprint; groups in order; first 3 are primaries.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from tracewise.contracts import FailedStep
from tracewise.prepass.envelope import DEFAULT_MAX_BYTES, JobInfo, RetainedLog, retain
from tracewise.prepass.extractors import generic as gen
from tracewise.prepass.extractors import python as py
from tracewise.prepass.extractors import typescript as ts
from tracewise.prepass.extractors.base import Candidate, Lines

MAX_PRIMARIES = 3
MAX_SIBLING_NAMES = 20

Extractor = Callable[[int, Lines], list[Candidate]]
TOOL_EXTRACTORS: tuple[Extractor, ...] = (
    py.pytest,
    py.traceback,
    py.ruff,
    py.mypy,
    ts.tsc,
    ts.jest,
    ts.vitest,
    ts.eslint,
)
_ALWAYS_KEEP = {"install"}

_HEX = re.compile(r"\b[0-9a-f]{7,64}\b")
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def fingerprint(c: Candidate) -> str:
    msg = _WS.sub(" ", _NUM.sub("<n>", _HEX.sub("<hex>", c.message))).strip()
    basis = f"{c.tool}|{c.code or ''}|{msg}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


@dataclass
class Group:
    fingerprint: str
    members: list[Candidate]

    @property
    def primary(self) -> Candidate:
        return self.members[0]

    @property
    def sibling_names(self) -> list[str]:
        return [m.label for m in self.members[1:]][:MAX_SIBLING_NAMES]


@dataclass
class PrepassResult:
    failed: list[FailedStep]
    logs: dict[int, RetainedLog]
    primaries: list[Group]
    overflow_groups: int = 0
    cascades: list[Candidate] = field(default_factory=list)

    @property
    def log_truncated(self) -> bool:
        return any(r.truncated for r in self.logs.values())

    def excerpt(self, c: Candidate) -> str | None:
        log = self.logs.get(c.job_id)
        return log.text(*c.span) if log else None


def _job_candidates(job_id: int, lines: Lines) -> list[Candidate]:
    tool: list[Candidate] = []
    for ex in TOOL_EXTRACTORS:
        tool.extend(ex(job_id, lines))
    generic = gen.generic(job_id, lines)
    tool_lines = {n for c in tool for n in range(c.span[0], c.span[1] + 1)}
    tool_msgs = [c.message for c in tool if c.message]
    first_tool = min((c.log_line for c in tool), default=None)
    kept: list[Candidate] = []
    for g in generic:
        if g.log_line in tool_lines or any(m in g.message or g.message in m for m in tool_msgs):
            continue
        if g.kind in _ALWAYS_KEEP or g.code == "timeout":
            kept.append(g)
        elif first_tool is None or g.log_line < first_tool:
            kept.append(g)
    out = tool + kept
    if any(c.kind != "exit" for c in out):
        out = [c for c in out if c.kind != "exit"]
    return sorted(out, key=lambda c: c.log_line)


def rank(per_job: Sequence[list[Candidate]]) -> tuple[list[Group], list[Candidate], int]:
    ordered = [c for job in per_job for c in job]  # job order, then line order
    compile_modules = {c.module for c in ordered if c.kind == "compile" and c.module}
    seen_root = False
    cascades: list[Candidate] = []
    roots: list[Candidate] = []
    for c in ordered:
        if c.kind == "missing_module" and (seen_root or (c.module in compile_modules)):
            cascades.append(c)
            continue
        if c.kind in ("compile", "install"):
            seen_root = True
        roots.append(c)
    groups: dict[str, Group] = {}
    for c in roots:
        fp = fingerprint(c)
        groups.setdefault(fp, Group(fp, [])).members.append(c)
    ordered_groups = list(groups.values())
    return ordered_groups[:MAX_PRIMARIES], cascades, max(0, len(ordered_groups) - MAX_PRIMARIES)


def run_prepass(jobs: Iterable[tuple[JobInfo, Iterable[str]]], max_bytes: int = DEFAULT_MAX_BYTES) -> PrepassResult:
    """`jobs`: failed jobs from the jobs API, each with its raw log line iterator, in job order."""
    failed: list[FailedStep] = []
    logs: dict[int, RetainedLog] = {}
    per_job: list[list[Candidate]] = []
    for job, raw in jobs:
        log = retain(job, raw, max_bytes)
        logs[job.id] = log
        failed.append(FailedStep(job_id=job.id, job=job.name[:200], step=log.step, command=log.command))
        cands = _job_candidates(job.id, log.ordered())
        for c in cands:
            c.step_number = log.step_number or 0
        per_job.append(cands)
    primaries, cascades, overflow = rank(per_job)
    return PrepassResult(failed, logs, primaries, overflow, cascades)
