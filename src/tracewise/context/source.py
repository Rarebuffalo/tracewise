"""Read-only code sources at one exact commit (T-304).

A `CodeSource` exposes the tree of `head_sha` and bounded file reads. Implementations:
`GitObjectSource` (objects fetched into a private bare repo; nothing is checked out) and
`ContentsApiSource` (GitHub Contents/Trees API at the same SHA). `UnavailableSource` makes
"no code context" explicit instead of silently empty.

Symlinks are resolved **lexically inside the tree** (≤5 hops) and never on any filesystem; a
target that is absolute or leaves the repository is refused. Submodules are reported, not read.
Missing blobs (filtered for size) and oversized or binary files are expected outcomes.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from tracewise.context.paths import UnsafePath, resolve_link, validate_repo_path

EntryKind = Literal["file", "symlink", "submodule"]
MAX_SYMLINK_HOPS = 5
BINARY_SNIFF_BYTES = 8000


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 1024 * 1024  # FS-CTX-1: skip files > 1 MB
    max_total_read_bytes: int = 24 * 1024 * 1024
    max_reads: int = 4000
    max_entries: int = 100_000


class ReadStatus(StrEnum):
    ok = "ok"
    not_found = "not_found"
    too_large = "too_large"
    binary = "binary"
    symlink_escapes = "symlink_escapes"
    symlink_loop = "symlink_loop"
    submodule = "submodule"
    is_directory = "is_directory"
    invalid_path = "invalid_path"
    budget_exhausted = "budget_exhausted"
    unavailable = "unavailable"


@dataclass(frozen=True)
class TreeEntry:
    path: str
    kind: EntryKind
    oid: str
    size: int | None = None  # None when unknown (e.g. filtered blob)


@dataclass(frozen=True)
class FileRead:
    requested: str
    status: ReadStatus
    path: str | None = None  # resolved repository path actually read
    text: str | None = None
    size: int | None = None


@dataclass
class _Budget:
    limits: Limits
    used_bytes: int = 0
    reads: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, n: int) -> bool:
        with self.lock:
            if self.reads + 1 > self.limits.max_reads or self.used_bytes + n > self.limits.max_total_read_bytes:
                return False
            self.reads += 1
            self.used_bytes += n
            return True


class CodeSource(ABC):
    kind: str = "abstract"

    def __init__(self, head_sha: str, limits: Limits | None = None) -> None:
        self.head_sha = head_sha
        self.limits = limits or Limits()
        self._budget = _Budget(self.limits)
        self._entries: dict[str, TreeEntry] | None = None
        self.tree_truncated = False
        self.skipped: dict[str, ReadStatus] = {}  # FS-CTX-1 `files_skipped`

    @property
    def available(self) -> bool:
        return True

    def entries(self) -> dict[str, TreeEntry]:
        if self._entries is None:
            ents, truncated = self._list_tree()
            self.tree_truncated = truncated or len(ents) > self.limits.max_entries
            self._entries = dict(list(ents.items())[: self.limits.max_entries])
        return self._entries

    def directories(self) -> set[str]:
        dirs = {""}
        for p in self.entries():
            parts = p.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        return dirs

    def read(self, path: str) -> FileRead:
        try:
            rel = validate_repo_path(path)
        except UnsafePath:
            return FileRead(path, ReadStatus.invalid_path)
        entries = self.entries()
        seen: list[str] = []
        current = rel
        for _ in range(MAX_SYMLINK_HOPS + 1):
            entry = entries.get(current)
            if entry is None:
                status = ReadStatus.is_directory if current in self.directories() else ReadStatus.not_found
                return FileRead(path, status, current)
            if entry.kind == "submodule":
                return self._skip(path, current, ReadStatus.submodule)
            if entry.kind == "file":
                return self._read_file(path, entry)
            seen.append(current)
            target = self._read_link_target(entry)
            nxt = resolve_link(current, target) if target is not None else None
            if nxt is None:
                return self._skip(path, current, ReadStatus.symlink_escapes)
            if nxt in seen:
                return self._skip(path, current, ReadStatus.symlink_loop)
            current = nxt
        return self._skip(path, current, ReadStatus.symlink_loop)

    def _read_file(self, requested: str, entry: TreeEntry) -> FileRead:
        if entry.size is None or entry.size > self.limits.max_file_bytes:
            return self._skip(requested, entry.path, ReadStatus.too_large, entry.size)
        if not self._budget.take(entry.size):
            return FileRead(requested, ReadStatus.budget_exhausted, entry.path, size=entry.size)
        data = self._read_blob(entry)
        if data is None:
            return self._skip(requested, entry.path, ReadStatus.unavailable, entry.size)
        if len(data) > self.limits.max_file_bytes:
            return self._skip(requested, entry.path, ReadStatus.too_large, len(data))
        if b"\x00" in data[:BINARY_SNIFF_BYTES]:
            return self._skip(requested, entry.path, ReadStatus.binary, len(data))
        return FileRead(requested, ReadStatus.ok, entry.path, data.decode("utf-8", errors="replace"), len(data))

    def _skip(self, requested: str, path: str, status: ReadStatus, size: int | None = None) -> FileRead:
        self.skipped[path] = status
        return FileRead(requested, status, path, size=size)

    def _read_link_target(self, entry: TreeEntry) -> str | None:
        if entry.size is not None and entry.size > 4096:
            return None
        data = self._read_blob(entry)
        if data is None or len(data) > 4096:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @abstractmethod
    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]: ...

    @abstractmethod
    def _read_blob(self, entry: TreeEntry) -> bytes | None: ...


class UnavailableSource(CodeSource):
    """Explicit 'no code context' (both Git and the Contents API failed). Every read says so."""

    kind = "unavailable"

    def __init__(self, head_sha: str, reason: str) -> None:
        super().__init__(head_sha)
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def read(self, path: str) -> FileRead:
        return FileRead(path, ReadStatus.unavailable)

    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]:
        return {}, False

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        return None
