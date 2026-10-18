"""Fixture repositories for benchmark cases (T-601).

`snapshot()` reconstructs each commit's tree in pure Python (C0 full tree + overlays), used by the
scorer and integrity checks. `build_repo()` materialises the same trees as a real git repository with
fixed identities and dates, so commit SHAs are reproducible, plus a bare clone the harness serves to the
real `GitFetcher`. Symlinks are declared in case.yaml (`symlinks:` per commit) and created at build time,
so no symlink is ever committed into this source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracewise.bench.model import CaseSpec, case_dir

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Bench",
    "GIT_AUTHOR_EMAIL": "bench@example.invalid",
    "GIT_COMMITTER_NAME": "Bench",
    "GIT_COMMITTER_EMAIL": "bench@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "LC_ALL": "C",
    "TZ": "UTC",
}
DATES = {"C0": "2026-01-01T00:00:00Z", "C1": "2026-01-02T00:00:00Z", "C2": "2026-01-03T00:00:00Z"}
ORDER = ("C0", "C1", "C2")


def _symlinks(spec: CaseSpec, commit: str) -> dict[str, str]:
    return dict(spec.symlinks.get(commit, {}))  # type: ignore[call-overload]


def snapshot(spec: CaseSpec, commit: str) -> dict[str, bytes]:
    """Files of `commit` (C0, C1 or C2) as {repo-relative path: bytes}. Symlinks map to their target text."""
    files: dict[str, bytes] = {}
    for c in ORDER[: ORDER.index(commit) + 1]:
        root = case_dir(spec.id) / "repo" / c
        if c != "C0":
            for gone in spec.commits[c].delete:  # type: ignore[index]
                files.pop(gone, None)
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    files[p.relative_to(root).as_posix()] = p.read_bytes()
        for link, target in _symlinks(spec, c).items():
            files[link] = target.encode()
    return files


@dataclass(frozen=True)
class BuiltRepo:
    work: Path
    bare: Path
    shas: dict[str, str]  # C0/C1/C2 → commit SHA


def _git(args: list[str], cwd: Path, date: str | None = None) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), **GIT_ENV}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603,S607


def build_repo(spec: CaseSpec, dest: Path) -> BuiltRepo:
    """Materialise C0→C1→C2 as commits in `dest/work` and a bare clone at `dest/<owner>/<name>.git`."""
    work = dest / "work" / spec.id
    work.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], work)
    _git(["config", "core.symlinks", "true"], work)
    shas: dict[str, str] = {}
    for c in ORDER:
        for p in list(work.iterdir()):
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        for rel, data in snapshot(spec, c).items():
            f = work / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            if rel in _all_links(spec, c):
                os.symlink(data.decode(), f)
            else:
                f.write_bytes(data)
        _git(["add", "-A"], work)
        msg = "baseline" if c == "C0" else spec.commits[c].message  # type: ignore[index]
        _git(["commit", "-q", "--allow-empty", "-m", msg], work, DATES[c])
        shas[c] = _git(["rev-parse", "HEAD"], work)
    owner, name = spec.repo.split("/")
    bare = dest / "srv" / owner / f"{name}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "-q", "--bare", str(work), str(bare)], dest)
    for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true"), ("http.uploadpack", "true")):
        _git(["config", k, v], bare)
    return BuiltRepo(work, bare, shas)


def _all_links(spec: CaseSpec, commit: str) -> set[str]:
    out: set[str] = set()
    for c in ORDER[: ORDER.index(commit) + 1]:
        out |= set(_symlinks(spec, c))
    return out


def diff_files(repo: BuiltRepo, base: str, head: str) -> list[dict[str, Any]]:
    """GitHub compare-API-shaped `files` for base...head, from the real git diff."""
    out: list[dict[str, Any]] = []
    status_map = {"A": "added", "M": "modified", "D": "removed", "T": "modified"}
    numstat = {}
    for line in _git(["diff", "--numstat", base, head], repo.work).splitlines():
        a, d, path = line.split("\t", 2)
        numstat[path] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)
    for line in _git(["diff", "--name-status", "--no-renames", base, head], repo.work).splitlines():
        st, path = line.split("\t", 1)
        patch = _git(["diff", "--unified=3", base, head, "--", path], repo.work)
        hunks = patch[patch.find("@@") :] if "@@" in patch else None
        add, rem = numstat.get(path, (0, 0))
        out.append(
            {"filename": path, "status": status_map.get(st[0], "modified"), "additions": add, "deletions": rem, "patch": hunks}
        )
    return out
