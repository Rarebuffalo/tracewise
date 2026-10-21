"""Dependency drift with structured corroboration (T-903; FS-ATR-4; AT-ATR-08). P2: computed, NOT yet published.

Two situations are told apart, from structured evidence only:

* **Manifest change** (B-06): the trigger diff changed a dependency declaration or lock entry. The change is
  corroborated when the failing step's error names one of the changed packages.
* **Upstream drift** (B-05): no dependency declaration changed, the error names a package, and that package's
  installed version differs between the last green run's install output and this run's. Without both install
  outputs the drift is reported as uncorroborated, never guessed.

Inputs are untrusted (patches are repository content, logs are CI output). Package names are validated against a
strict pattern and normalised (PEP 503 style); versions are bounded strings. Parsing is bounded per file and in total.
ADR-13: the result is a signal, never proof, and its statements never use causal wording. Nothing here reaches
GitHub or a published report.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from tracewise.context.trigger import TriggerDiff

MAX_PATCH_LINES = 5000  # per file
MAX_CHANGES = 200
MAX_LOG_LINES = 20_000
_VERSION_MAX = 64

_NAME = re.compile(r"[A-Za-z0-9@](?:[A-Za-z0-9._/@-]{0,212}[A-Za-z0-9])?")
_REQ_FILE = re.compile(r"(?:^|/)(?:(?:requirements|constraints)[\w.-]*|requirements/[\w.-]+)\.(?:txt|in)$")
_PY_LOCKS = frozenset({"poetry.lock", "uv.lock", "pdm.lock"})
_JS_MANIFEST = "package.json"
_JS_LOCK = "package-lock.json"


def normalise(name: str) -> str:
    """PEP 503-style: case-insensitive, runs of `-_.` equal. Scoped npm names keep their `@scope/`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _valid(name: str) -> str | None:
    name = name.strip()
    return normalise(name) if _NAME.fullmatch(name) else None


