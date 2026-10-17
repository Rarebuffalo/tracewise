"""Read-only investigation tools (T-305; FS-CTX-2, FS-CTX-5, FS-DX-3).

`read_file`, `grep`, `list_dir` and `get_diff` over one `CodeSource` at one commit. There are no
write, execute or network tools. Every call is logged; `files_examined()` is derived **only** from
successful `read_file` calls (repo-relative, true ranges, end ≤ EOF), never from model text.
Tool output is untrusted repository data; the investigator must delimit it (FS-SEC-1).
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from tracewise.context.paths import UnsafePath, validate_repo_path
from tracewise.context.source import CodeSource, ReadStatus

TOOL_NAMES = ("read_file", "grep", "list_dir", "get_diff")


@dataclass(frozen=True)
class ToolLimits:
    max_calls: int = 12
    max_output_chars: int = 8000
    max_read_lines: int = 250
    max_list_entries: int = 300
    grep_max_matches: int = 50
    grep_max_files: int = 400
    grep_max_bytes: int = 8 * 1024 * 1024
    grep_timeout_s: float = 5.0
    grep_max_line_chars: int = 240
    max_pattern_chars: int = 200


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str
    status: str = "ok"


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any]
    result: ToolResult
    examined: tuple[str, int, int] | None = None  # (path, start, end) for successful read_file


@dataclass
class ToolBox:
    source: CodeSource
    diff_text: str | None = None
    limits: ToolLimits = field(default_factory=ToolLimits)
    log: list[ToolCall] = field(default_factory=list)

    @property
    def calls_left(self) -> int:
        return self.limits.max_calls - len(self.log)

    @property
    def budget_exhausted(self) -> bool:
        return self.calls_left <= 0

    # ------------------------------------------------------------ dispatch

    def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        """Single entry point for the investigator. Unknown tools and bad args are errors, not exceptions."""
        if self.budget_exhausted:
            return ToolResult(False, "tool-call budget exhausted", "budget_exhausted")
        handlers: dict[str, Callable[..., tuple[ToolResult, tuple[str, int, int] | None]]] = {
            "read_file": self._read_file,
            "grep": self._grep,
            "list_dir": self._list_dir,
            "get_diff": self._get_diff,
        }
        handler = handlers.get(tool)
        if handler is None:
            res, examined = ToolResult(False, f"unknown tool {tool!r}", "unknown_tool"), None
        else:
            try:
                res, examined = handler(**args)
            except TypeError:
                res, examined = ToolResult(False, "invalid arguments", "invalid_args"), None
        res = self._cap(res)
        self.log.append(ToolCall(tool, dict(args), res, examined))
        return res

    def files_examined(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in self.log:
            if c.examined and {"path": c.examined[0], "start": c.examined[1], "end": c.examined[2]} not in out:
                out.append({"path": c.examined[0], "start": c.examined[1], "end": c.examined[2]})
        return out

    # ------------------------------------------------------------ tools

    def _read_file(self, path: str, start: int = 1, end: int | None = None) -> tuple[ToolResult, tuple[str, int, int] | None]:
        if not isinstance(start, int) or (end is not None and not isinstance(end, int)) or start < 1:
            return ToolResult(False, "start/end must be positive integers", "invalid_args"), None
        r = self.source.read(path)
        if r.status is not ReadStatus.ok or r.text is None or r.path is None:
            return ToolResult(False, f"{path}: {r.status.value}", r.status.value), None
        lines = r.text.splitlines()
        if not lines:
            return ToolResult(True, f"{r.path}: (empty file)"), None
        if start > len(lines):
            return ToolResult(False, f"{r.path}: start {start} is beyond EOF ({len(lines)} lines)", "beyond_eof"), None
        stop = min(
            len(lines),
            end if end is not None and end >= start else start + self.limits.max_read_lines - 1,
            start + self.limits.max_read_lines - 1,
        )
        body = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, stop + 1))
        header = f"{r.path} lines {start}-{stop} of {len(lines)}" + (f" (via symlink {path})" if r.path != path else "")
        return ToolResult(True, f"{header}\n{body}"), (r.path, start, stop)

    def _list_dir(self, path: str = "") -> tuple[ToolResult, None]:
        try:
            rel = validate_repo_path(path, allow_root=True)
        except UnsafePath:
            return ToolResult(False, f"{path}: invalid_path", "invalid_path"), None
        if rel not in self.source.directories():
            return ToolResult(False, f"{path}: not a directory", "not_found"), None
        prefix = f"{rel}/" if rel else ""
        children: dict[str, str] = {}
        for p, e in self.source.entries().items():
            if not p.startswith(prefix):
                continue
            head, sep, _ = p[len(prefix) :].partition("/")
            if sep:
                children.setdefault(head + "/", "dir")
            else:
                children[head] = {
                    "file": f"file {e.size if e.size is not None else '>limit'} B",
                    "symlink": "symlink",
                    "submodule": "submodule (not inspected)",
                }[e.kind]
        names = sorted(children)
        shown = names[: self.limits.max_list_entries]
        body = "\n".join(f"{n}\t{children[n]}" for n in shown)
        more = f"\n… {len(names) - len(shown)} more" if len(names) > len(shown) else ""
        return ToolResult(True, f"{rel or '.'}/\n{body}{more}"), None

    def _grep(self, pattern: str, glob: str | None = None, ignore_case: bool = False) -> tuple[ToolResult, None]:
        if not isinstance(pattern, str) or not 0 < len(pattern) <= self.limits.max_pattern_chars or "\x00" in pattern:
            return ToolResult(False, "pattern must be 1-200 characters", "invalid_args"), None
        if glob is not None and (not isinstance(glob, str) or len(glob) > 200 or "\x00" in glob or glob.startswith("/")):
            return ToolResult(False, "invalid glob", "invalid_args"), None
        files: list[list[str]] = []
        size = 0
        candidates = [
            e
            for p, e in sorted(self.source.entries().items())
            if e.kind == "file" and (glob is None or PurePosixPath(p).match(glob) or fnmatch.fnmatchcase(p, glob))
        ]
        for e in candidates[: self.limits.grep_max_files]:
            if e.size is None or e.size > self.source.limits.max_file_bytes or size + e.size > self.limits.grep_max_bytes:
                continue
            r = self.source.read(e.path)
            if r.status is ReadStatus.ok and r.text is not None:
                files.append([e.path, r.text])
                size += len(r.text)
        partial = len(candidates) > self.limits.grep_max_files
        req = json.dumps(
            {
                "pattern": pattern,
                "ignore_case": bool(ignore_case),
                "files": files,
                "max_matches": self.limits.grep_max_matches,
                "max_line_chars": self.limits.grep_max_line_chars,
            }
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-m", "tracewise.context.grep_worker"],
                input=req.encode(),
                capture_output=True,
                timeout=self.limits.grep_timeout_s,
                check=False,
                cwd="/",
                env={},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "grep timed out (pattern too expensive)", "timeout"), None
        try:
            out = json.loads(proc.stdout or b"{}")
        except ValueError:
            out = {}
        if proc.returncode != 0 or "error" in out or "matches" not in out:
            status = "invalid_pattern" if out.get("error") == "invalid pattern" else "grep_failed"
            return ToolResult(False, f"grep failed: {status}", status), None
        lines = [f"{p}:{n}: {t}" for p, n, t in out["matches"]]
        notes = []
        if out.get("truncated"):
            notes.append(f"(first {self.limits.grep_max_matches} matches)")
        if partial:
            notes.append(f"(searched the first {self.limits.grep_max_files} matching files)")
        body = "\n".join(lines) if lines else "no matches"
        return ToolResult(True, body + ("\n" + " ".join(notes) if notes else "")), None

    def _get_diff(self) -> tuple[ToolResult, None]:
        if self.diff_text is None:
            return ToolResult(False, "no trigger diff available", "unavailable"), None
        return ToolResult(True, self.diff_text), None

    def _cap(self, res: ToolResult) -> ToolResult:
        if len(res.content) <= self.limits.max_output_chars:
            return res
        return ToolResult(res.ok, res.content[: self.limits.max_output_chars] + "\n… (output truncated)", res.status)
