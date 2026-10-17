"""Local Git smart-HTTP server for offline tests: `git http-backend` behind a WSGI shim.

Binds 127.0.0.1 on an ephemeral port, serves bare repos from a private temp dir, and requires
`Authorization: Basic base64(x-access-token:<token>)` with a token generated per test. Records
every request's headers so tests can assert how credentials were sent. Fault modes let tests
inject HTTP errors, slow responses and oversized packs.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

BACKEND = Path(subprocess.check_output(["git", "--exec-path"], text=True).strip()) / "git-http-backend"  # noqa: S607


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args: Any) -> None:  # no request logging (would include paths only, but keep quiet)
        pass


class _ThreadedServer(WSGIServer):
    daemon_threads = True

    def process_request(self, request: Any, client_address: Any) -> None:
        t = threading.Thread(target=self._handle, args=(request, client_address), daemon=True)
        t.start()

    def _handle(self, request: Any, client_address: Any) -> None:
        try:
            self.finish_request(request, client_address)
        finally:
            self.shutdown_request(request)


@dataclass
class GitServer:
    root: Path
    token: str
    faults: dict[str, Any] = field(default_factory=dict)
    seen: list[dict[str, str]] = field(default_factory=list)
    _srv: Any = None
    _thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self._srv.server_address[:2]
        return f"http://{host}:{port}"

    def expected_auth(self) -> str:
        return "Basic " + base64.b64encode(f"x-access-token:{self.token}".encode()).decode()

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

    # ------------------------------------------------------------ WSGI

    def app(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        headers = {k[5:].replace("_", "-").lower(): v for k, v in environ.items() if k.startswith("HTTP_")}
        self.seen.append({"path": environ.get("PATH_INFO", ""), "query": environ.get("QUERY_STRING", ""), **headers})
        if (delay := self.faults.get("delay_s")) is not None:
            time.sleep(delay)
        if (status := self.faults.get("status")) is not None:
            start_response(f"{status} Fault", [("Content-Type", "text/plain")])
            return [b"injected fault"]
        if headers.get("authorization") != self.expected_auth():
            start_response("401 Unauthorized", [("WWW-Authenticate", 'Basic realm="test"'), ("Content-Type", "text/plain")])
            return [b"auth required"]
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ["wsgi.input"].read(length) if length else b""
        env = {
            "PATH": os.environ["PATH"],
            "GIT_PROJECT_ROOT": str(self.root / "srv"),
            "GIT_HTTP_EXPORT_ALL": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(self.root),
            "REQUEST_METHOD": environ["REQUEST_METHOD"],
            "PATH_INFO": environ.get("PATH_INFO", ""),
            "QUERY_STRING": environ.get("QUERY_STRING", ""),
            "CONTENT_TYPE": environ.get("CONTENT_TYPE", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": "x-access-token",
            "REMOTE_ADDR": "127.0.0.1",
        }
        if "git-protocol" in headers:
            env["GIT_PROTOCOL"] = headers["git-protocol"]
        if "content-encoding" in headers:
            env["HTTP_CONTENT_ENCODING"] = headers["content-encoding"]
        out = subprocess.run([str(BACKEND)], input=body, env=env, capture_output=True, check=False).stdout  # noqa: S603
        head, _, payload = out.partition(b"\r\n\r\n")
        status = "200 OK"
        hdrs = []
        for line in head.decode("latin-1").split("\r\n"):
            if not line:
                continue
            k, _, v = line.partition(":")
            if k.lower() == "status":
                status = v.strip()
            else:
                hdrs.append((k, v.strip()))
        if (pad := self.faults.get("pad_bytes")) and "git-upload-pack" in environ.get("PATH_INFO", ""):
            payload = payload + b"\0" * pad  # oversized/garbage tail
        start_response(status, hdrs)
        return [payload]

    def start(self) -> GitServer:
        self._srv = make_server("127.0.0.1", 0, self.app, server_class=_ThreadedServer, handler_class=_Quiet)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
        shutil.rmtree(self.root, ignore_errors=True)


def git_server(token: str) -> GitServer:
    root = Path(tempfile.mkdtemp(prefix="twgit-"))
    root.chmod(0o700)
    return GitServer(root, token).start()
