"""Local Git smart-HTTP server for offline tests: `git http-backend` behind a WSGI shim.

Binds 127.0.0.1 on an ephemeral port, serves bare repos from a private temp dir, and requires
`Authorization: Basic base64(x-access-token:<token>)` with a token generated per test. Records
every request's headers so tests can assert how credentials were sent. Fault modes let tests
inject HTTP errors, slow responses and oversized packs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tracewise.bench.gitserve import LocalGitServer


@dataclass
class GitServer(LocalGitServer):
    """Test helper: LocalGitServer plus repository builders."""

    # ------------------------------------------------------------ repos

    def git(self, *args: str, cwd: Path) -> str:
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        }
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603,S607

    def make_repo(
        self,
        owner: str,
        name: str,
        files: dict[str, bytes | str],
        *,
        symlinks: dict[str, str] | None = None,
        submodules: dict[str, str] | None = None,
        parent_files: dict[str, bytes | str] | None = None,
    ) -> str:
        """Create owner/name.git with (optionally) a parent commit, then a commit with `files`. Returns head SHA."""
        work = self.root / "work" / owner / name
        work.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", cwd=work)
        self.git("config", "core.symlinks", "true", cwd=work)

        def write(fs: dict[str, bytes | str]) -> None:
            for p in [p for p in work.rglob("*") if ".git" not in p.parts and p.is_file()]:
                p.unlink()
            for rel, data in fs.items():
                f = work / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data.encode() if isinstance(data, str) else data)

        if parent_files is not None:
            write(parent_files)
            self.git("add", "-A", cwd=work)
            self.git("commit", "-q", "-m", "parent", cwd=work)
        write(files)
        for link, target in (symlinks or {}).items():
            (work / link).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, work / link)
        self.git("add", "-A", cwd=work)
        for path, sha in (submodules or {}).items():
            self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},{path}", cwd=work)
        self.git("commit", "-q", "--allow-empty", "-m", "head", cwd=work)
        head = self.git("rev-parse", "HEAD", cwd=work)
        bare = self.root / "srv" / owner / f"{name}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        self.git("clone", "-q", "--bare", str(work), str(bare), cwd=self.root)
        for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true"), ("http.uploadpack", "true")):
            self.git("config", k, v, cwd=bare)
        return head

    def stop(self) -> None:
        super().stop()
        shutil.rmtree(self.root, ignore_errors=True)


def git_server(token: str) -> GitServer:
    root = Path(tempfile.mkdtemp(prefix="twgit-"))
    root.chmod(0o700)
    srv = GitServer(root, token)
    srv.start()
    return srv
