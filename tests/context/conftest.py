"""Fixtures: one local git smart-HTTP server per module; private workspace root per test."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.git_server import GitServer, git_server
from tracewise.context.gitfetch import FetchLimits, GitFetcher
from tracewise.context.source import Limits


@pytest.fixture(scope="module")
def server() -> Iterator[GitServer]:
    s = git_server(secrets.token_hex(20))  # generated per run; never a real credential
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def ws_root(tmp_path: Path) -> Path:
    return tmp_path / "ws"


def make_fetcher(server: GitServer, ws_root: Path, **kw) -> GitFetcher:  # type: ignore[no-untyped-def]
    limits = kw.pop("limits", Limits())
    fl = FetchLimits(**kw)
    return GitFetcher(
        workspace_root=ws_root, limits=limits, fetch_limits=fl, base_url=server.base_url, allow_insecure_loopback=True
    )
