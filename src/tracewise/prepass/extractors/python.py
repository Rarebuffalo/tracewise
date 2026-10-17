"""Python extractors: pytest, tracebacks, ruff, mypy (T-203)."""

from __future__ import annotations

import re

from tracewise.prepass.extractors.base import Candidate, Kind, Lines, module_key, norm_path

# --- pytest
_SECTION = re.compile(r"^_{3,} (\S.{0,300}?) _{3,}$")
_E_LINE = re.compile(r"^E {1,8}(\S.{0,2000})$")
_LOC = re.compile(r"^([\w./\\-]{1,300}\.py):(\d{1,7}): (?:in \S{1,200}|(\w{1,100}))$")
_SUMMARY = re.compile(r"^(FAILED|ERROR) ([\w./\\-]{1,300}\.py(?:::[^\s]{1,300})?)(?: - (.{1,2000}))?$")


def _short(nodeid: str) -> str:
    tail = nodeid.split("::", 1)[1] if "::" in nodeid else nodeid
    return tail.replace("::", ".")


def pytest(job_id: int, lines: Lines) -> list[Candidate]:
    """Failure sections (`____ test_x ____` + first `E` line) first, then the short summary."""
    by_test: dict[str, Candidate] = {}
    current: str | None = None
    loc: tuple[str, int] | None = None
    for no, text in lines:
        m = _SECTION.match(text)
        if m:
            current, loc = m.group(1).strip(), None
            continue
        if current is None:
            continue
        m = _LOC.match(text)
        if m:
            loc = (norm_path(m.group(1)), int(m.group(2)))
            c = by_test.get(current)
            if c is not None and c.path is None:  # long format: location after the E lines
                c.path, c.line = loc
            continue
        m = _E_LINE.match(text)
        if m and current not in by_test:
            msg = m.group(1).strip()
            mod = _missing_module(msg)
            by_test[current] = Candidate(
                "pytest",
                "missing_module" if mod else "test",
                job_id,
                no,
                msg,
                test=current,
                code=_exc_name(msg),
                module=mod,
                path=loc[0] if loc else None,
                line=loc[1] if loc else None,
            )
    out: dict[str, Candidate] = {c.test or "": c for c in by_test.values()}
    for no, text in lines:
        m = _SUMMARY.match(text)
        if not m:
            continue
        nodeid, msg = m.group(2), (m.group(3) or "").strip()
        short = _short(nodeid)
        hit = short if short in out else (f"ERROR collecting {nodeid}" if f"ERROR collecting {nodeid}" in out else None)
        if hit is not None:
            existing = out.pop(hit)
            existing.test = nodeid
            if existing.path is None:
                existing.path = norm_path(nodeid.split("::")[0])
            out[nodeid] = existing
        elif nodeid not in out:
            mod = _missing_module(msg)
            kind: Kind = "missing_module" if mod else ("test" if m.group(1) == "FAILED" else "exception")
            out[nodeid] = Candidate(
                "pytest",
                kind,
                job_id,
                no,
                msg or m.group(1),
                test=nodeid,
                path=norm_path(nodeid.split("::")[0]),
                code=_exc_name(msg),
                module=mod,
            )
    return list(out.values())


def _exc_name(msg: str) -> str | None:
    m = re.match(r"^(?:E\s+)?([A-Z]\w{0,80}(?:Error|Exception|Warning|Exit))\b", msg)
    if m:
        return m.group(1)
    return "AssertionError" if msg.startswith("assert ") else None


_NO_MODULE = re.compile(r"No module named ['\"]?([\w.]{1,200})['\"]?")


def _missing_module(msg: str) -> str | None:
    m = _NO_MODULE.search(msg)
    return module_key(m.group(1)) if m else None


