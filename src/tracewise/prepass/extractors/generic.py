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
    r"|error: (?:failed to (?:solve|resolve)|Because ).{0,2000})$"
)
# pip reports one unresolvable requirement as two lines; the second continues the first (A-04).
_PIP_NOVERSION = re.compile(r"^ERROR: Could not find a version that satisfies the requirement (\S{1,300})")
_PIP_NODIST = re.compile(r"^ERROR: No matching distribution found for (\S{1,300})$")
_PREFIX = re.compile(r"^(?:Error|ERROR|error|fatal|FATAL|npm ERR!|npm error)(?::|!)? (.{1,2000})$")
_KILLED = re.compile(r"(?:exit code 137|Killed$|signal 9\b|out of memory|OOMKilled)", re.IGNORECASE)


_FIRST = frozenset("#EefFn")  # first characters of every prefix above
_KILL_HINTS = ("137", "Killed", "signal 9", "emory", "OOM")


def generic(job_id: int, lines: Lines) -> list[Candidate]:
    out = []
    for no, text in lines:
        t = text.strip()
        if not t or (t[0] not in _FIRST and not any(h in t for h in _KILL_HINTS)):
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
            out.append(Candidate("installer", "install", job_id, no, t, code="install"))
        elif m := _ANNOT.match(t):
            out.append(Candidate("annotation", "generic", job_id, no, m.group(1).strip()))
        elif _PREFIX.match(t):
            out.append(Candidate("generic", "generic", job_id, no, t))
        elif _KILLED.search(t):
            out.append(Candidate("runner", "generic", job_id, no, t, code="oom"))
    return out
