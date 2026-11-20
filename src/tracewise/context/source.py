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

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from tracewise.context.paths import UnsafePath, resolve_link, validate_repo_path
from tracewise.observe import event

log = logging.getLogger(__name__)

EntryKind = Literal["file", "symlink", "submodule"]
# Who is reading: the investigation's tools, or the validator checking the model's claims afterwards (C-3).
ReadPurpose = Literal["tool", "validation"]
MAX_SYMLINK_HOPS = 5
BINARY_SNIFF_BYTES = 8000


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 1024 * 1024  # FS-CTX-1: skip files > 1 MB
    # Global totals for one analysis: tool reads plus validation reads together never exceed them.
    max_total_read_bytes: int = 24 * 1024 * 1024
    max_reads: int = 4000
    max_entries: int = 100_000
    # C-3: the part of the totals reserved for the evidence validator. Tools draw only on the rest, so a tool-heavy
    # investigation (12 greps can ask for 4,800 reads and 96 MB) cannot leave validation unable to read the location.
    validation_reads: int = 64
    validation_read_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.validation_reads < self.max_reads:
            raise ValueError("validation_reads must be positive and below max_reads")
        if not 0 < self.validation_read_bytes < self.max_total_read_bytes:
            raise ValueError("validation_read_bytes must be positive and below max_total_read_bytes")


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
    temporarily_unavailable = "temporarily_unavailable"  # a transient failure that outlasted the in-place retries
    read_failed = "read_failed"  # a permanent GitHub error for this one file (422, malformed response): not retried


class TransientReadError(Exception):
    """Raised by `_read_blob` when a read may succeed if repeated (e.g. a GitHub 5xx, 429 or timeout). The source
    retries it in place, boundedly, instead of failing the whole analysis (I-3, D-B). Messages carry no content."""


class PermanentReadError(Exception):
    """Raised by `_read_blob` when GitHub refused this one read for good (not absence, not access): reported as
    `read_failed`, never retried, and never taken as proof that the file does not exist. Messages carry no content."""


# I-3/D-B: in-place retries of a transient read, on top of the GitHub client's own inline retries (≤3 per request):
# one more pass after a pause rides out a longer outage. Bounded in count, and never past the attempt deadline.
TRANSIENT_READ_TRIES = 2
TRANSIENT_BACKOFF_S = (1.0,)


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
    max_reads: int
    max_bytes: int
    used_bytes: int = 0
    reads: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, n: int) -> bool:
        with self.lock:
            if self.reads + 1 > self.max_reads or self.used_bytes + n > self.max_bytes:
                return False
            self.reads += 1
            self.used_bytes += n
            return True


class CodeSource(ABC):
    kind: str = "abstract"

    def __init__(self, head_sha: str, limits: Limits | None = None) -> None:
        self.head_sha = head_sha
        self.limits = limits or Limits()
        lim = self.limits
        # Two fixed pools that sum to the global totals: neither can grow, and neither can drain the other (C-3).
        self._budgets: dict[ReadPurpose, _Budget] = {
            "tool": _Budget(lim.max_reads - lim.validation_reads, lim.max_total_read_bytes - lim.validation_read_bytes),
            "validation": _Budget(lim.validation_reads, lim.validation_read_bytes),
        }
        self._entries: dict[str, TreeEntry] | None = None
        self.tree_truncated = False
        self.skipped: dict[str, ReadStatus] = {}  # FS-CTX-1 `files_skipped`
        # Set by evidence collection to the attempt deadline's `remaining` (C-4): transient-read retries stop there.
        self.time_left: Callable[[], float] | None = None
        self._sleep: Callable[[float], None] = time.sleep

    @property
    def available(self) -> bool:
        return True

    @property
    def transient_failure(self) -> bool:
        """Some code could not be read because of a transient failure that outlasted the retries: what the
        investigation saw is incomplete for reasons unrelated to the repository (I-3, source unavailable)."""
        return ReadStatus.temporarily_unavailable in self.skipped.values()

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

    def read(self, path: str, *, purpose: ReadPurpose = "tool") -> FileRead:
        """Path, symlink and size rules are the same for every purpose; only the budget charged differs."""
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
                return self._read_file(path, entry, purpose)
            seen.append(current)
            target = self._read_link_target(entry)
            nxt = resolve_link(current, target) if target is not None else None
            if nxt is None:
                return self._skip(path, current, ReadStatus.symlink_escapes)
            if nxt in seen:
                return self._skip(path, current, ReadStatus.symlink_loop)
            current = nxt
        return self._skip(path, current, ReadStatus.symlink_loop)

    def _read_file(self, requested: str, entry: TreeEntry, purpose: ReadPurpose) -> FileRead:
        if entry.size is None or entry.size > self.limits.max_file_bytes:
            return self._skip(requested, entry.path, ReadStatus.too_large, entry.size)
        if not self._budgets[purpose].take(entry.size):
            # Visible in `files_skipped`: a file the budget kept from being read is never silently absent.
            self.skipped.setdefault(entry.path, ReadStatus.budget_exhausted)
            return FileRead(requested, ReadStatus.budget_exhausted, entry.path, size=entry.size)
        data: bytes | None = None
        for i in range(TRANSIENT_READ_TRIES):
            try:
                data = self._read_blob(entry)
                break
            except PermanentReadError:
                return self._skip(requested, entry.path, ReadStatus.read_failed, entry.size)
            except TransientReadError:
                wait = TRANSIENT_BACKOFF_S[min(i, len(TRANSIENT_BACKOFF_S) - 1)]
                out_of_time = self.time_left is not None and self.time_left() <= wait
                if i == TRANSIENT_READ_TRIES - 1 or out_of_time:
                    event(log, "context.read_retries_exhausted", logging.WARNING, tries=i + 1, purpose=purpose)
                    return self._skip(requested, entry.path, ReadStatus.temporarily_unavailable, entry.size)
                event(log, "context.read_retry", tries=i + 1, purpose=purpose)
                self._sleep(wait)
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
    """Explicit 'no code context' (both Git and the Contents API failed). Every read says so. `transient`: the
    Contents API failed with a retryable error, so the code exists but could not be reached this attempt."""

    kind = "unavailable"

    def __init__(self, head_sha: str, reason: str, *, transient: bool = False) -> None:
        super().__init__(head_sha)
        self.reason, self.transient = reason, transient

    @property
    def available(self) -> bool:
        return False

    @property
    def transient_failure(self) -> bool:
        return self.transient

    def read(self, path: str, *, purpose: ReadPurpose = "tool") -> FileRead:
        return FileRead(path, ReadStatus.unavailable)

    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]:
        return {}, False

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        return None