# --- tracebacks
_TB_START = "Traceback (most recent call last):"
_FRAME = re.compile(r'^\s{0,8}File "([^"]{1,500})", line (\d{1,7})(?:, in (\S{1,200}))?')
_EXC = re.compile(r"^([A-Za-z_][\w.]{0,200}(?:Error|Exception|Exit|Interrupt|Warning|KeyError)?)(?::\s?(.{0,2000}))?$")
_LIB = re.compile(r"(?:site-packages|dist-packages|/lib/python\d|<frozen |^/usr/|/opt/hostedtoolcache/)")


def traceback(job_id: int, lines: Lines) -> list[Candidate]:
    out: list[Candidate] = []
    i, n = 0, len(lines)
    while i < n:
        no, text = lines[i]
        if text.strip() != _TB_START:
            i += 1
            continue
        start = no
        frames: list[tuple[str, int]] = []
        j = i + 1
        while j < n and j - i < 400:
            t = lines[j][1]
            fm = _FRAME.match(t)
            if fm:
                frames.append((fm.group(1), int(fm.group(2))))
            elif t[:1] not in (" ", "\t") and t.strip():
                break
            j += 1
        if j >= n:
            break
        end_no, last = lines[j]
        em = _EXC.match(last.strip())
        if em and frames:
            exc, msg = em.group(1), (em.group(2) or "").strip()
            own = [f for f in frames if not _LIB.search(f[0])]
            path, line = own[-1] if own else frames[-1]
            mod = _missing_module(last) if "ModuleNotFoundError" in exc or "ImportError" in exc else None
            out.append(
                Candidate(
                    "traceback",
                    "missing_module" if mod else "exception",
                    job_id,
                    start,
                    f"{exc}: {msg}" if msg else exc,
                    log_line_end=end_no,
                    code=exc.rsplit(".", 1)[-1],
                    path=norm_path(path),
                    line=line,
                    module=mod,
                )
            )
        i = j + 1
    return out


# --- ruff (concise and full output formats)
_RUFF_CONCISE = re.compile(r"^([\w./\\-]{1,300}\.pyi?):(\d{1,7}):(\d{1,5}): ([A-Z]{1,4}\d{2,4}) (?:\[\*\] )?(.{1,1000})$")
_RUFF_FULL_HEAD = re.compile(r"^([A-Z]{1,4}\d{2,4}) (?:\[\*\] )?(.{1,1000})$")
_RUFF_FULL_LOC = re.compile(r"^\s{0,8}--> ([\w./\\-]{1,300}\.pyi?):(\d{1,7}):(\d{1,5})$")


def ruff(job_id: int, lines: Lines) -> list[Candidate]:
    out: list[Candidate] = []
    pending: tuple[int, str, str] | None = None
    for no, text in lines:
        m = _RUFF_CONCISE.match(text)
        if m:
            out.append(
                Candidate(
                    "ruff",
                    "lint",
                    job_id,
                    no,
                    m.group(5).strip(),
                    code=m.group(4),
                    path=norm_path(m.group(1)),
                    line=int(m.group(2)),
                )
            )
            continue
        m = _RUFF_FULL_HEAD.match(text)
        if m:
            pending = (no, m.group(1), m.group(2).strip())
            continue
        m = _RUFF_FULL_LOC.match(text)
        if m and pending:
            out.append(
                Candidate(
                    "ruff",
                    "lint",
                    job_id,
                    pending[0],
                    pending[2],
                    log_line_end=no,
                    code=pending[1],
                    path=norm_path(m.group(1)),
                    line=int(m.group(2)),
                )
            )
            pending = None
    return out


# --- mypy
_MYPY = re.compile(r"^([\w./\\-]{1,300}\.pyi?):(\d{1,7})(?::\d{1,5})?: error: (.{1,1500}?)(?:\s{2}\[([\w-]{1,60})\])?$")


def mypy(job_id: int, lines: Lines) -> list[Candidate]:
    out = []
    for no, text in lines:
        m = _MYPY.match(text)
        if m:
            out.append(
                Candidate(
                    "mypy",
                    "compile",
                    job_id,
                    no,
                    m.group(3).strip(),
                    code=m.group(4),
                    path=norm_path(m.group(1)),
                    line=int(m.group(2)),
                )
            )
    return out
