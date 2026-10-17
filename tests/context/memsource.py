"""In-memory CodeSource for tool tests (no git, no network)."""

from __future__ import annotations

import hashlib

from tracewise.context.source import CodeSource, Limits, TreeEntry


class MemSource(CodeSource):
    kind = "memory"

    def __init__(
        self,
        files: dict[str, bytes | str],
        *,
        symlinks: dict[str, str] | None = None,
        submodules: tuple[str, ...] = (),
        limits: Limits | None = None,
    ) -> None:
        super().__init__("a" * 40, limits)
        self._data: dict[str, bytes] = {}
        self._ents: dict[str, TreeEntry] = {}
        for p, d in files.items():
            b = d.encode() if isinstance(d, str) else d
            oid = hashlib.sha1(b, usedforsecurity=False).hexdigest()
            self._data[oid] = b
            self._ents[p] = TreeEntry(p, "file", oid, len(b))
        for p, t in (symlinks or {}).items():
            oid = hashlib.sha1(b"L" + t.encode(), usedforsecurity=False).hexdigest()
            self._data[oid] = t.encode()
            self._ents[p] = TreeEntry(p, "symlink", oid, len(t))
        for p in submodules:
            self._ents[p] = TreeEntry(p, "submodule", "b" * 40, None)

    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]:
        return dict(self._ents), False

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        return self._data.get(entry.oid)
