"""Local git smart-HTTP server (`git http-backend` behind a WSGI shim) for REPLAY runs (T-601).

Binds 127.0.0.1 on an ephemeral port, serves bare repositories under `root/srv`, and requires
`Authorization: Basic base64(x-access-token:<token>)` with a token generated per run. Used by the
benchmark harness and by tests so the product's real `GitFetcher` can be exercised offline.
"""

from __future__ import annotations

import base64
import os
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

BACKEND = Path(subprocess.check_output(["git", "--exec-path"], text=True).strip()) / "git-http-backend"  # noqa: S607


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass


class _ThreadedServer(WSGIServer):
    daemon_threads = True

    def process_request(self, request: Any, client_address: Any) -> None:
        threading.Thread(target=self._handle, args=(request, client_address), daemon=True).start()

    def _handle(self, request: Any, client_address: Any) -> None:
        try:
            self.finish_request(request, client_address)
        finally:
            self.shutdown_request(request)


@dataclass
class LocalGitServer:
    root: Path
    token: str
    faults: dict[str, Any] = field(default_factory=dict)
    seen: list[dict[str, str]] = field(default_factory=list)
    _srv: Any = None

    @property
    def base_url(self) -> str:
        host, port = self._srv.server_address[:2]
        return f"http://{host}:{port}"

    def expected_auth(self) -> str:
        return "Basic " + base64.b64encode(f"x-access-token:{self.token}".encode()).decode()

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
        status_line, hdrs = "200 OK", []
        for line in head.decode("latin-1").split("\r\n"):
            if not line:
                continue
            k, _, v = line.partition(":")
            if k.lower() == "status":
                status_line = v.strip()
            else:
                hdrs.append((k, v.strip()))
        start_response(status_line, hdrs)
        return [payload]

    def start(self) -> LocalGitServer:
        self._srv = make_server("127.0.0.1", 0, self.app, server_class=_ThreadedServer, handler_class=_Quiet)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
