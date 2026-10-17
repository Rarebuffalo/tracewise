"""Shared candidate model and helpers for extractors (FS-DX-9)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Kind = Literal["compile", "lint", "test", "exception", "missing_module", "install", "generic", "exit"]
Lines = Sequence[tuple[int, str]]  # (log line number, sanitised text)

_RUNNER_ROOT = re.compile(r"^(?:/home/runner/work/[^/]+/[^/]+/|/__w/[^/]+/[^/]+/|[A-Za-z]:\\a\\[^\\]+\\[^\\]+\\)")


@dataclass
class Candidate:
    tool: str
    kind: Kind
    job_id: int
    log_line: int
    message: str
    log_line_end: int | None = None
    code: str | None = None
    path: str | None = None
    line: int | None = None
    test: str | None = None
    module: str | None = None
    step_number: int = 0

    @property
    def span(self) -> tuple[int, int]:
        return self.log_line, self.log_line_end or self.log_line

    @property
    def label(self) -> str:
        if self.test:
            return self.test
        if self.path:
            return f"{self.path}:{self.line}" if self.line else self.path
        return self.message[:80]


def norm_path(p: str) -> str:
    p = _RUNNER_ROOT.sub("", p.strip().strip("\"'"))
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def module_key(spec: str) -> str:
    """'./utils/format.js' -> 'format'; 'foo.bar' -> 'bar'."""
    base = re.split(r"[/.]", spec.strip("'\"").rstrip("/"))
    parts = [b for b in base if b and b not in ("js", "ts", "tsx", "jsx", "mjs", "cjs", "py")]
    return parts[-1] if parts else spec
