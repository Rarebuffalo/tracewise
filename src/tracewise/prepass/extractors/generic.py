"""Generic fallback extractor (T-205): annotations, installers, common `error:` prefixes."""

from __future__ import annotations

import re

from tracewise.prepass.extractors.base import Candidate, Lines

_EXIT = re.compile(r"^##\[error\]Process completed with exit code (\d{1,3})\.?$")
_TIMEOUT = re.compile(
    r"^##\[error\]The (?:job|operation) (?:running on runner .{0,200} )?has exceeded the maximum execution time"
)
_ANNOT = re.compile(r"^##\[error\](.{1,2000})$")
_INSTALL = re.compile(
    r"^(?:ERROR: (?:Could not find a version|No matching distribution|Cannot install|ResolutionImpossible"
    r"|Could not install|Failed building wheel).{0,2000}"
    r"|npm (?:ERR!|error) (?:code )?(?:ERESOLVE|E404|ETARGET|ENOTFOUND).{0,2000}"
    r"|error: (?:failed to (?:solve|resolve)|Because ).{0,2000}"
    r"|(?:× |error: )No solution found when resolving dependencies.{0,2000})$"  # uv
)
# pip reports one unresolvable requirement as two lines; the second continues the first (A-04).
_PIP_NOVERSION = re.compile(r"^ERROR: Could not find a version that satisfies the requirement (\S{1,300})")
_PIP_NODIST = re.compile(r"^ERROR: No matching distribution found for (\S{1,300})$")
# pip's conflict report: "Cannot install …", an explanation, then a closing "ResolutionImpossible" line (Phase 52).
_PIP_CONFLICT = "ERROR: Cannot install "
_PIP_IMPOSSIBLE = "ERROR: ResolutionImpossible"
_PIP_REPORT_SPAN = 15
# npm prints one failure as a contiguous block of `npm error` / `npm ERR!` lines (Phase 52).
_NPM_PREFIXES = ("npm error", "npm ERR!")
_PREFIX = re.compile(r"^(?:Error|ERROR|error|fatal|FATAL|npm ERR!|npm error)(?::|!)? (.{1,2000})$")
_KILLED = re.compile(r"(?:exit code 137|Killed$|signal 9\b|out of memory|OOMKilled)", re.IGNORECASE)


_FIRST = frozenset("#EefFn×")  # first characters of every prefix above
_KILL_HINTS = ("137", "Killed", "signal 9", "emory", "OOM")


def generic(job_id: int, lines: Lines) -> list[Candidate]:
    """Candidates in line order. Continuation lines of ONE installer failure report are folded into the report's
    first candidate (its span grows) instead of becoming further primaries: pip's two-line "no matching
    distribution" (A-04), pip's conflict report ending in ResolutionImpossible, and an npm error block. Anything
    outside such a report, or separated from it by other output, stays a separate candidate."""
    out: list[Candidate] = []
    npm_block_start: int | None = None  # first line of the current contiguous npm error block
    npm_block_owner: Candidate | None = None  # the block's first candidate
    for no, text in lines:
        t = text.strip()
        in_npm = t.startswith(_NPM_PREFIXES)
        if not in_npm:
            npm_block_start = npm_block_owner = None
        elif npm_block_start is None:
            npm_block_start = no
        if not t or (t[0] not in _FIRST and not any(h in t for h in _KILL_HINTS)):
            continue
        if in_npm and npm_block_owner is not None and (_INSTALL.match(t) or _PREFIX.match(t)):
            npm_block_owner.log_line_end = no  # the same npm failure report
            continue
        if m := _EXIT.match(t):
            code = m.group(1)
            out.append(Candidate("runner", "exit", job_id, no, t.removeprefix("##[error]"), code=f"exit {code}"))
        elif _TIMEOUT.match(t):
            out.append(Candidate("runner", "generic", job_id, no, t.removeprefix("##[error]"), code="timeout"))
        elif _INSTALL.match(t):
            prev = out[-1] if out else None
            follow = _PIP_NODIST.match(t)
            lead = _PIP_NOVERSION.match(prev.message) if prev is not None and prev.tool == "installer" else None
            if prev is not None and follow and lead and lead.group(1) == follow.group(1) and no - prev.span[1] <= 2:
                prev.log_line_end = no  # the same failure: one candidate spanning both lines
                continue
            if (
                prev is not None
                and t.startswith(_PIP_IMPOSSIBLE)
                and prev.message.startswith(_PIP_CONFLICT)
                and no - prev.span[1] <= _PIP_REPORT_SPAN
            ):
                prev.log_line_end = no  # the closing line of the same conflict report
                continue
            out.append(Candidate("installer", "install", job_id, no, t, code="install"))
        elif m := _ANNOT.match(t):
            out.append(Candidate("annotation", "generic", job_id, no, m.group(1).strip()))
        elif _PREFIX.match(t):
            out.append(Candidate("generic", "generic", job_id, no, t))
        elif _KILLED.search(t):
            out.append(Candidate("runner", "generic", job_id, no, t, code="oom"))
        if in_npm and npm_block_owner is None and out and out[-1].log_line == no:
            npm_block_owner = out[-1]
    return out