def _version(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().strip("\"',")
    return v[:_VERSION_MAX] if v and not any(c.isspace() for c in v) else None


@dataclass(frozen=True)
class DependencyChange:
    package: str  # normalised
    file: str
    old: str | None  # specifier or locked version before; None when added
    new: str | None  # after; None when removed


@dataclass(frozen=True)
class DriftSignal:
    kind: str  # manifest_change | upstream_drift | none | unknown
    corroborated: bool
    statement: str
    changes: tuple[DependencyChange, ...] = ()
    implicated_packages: tuple[str, ...] = ()
    basis: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ manifest and lock patches


def dependency_file_kind(path: str) -> str | None:
    name = PurePosixPath(path).name
    if _REQ_FILE.search(path):
        return "requirements"
    if name == "pyproject.toml":
        return "pyproject"
    if name in _PY_LOCKS:
        return "toml_lock"
    if name == _JS_MANIFEST:
        return "package_json"
    if name == _JS_LOCK:
        return "package_lock"
    if name == "go.mod":
        return "go_mod"
    return None


_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*((?:[<>=!~]=?|===)\s*[^;#\s]+(?:\s*,\s*[<>=!~]=?\s*[^;#\s,]+)*)?"
)
_PYPROJECT_DEP = re.compile(r"""^\s*["']([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([<>=!~][^"';]*)?["']\s*,?\s*$""")
_POETRY_DEP = re.compile(r"""^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*["']([^"']+)["']\s*$""")
_JSON_DEP = re.compile(r"""^\s*"((?:@[a-z0-9._-]+/)?[a-z0-9._-]+)"\s*:\s*"([^"]+)"\s*,?\s*$""", re.IGNORECASE)
_GO_REQ = re.compile(r"^\s*(?:require\s+)?([a-z0-9.-]+\.[a-z]{2,}/[A-Za-z0-9._/~-]+)\s+(v[0-9][^\s]*)")


def _line_entry(kind: str, line: str) -> tuple[str, str | None] | None:
    """(package, specifier) declared on one manifest line, or None. Lock files are handled per block."""
    if kind == "requirements":
        if line.lstrip().startswith(("#", "-")):
            return None
        m = _REQ_LINE.match(line)
        return (m.group(1), (m.group(2) or "").replace(" ", "") or None) if m else None
    if kind == "pyproject":
        m = _PYPROJECT_DEP.match(line) or _POETRY_DEP.match(line)
        if not m or m.group(1) in {"python", "name", "version", "description", "requires-python", "build-backend"}:
            return None
        return m.group(1), (m.group(2) or "").replace(" ", "") or None
    if kind == "package_json":
        m = _JSON_DEP.match(line)
        if not m or m.group(1) in {"name", "version", "description", "main", "license", "type", "private", "node", "npm"}:
            return None
        return m.group(1), m.group(2)
    if kind == "go_mod":
        m = _GO_REQ.match(line)
        return (m.group(1), m.group(2)) if m else None
    return None


def _patch_sides(patch: str) -> tuple[list[str], list[str], list[str]]:
    """(removed, added, context) lines of a unified-diff hunk body, bounded."""
    removed: list[str] = []
    added: list[str] = []
    context: list[str] = []
    for i, line in enumerate(patch.splitlines()):
        if i >= MAX_PATCH_LINES:
            break
        if line.startswith(("@@", "+++", "---", "\\")):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
        else:
            context.append(line[1:] if line.startswith(" ") else line)
    return removed, added, context


def _lock_versions(lines: list[str], kind: str) -> dict[str, str]:
    """Package → version for the lock blocks visible in a patch side (`name = "x"` then `version = "y"` in TOML
    locks; `"node_modules/x": {` then `"version": "y"` in package-lock.json)."""
    out: dict[str, str] = {}
    current: str | None = None
    for line in lines:
        s = line.strip()
        if kind == "toml_lock":
            if s == "[[package]]":
                current = None
            elif m := re.fullmatch(r'name\s*=\s*"([^"]+)"', s):
                current = _valid(m.group(1))
            elif (m := re.fullmatch(r'version\s*=\s*"([^"]+)"', s)) and current and (v := _version(m.group(1))):
                out[current] = v
                current = None
        elif kind == "package_lock":
            if m := re.fullmatch(r'"(?:[^"]*/)?node_modules/((?:@[^"/]+/)?[^"/]+)"\s*:\s*\{', s):
                current = _valid(m.group(1))
            elif (m := re.fullmatch(r'"version"\s*:\s*"([^"]+)",?', s)) and current and (v := _version(m.group(1))):
                out[current] = v
                current = None
    return out


def _diff_maps(path: str, before: dict[str, str | None], after: dict[str, str | None]) -> list[DependencyChange]:
    out: list[DependencyChange] = []
    for pkg in sorted(set(before) | set(after)):
        old, new = before.get(pkg), after.get(pkg)
        if pkg in before and pkg in after and old == new:
            continue
        out.append(DependencyChange(pkg, path, old if pkg in before else None, new if pkg in after else None))
    return out


def _side_in_order(patch: str, keep: str) -> list[str]:
    """One side of the patch in its original order: context lines plus the lines starting with `keep`."""
    out: list[str] = []
    for i, line in enumerate(patch.splitlines()):
        if i >= MAX_PATCH_LINES:
            break
        if line.startswith(("@@", "+++", "---", "\\")):
            continue
        if line.startswith(keep):
            out.append(line[1:])
        elif not line.startswith(("+", "-")):
            out.append(line[1:] if line.startswith(" ") else line)
    return out


def manifest_changes(diff: TriggerDiff) -> tuple[list[DependencyChange], list[str]]:
    """Dependency changes in the trigger diff, and the dependency files whose versions could not be read (no
    patch: binary, too large, or omitted by GitHub)."""
    changes: list[DependencyChange] = []
    unreadable: list[str] = []
    for f in diff.files:
        kind = dependency_file_kind(f.path)
        if kind is None:
            continue
        if f.patch is None:
            unreadable.append(f.path)
            continue
        if kind in ("toml_lock", "package_lock"):
            before = _lock_versions(_side_in_order(f.patch, "-"), kind)
            after = _lock_versions(_side_in_order(f.patch, "+"), kind)
            found = _diff_maps(f.path, dict(before.items()), dict(after.items()))
        else:
            removed, added, _ = _patch_sides(f.patch)
            b: dict[str, str | None] = {}
            a: dict[str, str | None] = {}
            for side, target in ((removed, b), (added, a)):
                for line in side:
                    entry = _line_entry(kind, line)
                    if entry and (pkg := _valid(entry[0])):
                        target[pkg] = _version(entry[1])
            found = _diff_maps(f.path, b, a)
        changes.extend(found)
        if len(changes) >= MAX_CHANGES:
            return changes[:MAX_CHANGES], unreadable
    return changes, unreadable


# ------------------------------------------------------------------ what the error names, what was installed

_IMPLICATING = (
    re.compile(r"AttributeError: module '([A-Za-z0-9_.]+)' has no attribute"),
    re.compile(r"ModuleNotFoundError: No module named '([A-Za-z0-9_.]+)'"),
    re.compile(r"ImportError: cannot import name '[^']+' from '([A-Za-z0-9_.]+)'"),
    re.compile(r"The user requested ([A-Za-z0-9][A-Za-z0-9._-]*)"),
    re.compile(r"^\s+([A-Za-z0-9][A-Za-z0-9._-]*) [0-9][^\s]* depends on ([A-Za-z0-9][A-Za-z0-9._-]*)"),
    re.compile(r"Cannot install .* and ([A-Za-z0-9][A-Za-z0-9._-]*)[<>=!~]"),
    re.compile(r"Could not find a version that satisfies the requirement ([A-Za-z0-9][A-Za-z0-9._-]*)"),
    re.compile(r"No matching distribution found for ([A-Za-z0-9][A-Za-z0-9._-]*)"),
    re.compile(r"npm (?:ERR!|error) (?:peer|Could not resolve dependency:.*?) ((?:@[a-z0-9._-]+/)?[a-z0-9._-]+)@"),
    re.compile(r"Cannot find module '((?:@[a-z0-9._-]+/)?[a-z0-9._-]+)"),
)


def implicated_packages(lines: Iterable[str]) -> set[str]:
    """Packages named by error lines (top-level module for `a.b`). Import names are compared as written; a
    distribution whose import name differs (e.g. `PyYAML`/`yaml`) is not matched, by design."""
    out: set[str] = set()
    for i, line in enumerate(lines):
        if i >= MAX_LOG_LINES:
            break
        for rx in _IMPLICATING:
            for m in rx.finditer(line):
                for g in m.groups():
                    if g and (n := _valid(g.split(".")[0] if not g.startswith("@") else g)):
                        out.add(n)
    return out


_PIP_DONE = re.compile(r"^Successfully installed (.+)$")
_PIP_DIST = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._]*)-([0-9][A-Za-z0-9.+!]*)$")
_PIN = re.compile(r"^\s*[+]?\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.+!]*)\s*$")  # uv "+ foo==2.0.0"
_NPM = re.compile(r"^\s*[+]\s*((?:@[a-z0-9._-]+/)?[a-z0-9._-]+)@([0-9][^\s]*)\s*$")


