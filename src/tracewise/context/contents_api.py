"""Contents-API fallback code source (T-304; FS-CTX-1).

Used only when the Git fetch fails. Same SHA, same path rules, same size limits:
* the tree comes from `GET /git/trees/{head_sha}?recursive=1` (truncation flagged);
* a file comes from `GET /contents/{path}?ref={head_sha}` and is accepted only if its blob SHA equals
  the tree entry's and its decoded size matches; files over the limit are never requested;
* a symlink's target text comes from `GET /git/blobs/{oid}` and is resolved lexically in the tree.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from tracewise.context.paths import UnsafePath, validate_repo_path
from tracewise.context.source import CodeSource, EntryKind, Limits, TreeEntry
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient


class ContentsApiSource(CodeSource):
    kind = "contents_api"

    def __init__(self, rc: RepoClient, head_sha: str, limits: Limits | None = None) -> None:
        super().__init__(head_sha, limits)
        self._rc = rc

    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]:
        doc = self._rc.request("get_tree", tree_sha=self.head_sha, query={"recursive": "1"})
        if not isinstance(doc, dict) or not isinstance(doc.get("tree"), list):
            raise gh_err.GitHubPermanent("unexpected tree response")
        out: dict[str, TreeEntry] = {}
        for item in doc["tree"]:
            if not isinstance(item, dict) or item.get("type") == "tree":
                continue
            try:
                path = validate_repo_path(str(item.get("path", "")))
            except UnsafePath:
                continue
            mode = item.get("mode")
            kind: EntryKind = "submodule" if mode == "160000" else "symlink" if mode == "120000" else "file"
            size = item.get("size") if isinstance(item.get("size"), int) else None
            out[path] = TreeEntry(path, kind, str(item.get("sha", "")), size)
        return out, bool(doc.get("truncated"))

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        try:
            if entry.kind == "symlink":
                doc = self._rc.request("get_blob", file_sha=entry.oid)
            else:
                doc = self._rc.request("get_contents", path=entry.path, query={"ref": self.head_sha})
        except (gh_err.NotFound, gh_err.Gone, gh_err.PermissionDenied):
            return None
        return _decode(doc, entry)


def _decode(doc: Any, entry: TreeEntry) -> bytes | None:
    if not isinstance(doc, dict) or doc.get("encoding") != "base64" or not isinstance(doc.get("content"), str):
        return None
    if doc.get("sha") != entry.oid:
        return None  # not the blob of this commit's tree entry
    try:
        data = base64.b64decode(doc["content"], validate=False)
    except (binascii.Error, ValueError):
        return None
    if entry.size is not None and len(data) != entry.size:
        return None
    return data
