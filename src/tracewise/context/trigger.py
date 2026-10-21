"""Trigger diff and `touches_implicated` (T-306; FS-CTX-3, FS-ATR-1, FS-SEC-2, ADR-18).

`compute_trigger_diff` asks the compare API for the files changed by the run's commit: against its
first parent (push), or against a supplied base (PR: the base branch SHA; a three-dot compare is
relative to the merge base). Truncation is flagged (≤300 files, ≤250 commits).

`relevance` is computed by code only and is **a signal, not proof**. Callers must pass every
implicated path known at that point: the pre-pass locations **and** the validated diagnosis
location (T-403). With an incomplete set, "not implicated" could wrongly exonerate a push, so:
truncated diffs, unknown diffs and empty implicated sets yield `None` (unknown), never `False`.
Statements never say "caused"; they only describe overlap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from tracewise.context.paths import UnsafePath, validate_repo_path, validate_sha
from tracewise.contracts import Attribution
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient

MAX_FILES = 300
MAX_COMMITS = 250
MAX_LISTED = 100


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    previous_path: str | None = None
    patch: str | None = None  # untrusted repository content


@dataclass(frozen=True)
class TriggerDiff:
    head_sha: str
    base_sha: str | None
    files: tuple[ChangedFile, ...] = ()
    truncated: bool = False
    known: bool = True
    reason: str | None = None

    def changed_paths(self) -> set[str]:
        out = {f.path for f in self.files}
        out |= {f.previous_path for f in self.files if f.previous_path}
        return out

    def render(self, max_chars: int = 8000) -> str:
        """Text for the `get_diff` tool. Patches are untrusted data; the investigator delimits them."""
        if not self.known:
            return f"trigger diff unavailable: {self.reason}"
        head = [
            f"trigger {self.head_sha[:12]} vs {(self.base_sha or '?')[:12]}: {len(self.files)} file(s) changed"
            + (" (TRUNCATED)" if self.truncated else "")
        ]
        head += [f"{f.status[:1].upper()} {f.path} (+{f.additions} -{f.deletions})" for f in self.files[:MAX_LISTED]]
        text = "\n".join(head)
        for f in self.files:
            if f.patch and len(text) < max_chars:
                text += f"\n--- {f.path}\n{f.patch}"
        return text if len(text) <= max_chars else text[:max_chars] + "\n… (diff truncated)"


def _unknown(head: str, base: str | None, reason: str) -> TriggerDiff:
    return TriggerDiff(head, base, known=False, reason=reason)


def compute_trigger_diff(rc: RepoClient, head_sha: str, *, base_sha: str | None = None) -> TriggerDiff:
    validate_sha(head_sha)
    try:
        if base_sha is None:
            commit = rc.request("get_commit", sha=head_sha)
            parents = commit.get("parents") if isinstance(commit, dict) else None
            if not isinstance(parents, list):
                return _unknown(head_sha, None, "unexpected commit response")
            if not parents:
                return _unknown(head_sha, None, "root commit (no parent to compare with)")
            first = parents[0]
            if not isinstance(first, dict) or not isinstance(first.get("sha"), str):
                return _unknown(head_sha, None, "unexpected commit response")  # never index an unexpected shape
            base_sha = first["sha"]
        validate_sha(base_sha)
        doc = rc.request("compare", basehead=f"{base_sha}...{head_sha}")
    except UnsafePath:
        return _unknown(head_sha, base_sha, "invalid base or head SHA")
    except (gh_err.GitHubPermanent, gh_err.GitHubRetryable) as e:
        return _unknown(head_sha, base_sha, f"compare unavailable ({type(e).__name__})")
    return _parse_compare(doc, head_sha, base_sha)


def _count(v: Any) -> int:
    """A non-negative line count from untrusted JSON; anything else counts as 0 (never raises)."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def _parse_compare(doc: Any, head_sha: str, base_sha: str) -> TriggerDiff:
    if not isinstance(doc, dict) or not isinstance(doc.get("files", []), list):
        return _unknown(head_sha, base_sha, "unexpected compare response")
    files: list[ChangedFile] = []
    for f in doc.get("files", []):
        if not isinstance(f, dict):
            continue
        try:
            path = validate_repo_path(str(f.get("filename", "")))
        except UnsafePath:
            continue
        prev = f.get("previous_filename")
        try:
            prev_ok = validate_repo_path(prev) if isinstance(prev, str) else None
        except UnsafePath:
            prev_ok = None
        files.append(
            ChangedFile(
                path,
                str(f.get("status", "modified")),
                _count(f.get("additions")),
                _count(f.get("deletions")),
                prev_ok,
                f.get("patch") if isinstance(f.get("patch"), str) else None,
            )
        )
    commits = doc.get("total_commits")
    truncated = len(files) >= MAX_FILES or (isinstance(commits, int) and commits > MAX_COMMITS)
    return TriggerDiff(head_sha, base_sha, tuple(files), truncated)


@dataclass(frozen=True)
class Relevance:
    touches_implicated: bool | None
    statement: str
    overlap: tuple[str, ...] = ()
    basis: list[str] = field(default_factory=list)


def _names(paths: list[str]) -> str:
    shown = paths[:3]
    rest = len(paths) - len(shown)
    return ", ".join(shown) + (f" and {rest} more" if rest > 0 else "")


def relevance(diff: TriggerDiff, implicated: Iterable[str]) -> Relevance:
    implicated_set: set[str] = set()
    for p in implicated:
        try:
            implicated_set.add(validate_repo_path(p))
        except UnsafePath:
            continue
    if not diff.known:
        return Relevance(
            None, "Could not determine which files this push changed; relevance is unknown.", basis=["trigger_diff_unknown"]
        )
    if not implicated_set:
        return Relevance(
            None, "No implicated file was identified, so the relevance of this push is unknown.", basis=["no_implicated_paths"]
        )
    changed = sorted(diff.changed_paths())
    overlap = sorted(diff.changed_paths() & implicated_set)
    if overlap:
        verb = "is" if len(overlap) == 1 else "are"
        return Relevance(
            True,
            f"This push changed {_names(overlap)}, which {verb} implicated (a signal, not proof).",
            tuple(overlap),
            ["trigger_diff", "implicated_paths"],
        )
    if diff.truncated:
        return Relevance(
            None,
            "The diff of this push is truncated and shows no implicated file; relevance is unknown.",
            basis=["trigger_diff_truncated"],
        )
    if not changed:
        return Relevance(
            False,
            "This push changed no files; not implicated; likely pre-dates this push.",
            basis=["trigger_diff", "implicated_paths"],
        )
    return Relevance(
        False,
        f"This push changed only {_names(changed)}; not implicated; likely pre-dates this push.",
        basis=["trigger_diff", "implicated_paths"],
    )


def to_attribution(diff: TriggerDiff, rel: Relevance) -> Attribution:
    return Attribution(
        trigger_sha=diff.head_sha,
        trigger_changed_files=sorted(diff.changed_paths())[:MAX_LISTED],
        touches_implicated=rel.touches_implicated,
        statement=rel.statement[:400],
        basis=rel.basis,
    )