def installed_versions(lines: Iterable[str]) -> dict[str, str]:
    """Package → version from installer output (pip `Successfully installed a-1 b-2`, uv `+ a==1`, npm `+ a@1`)."""
    out: dict[str, str] = {}
    for i, raw in enumerate(lines):
        if i >= MAX_LOG_LINES:
            break
        line = raw.rstrip()
        if m := _PIP_DONE.match(line.strip()):
            for token in m.group(1).split():
                if (d := _PIP_DIST.match(token)) and (n := _valid(d.group(1))) and (v := _version(d.group(2))):
                    out[n] = v
        elif (m := _PIN.match(line) or _NPM.match(line)) and (n := _valid(m.group(1))) and (v := _version(m.group(2))):
            out[n] = v
    return out


# ------------------------------------------------------------------ the signal


def _fmt(c: DependencyChange) -> str:
    return f"{c.package} ({c.old or 'not declared'} → {c.new or 'removed'}) in {c.file}"


def assess(
    diff: TriggerDiff,
    error_lines: Iterable[str],
    *,
    installed_now: Iterable[str] | None = None,
    installed_last_green: Iterable[str] | None = None,
) -> DriftSignal:
    """AT-ATR-08. `error_lines`: the failing step's redacted error lines. `installed_*`: install output of this run
    and of the lane's last green run (T-901), when available."""
    implicated = sorted(implicated_packages(error_lines))
    if not diff.known:
        return DriftSignal(
            "unknown",
            False,
            "The trigger diff is unknown, so dependency changes cannot be assessed.",
            implicated_packages=tuple(implicated),
            basis=["trigger_diff_unknown"],
        )
    changes, unreadable = manifest_changes(diff)
    if changes or unreadable:
        hit = [c for c in changes if c.package in implicated]
        if hit:
            shown = "; ".join(_fmt(c) for c in hit[:3])
            return DriftSignal(
                "manifest_change",
                True,
                f"This push changed a dependency the failing step names: {shown} (a signal, not proof).",
                tuple(changes),
                tuple(implicated),
                ["trigger_diff", "dependency_files", "error_lines"],
            )
        what = (
            f"changed {len(changes)} dependency declaration(s)"
            if changes
            else f"changed dependency files whose versions could not be read ({', '.join(unreadable[:3])})"
        )
        return DriftSignal(
            "manifest_change",
            False,
            f"This push {what}; none is named by the failing step's error.",
            tuple(changes),
            tuple(implicated),
            ["trigger_diff", "dependency_files"],
        )
    if diff.truncated:
        return DriftSignal(
            "unknown",
            False,
            "The trigger diff is truncated; dependency changes cannot be ruled out.",
            implicated_packages=tuple(implicated),
            basis=["trigger_diff_truncated"],
        )
    if not implicated:
        return DriftSignal(
            "none", False, "No dependency file changed and the error names no package.", basis=["trigger_diff", "error_lines"]
        )
    if installed_now is None or installed_last_green is None:
        return DriftSignal(
            "upstream_drift",
            False,
            f"No dependency file changed; the error names {', '.join(implicated[:3])}, but install "
            "output to compare versions is unavailable (uncorroborated).",
            implicated_packages=tuple(implicated),
            basis=["trigger_diff", "error_lines"],
        )
    now, before = installed_versions(installed_now), installed_versions(installed_last_green)
    moved = [
        DependencyChange(p, "(installed)", before[p], now[p])
        for p in implicated
        if p in now and p in before and now[p] != before[p]
    ]
    if moved:
        shown = "; ".join(f"{c.package} {c.old} → {c.new}" for c in moved[:3])
        return DriftSignal(
            "upstream_drift",
            True,
            f"No dependency file changed, but the installed version moved since the last green run: "
            f"{shown} (a signal, not proof).",
            tuple(moved),
            tuple(implicated),
            ["trigger_diff", "error_lines", "install_output"],
        )
    return DriftSignal(
        "none",
        False,
        "No dependency file changed and the named packages were installed at the same versions as in "
        "the last green run (or were not listed).",
        implicated_packages=tuple(implicated),
        basis=["trigger_diff", "error_lines", "install_output"],
    )
