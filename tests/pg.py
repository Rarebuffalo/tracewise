"""Disposable PostgreSQL cluster for tests (never the system instance).

`initdb` into a fresh private temp directory, listen on a Unix socket only (no TCP),
fsync off, `trust` auth confined to that socket directory (mode 0700). Stopped and deleted
on exit. No system configuration or existing data is read or changed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

OWNER = "tracewise_owner"
APP = "tracewise_app"
DB = "tracewise"


def _bin(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"{name} not found; PostgreSQL server binaries are required for DB tests")
    return path


@dataclass
class EphemeralPostgres:
    root: Path
    port: int = 5432

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def sock(self) -> Path:
        return self.root / "s"

    def url(self, user: str = APP, db: str = DB) -> str:
        return f"postgresql://{user}@/{db}?host={quote(str(self.sock), safe='')}&port={self.port}"

    def start(self) -> EphemeralPostgres:
        self.sock.mkdir(mode=0o700)
        env = {**os.environ, "LC_ALL": "C"}
        subprocess.run(  # noqa: S603
            [_bin("initdb"), "-D", str(self.data), "-U", OWNER, "--auth=trust", "-E", "UTF8", "--no-locale", "--no-sync"],
            check=True,
            capture_output=True,
            env=env,
        )
        opts = (
            f"-k {self.sock} -c listen_addresses='' -p {self.port} -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
        )
        subprocess.run(  # noqa: S603
            [_bin("pg_ctl"), "-D", str(self.data), "-o", opts, "-l", str(self.root / "pg.log"), "-w", "start"],
            check=True,
            capture_output=True,
            env=env,
        )
        import psycopg

        with psycopg.connect(self.url(OWNER, "postgres"), autocommit=True) as c:
            c.execute(f"CREATE ROLE {APP} LOGIN")
            c.execute(f"CREATE DATABASE {DB} OWNER {OWNER}")
        return self

    def stop(self) -> None:
        subprocess.run(  # noqa: S603
            [_bin("pg_ctl"), "-D", str(self.data), "-m", "immediate", "-w", "stop"], check=False, capture_output=True
        )
        shutil.rmtree(self.root, ignore_errors=True)


def ephemeral() -> EphemeralPostgres:
    # Short base path: Unix socket paths are limited to ~107 bytes.
    root = Path(tempfile.mkdtemp(prefix="twpg-", dir="/tmp" if Path("/tmp").is_dir() else None))  # noqa: S108 - mkdtemp: private 0700 dir
    root.chmod(0o700)
    return EphemeralPostgres(root).start()
