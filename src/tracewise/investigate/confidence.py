"""Confidence band + basis, computed by code (T-404; FS-DX-7, ADR-18, DECISIONS D-5).

The model's own confidence is never read. Inputs are deterministic facts:

* error_references_location: a retained log line of a failed job cites the location's file with a
  line inside [line_start-3, line_end+3] (pytest/ruff/mypy/eslint `path:N`, tsc `path(N,`, Python
  `File "…path", line N`, jest `(path:N:`).
* changed_line_at_location: the trigger diff's patch adds or changes a line inside the location.
* error_references_file: a retained log line cites the location's file at all.
* conflict: a compile or lint error (whose own location is definitive) points at another file.

Rule (D-5, the stricter reading of FS-DX-7 "the error references the location, or a changed line"):
  high   = diagnosed, location validated, no validation flags, no conflict, logs not truncated, and
           (error_references_location  OR  (changed_line_at_location AND error_references_file))
  medium = diagnosed, location validated (or a non-code category resting on a real error line), no conflict
  low    = everything else, including every non-diagnosed status
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from tracewise.context.trigger import TriggerDiff
from tracewise.contracts import CODE_CATEGORIES, Band, Category, Confidence, Location
from tracewise.prepass.primary import PrepassResult

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_DEFINITIVE_TOOLS = frozenset({"tsc", "mypy", "ruff", "eslint"})
__all__ = ["CODE_CATEGORIES", "assess", "changed_lines", "conflicts", "error_evidence"]


def changed_lines(diff: TriggerDiff) -> dict[str, set[int]]:
    """New-file line numbers added or changed by the trigger diff, from unified-diff patches."""
    out: dict[str, set[int]] = {}
    for f in diff.files:
        if not f.patch:
            continue
        lines: set[int] = set()
        new_no = 0
        in_hunk = False
        for raw in f.patch.splitlines():
            m = _HUNK.match(raw)
            if m:
                new_no = int(m.group(1))
                in_hunk = True
                continue
            if not in_hunk:
                continue  # file headers (`--- a/x`, `+++ b/x`) only occur before the first hunk
            # Inside a hunk the first character alone is the marker: a removed `---` (YAML) or an added `++i` is
            # still a change (Phase 57, F4).
            if raw.startswith("+"):
                lines.add(new_no)
                new_no += 1
            elif raw.startswith("-"):
                lines.add(new_no)  # deletion point counts as a change at that position
            elif raw.startswith("\\"):
                continue  # "\ No newline at end of file"
            else:
                new_no += 1
        out[f.path] = lines
    return out


def _line_refs(path: str, texts: Iterable[str]) -> tuple[bool, set[int]]:
    esc = re.escape(path)
    any_ref = re.compile(rf"(?:^|[\s\"'(/=]){esc}(?![\w/.-])")
    with_line = re.compile(rf"(?:^|[\s\"'(/=]){esc}(?::|\(|\"?, line )(\d{{1,7}})")
    found = False
    lines: set[int] = set()
    for t in texts:
        if path not in t:
            continue
        if any_ref.search(t):
            found = True
        lines.update(int(m.group(1)) for m in with_line.finditer(t))
    return found, lines


def error_evidence(pre: PrepassResult | None, loc: Location) -> tuple[bool, bool]:
    """(error_references_location, error_references_file) from retained failed-job logs and extractor data."""
    if pre is None:
        return False, False
    texts = [t for log in pre.logs.values() for _, t in log.ordered()]
    file_ref, lines = _line_refs(loc.path, texts)
    for g in pre.primaries:
        for c in g.members:
            if c.path == loc.path:
                file_ref = True
                if c.line is not None:
                    lines.add(c.line)
    near = any(loc.line_start - 3 <= n <= loc.line_end + 3 for n in lines)
    return near, file_ref


def conflicts(pre: PrepassResult | None, loc: Location) -> list[str]:
    if pre is None:
        return []
    others = sorted(
        {c.path for g in pre.primaries for c in [g.primary] if c.tool in _DEFINITIVE_TOOLS and c.path and c.path != loc.path}
    )
    mine = any(c.path == loc.path for g in pre.primaries for c in g.members)
    return [] if mine or not others else others


def assess(
    *,
    diagnosed: bool,
    reason: str | None,
    category: Category,
    location: Location | None,
    pre: PrepassResult | None,
    diff: TriggerDiff,
    flags: list[str],
    log_truncated: bool,
    has_error_line: bool,
) -> Confidence:
    if not diagnosed:
        return Confidence(band=Band.low, basis=[f"not_diagnosed:{reason or 'unknown'}"])
    basis: list[str] = []
    if location is None:
        basis.append("no_location")
        band = Band.medium if category not in CODE_CATEGORIES and has_error_line else Band.low
        basis.append("error_line_present" if has_error_line else "no_error_line")
        return Confidence(band=band, basis=basis)
    basis.append("location_examined")
    near, file_ref = error_evidence(pre, location)
    on_changed = any(location.line_start <= n <= location.line_end for n in changed_lines(diff).get(location.path, set()))
    if near:
        basis.append("error_references_location")
    if on_changed:
        basis.append("changed_line_at_location")
    if file_ref and not near:
        basis.append("error_references_file")
    clash = conflicts(pre, location)
    if clash:
        basis.append("conflicts_with_error_location:" + clash[0][:40])
        return Confidence(band=Band.low, basis=basis)
    if flags:
        basis.append(f"validation_flags:{len(flags)}")
    if log_truncated:
        basis.append("log_truncated")
    corroborated = near or (on_changed and file_ref)
    if corroborated and not flags and not log_truncated:
        return Confidence(band=Band.high, basis=basis)
    basis.append("not_corroborated" if not corroborated else "corroborated_but_degraded")
    return Confidence(band=Band.medium, basis=basis)
