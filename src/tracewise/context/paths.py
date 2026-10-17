"""Validation for repository identifiers and repository-relative paths (FS-CTX-5).

Everything that names a repository, commit or file passes through here before it reaches
Git, the GitHub API or a tool result. Rules are strict and allow-list based.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata

MAX_PATH_BYTES = 1024
_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class UnsafePath(ValueError):
    pass


def validate_owner_repo(full_name: str) -> tuple[str, str]:
    owner, sep, repo = full_name.partition("/")
    if not sep or not _OWNER.match(owner) or not _REPO.match(repo) or repo in (".", "..") or repo.endswith(".git"):
        raise UnsafePath("invalid owner/repository")
    return owner, repo


def validate_sha(sha: str) -> str:
    if not _SHA.match(sha):
        raise UnsafePath("commit must be a full 40-hex SHA")
    return sha


def validate_repo_path(path: str, *, allow_root: bool = False) -> str:
    """Return the canonical repo-relative path or raise `UnsafePath`.

    Rejects: empty (unless `allow_root`), absolute, `..`/`.`/empty segments, `.git` segments,
    backslashes, NUL/control/format characters, non-NFC Unicode, and over-long paths.
    Percent signs are literal file-name characters: paths are never URL-decoded.
    """
    if not isinstance(path, str):
        raise UnsafePath("path must be a string")
    if path in ("", ".") and allow_root:
        return ""
    if not path or len(path.encode("utf-8", "surrogatepass")) > MAX_PATH_BYTES:
        raise UnsafePath("path empty or too long")
    if path.startswith("/") or "\\" in path:
        raise UnsafePath("absolute paths and backslashes are not allowed")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") for ch in path):
        raise UnsafePath("control or unassigned characters in path")
    if unicodedata.normalize("NFC", path) != path:
        raise UnsafePath("path is not NFC-normalised")
    parts = path.rstrip("/").split("/") if allow_root else path.split("/")
    if any(p in ("", ".", "..") or p.lower() == ".git" for p in parts):
        raise UnsafePath("path contains empty, '.', '..' or '.git' segments")
    return "/".join(parts)


def resolve_link(link_path: str, target: str) -> str | None:
    """Resolve a symlink target lexically inside the repository. None if it escapes or is unsafe."""
    if not target or target.startswith("/") or "\\" in target or "\x00" in target:
        return None
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(link_path), target))
    if joined.startswith("../") or joined in ("..", ".", ""):
        return None
    try:
        return validate_repo_path(joined)
    except UnsafePath:
        return None
