"""Control-sequence stripping and secret redaction (T-202, FS-LOG-5).

Runs on every log line before storage, extraction or any LLM call. All patterns are
linear (no nested quantifiers) and lines are length-capped first (FS-DX-9).
"""

from __future__ import annotations

import math
import re
from collections import Counter

MAX_LINE_CHARS = 4096
REDACTED = "[REDACTED]"

_OSC = re.compile(r"\x1b\][^\x07\x1b]{0,8192}(?:\x07|\x1b\\)?")  # OSC 8 hyperlinks, titles
_CSI = re.compile(r"\x1b\[[0-?]{0,32}[ -/]{0,8}[@-~]")  # SGR colours, cursor moves
_ESC = re.compile(r"\x1b[@-Z\\-_]?")  # other two-byte escapes, bare ESC
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")  # C0 (keep \t) and C1


def strip_controls(line: str) -> str:
    """Remove ANSI/OSC/C1 sequences; resolve CR overwrites to the last segment."""
    line = line.rstrip("\r\n")
    if len(line) > MAX_LINE_CHARS * 2:
        line = line[: MAX_LINE_CHARS * 2]
    line = _OSC.sub("", line)
    line = _CSI.sub("", line)
    line = _ESC.sub("", line)
    if "\r" in line:
        segments = [s for s in line.split("\r") if s]
        line = segments[-1] if segments else ""
    line = _CTRL.sub("", line)
    return line[:MAX_LINE_CHARS]


_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----[^\n]{0,8192}"), REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)[A-Za-z0-9/+=]{40}"), r"\1" + REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}"), REDACTED),
    (re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,255}"), REDACTED),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,255}"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}"), REDACTED),
    # Credentials embedded in URLs (postgres://user:pass@host, https://x:token@github.com).
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]{0,20}://[^\s:/@]{1,256}:)[^\s@/]{1,512}@"), r"\1" + REDACTED + "@"),
    (re.compile(r"(?i)\b(authorization:\s*(?:bearer|token|basic)\s+)[^\s]{8,4096}"), r"\1" + REDACTED),
    (
        re.compile(
            r"(?i)\b((?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
            r"[\"']?\s*[=:]\s*[\"']?)[^\s\"',;]{4,512}"
        ),
        r"\1" + REDACTED,
    ),
]

_CANDIDATE = re.compile(r"[A-Za-z0-9+_=-]{32,512}")


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _looks_secret(tok: str) -> bool:
    # Hex (commit SHAs, hashes) is kept: it is needed for diagnosis and not a credential shape.
    if re.fullmatch(r"[0-9a-fA-F]+", tok):
        return False
    classes = sum(bool(re.search(p, tok)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))
    return classes == 3 and _entropy(tok) >= 4.2


def redact(line: str) -> str:
    """GitHub's own `***` masking is kept as is; then patterns, then high-entropy tokens."""
    for pat, repl in _PATTERNS:
        line = pat.sub(repl, line)
    return _CANDIDATE.sub(lambda m: REDACTED if _looks_secret(m.group(0)) else m.group(0), line)


def clean(line: str) -> str:
    return redact(strip_controls(line))
