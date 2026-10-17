"""TypeScript extractors: tsc, jest, vitest, eslint (T-204)."""

from __future__ import annotations

import re

from tracewise.prepass.extractors.base import Candidate, Lines, module_key, norm_path

_TS_EXT = r"\.(?:[cm]?[jt]sx?|vue|svelte)"

# --- tsc: `src/a.ts(3,10): error TS2305: ...` and pretty `src/a.ts:3:10 - error TS2305: ...`
_TSC = re.compile(
    rf"^([\w@./\\-]{{1,300}}{_TS_EXT})(?:\((\d{{1,7}}),\d{{1,5}}\):|:(\d{{1,7}}):\d{{1,5}} -) error (TS\d{{3,5}}): (.{{1,2000}})$"
)
_TS_NO_MODULE = re.compile(r"Cannot find module '([^']{1,300})'")


def tsc(job_id: int, lines: Lines) -> list[Candidate]:
    out = []
    for no, text in lines:
        m = _TSC.match(text)
        if not m:
            continue
        msg = m.group(5).strip()
        mod = _TS_NO_MODULE.search(msg)
        out.append(
            Candidate(
                "tsc",
                "compile",
                job_id,
                no,
                msg,
                code=m.group(4),
                path=norm_path(m.group(1)),
                line=int(m.group(2) or m.group(3)),
                module=module_key(mod.group(1)) if mod else None,
            )
        )
    return out


# --- jest
_JEST_FILE = re.compile(rf"^FAIL ([\w@./\\-]{{1,300}}{_TS_EXT})(?: \(.{{0,40}}\))?$")
_JEST_TEST = re.compile(r"^\s{0,4}● (.{1,500})$")
_JEST_AT = re.compile(rf"\bat (?:.{{0,300}} \()?([\w@./\\-]{{1,300}}{_TS_EXT}):(\d{{1,7}}):\d{{1,5}}\)?$")
_JEST_NO_MODULE = re.compile(r"Cannot find module '([^']{1,300})' from '([^']{1,300})'")


def jest(job_id: int, lines: Lines) -> list[Candidate]:
    out: list[Candidate] = []
    current_file: str | None = None
    cur: Candidate | None = None
    for no, text in lines:
        m = _JEST_FILE.match(text.strip())
        if m:
            current_file, cur = norm_path(m.group(1)), None
            continue
        m = _JEST_TEST.match(text)
        if m:
            name = m.group(1).strip()
            cur = Candidate(
                "jest", "test", job_id, no, "", test=f"{current_file} › {name}" if current_file else name, path=current_file
            )
            out.append(cur)
            continue
        if cur is None:
            continue
        stripped = text.strip()
        if not cur.message and stripped:
            nm = _JEST_NO_MODULE.search(stripped)
            cur.message = stripped[:2000]
            cur.log_line_end = no
            if nm:
                cur.kind, cur.module, cur.code = "missing_module", module_key(nm.group(1)), "MODULE_NOT_FOUND"
            elif "toMatchSnapshot" in stripped or "toMatchInlineSnapshot" in stripped:
                cur.code = "snapshot"
            continue
        am = _JEST_AT.search(stripped)
        if am and "node_modules" not in am.group(1) and cur.line is None:
            cur.path, cur.line = norm_path(am.group(1)), int(am.group(2))
    return [c for c in out if c.message and "Test suite failed to run" != c.message]


# --- vitest
_VITEST_HEAD = re.compile(rf"^\s{{0,2}}FAIL\s{{1,4}}([\w@./\\-]{{1,300}}{_TS_EXT})(?: > (.{{1,500}}))?$")
_VITEST_AT = re.compile(rf"^\s{{0,8}}❯ ([\w@./\\-]{{1,300}}{_TS_EXT}):(\d{{1,7}}):\d{{1,5}}$")
_VITEST_ERR = re.compile(r"^\s{0,4}([A-Z]\w{0,80}(?:Error|Exception)): ?(.{0,2000})$")


def vitest(job_id: int, lines: Lines) -> list[Candidate]:
    out: list[Candidate] = []
    cur: Candidate | None = None
    for no, text in lines:
        m = _VITEST_HEAD.match(text)
        if m and m.group(2):
            path = norm_path(m.group(1))
            cur = Candidate("vitest", "test", job_id, no, "", test=f"{path} > {m.group(2).strip()}", path=path)
            out.append(cur)
            continue
        if cur is None:
            continue
        em = _VITEST_ERR.match(text)
        if em and not cur.message:
            cur.code, cur.message, cur.log_line_end = em.group(1), f"{em.group(1)}: {em.group(2).strip()}", no
            nm = re.search(r"Cannot find module '([^']{1,300})'", text)
            if nm:
                cur.kind, cur.module = "missing_module", module_key(nm.group(1))
            continue
        am = _VITEST_AT.match(text)
        if am and cur.line is None and "node_modules" not in am.group(1):
            cur.path, cur.line = norm_path(am.group(1)), int(am.group(2))
    return [c for c in out if c.message]


# --- eslint (stylish and compact/unix)
_ESLINT_FILE = re.compile(rf"^((?:/|[A-Za-z]:\\)[^\s]{{1,500}}{_TS_EXT}|[\w@./\\-]{{1,300}}{_TS_EXT})$")
_ESLINT_ROW = re.compile(r"^\s{1,4}(\d{1,7}):\d{1,5}\s{1,4}error\s{1,4}(.{1,1000}?)\s{2,}([@\w/-]{1,100})$")
_ESLINT_COMPACT = re.compile(
    rf"^([^\s:]{{1,500}}{_TS_EXT}): line (\d{{1,7}}), col \d{{1,5}}, Error - (.{{1,1000}}?) \(([@\w/-]{{1,100}})\)$"
)


def eslint(job_id: int, lines: Lines) -> list[Candidate]:
    out = []
    current: str | None = None
    for no, text in lines:
        m = _ESLINT_FILE.match(text.strip()) if not text.startswith(" ") else None
        if m:
            current = norm_path(m.group(1))
            continue
        m = _ESLINT_ROW.match(text)
        if m and current:
            out.append(
                Candidate("eslint", "lint", job_id, no, m.group(2).strip(), code=m.group(3), path=current, line=int(m.group(1)))
            )
            continue
        m = _ESLINT_COMPACT.match(text)
        if m:
            out.append(
                Candidate(
                    "eslint",
                    "lint",
                    job_id,
                    no,
                    m.group(3).strip(),
                    code=m.group(4),
                    path=norm_path(m.group(1)),
                    line=int(m.group(2)),
                )
            )
    return out
