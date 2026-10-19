"""pytest plugin: refuse every non-loopback, non-Unix socket connection for the whole session.

Enable with `-p tests.netguard` (CI does). Loopback (the local fake servers, git http-backend) and AF_UNIX (the
disposable PostgreSQL socket) are allowed; anything else raises OSError, is counted, and fails the session, so a
test can never silently reach GitHub, OpenAI or any other external host.
"""

from __future__ import annotations

import socket
from typing import Any

ATTEMPTS: list[Any] = []
_real = socket.socket.connect
_real_ex = socket.socket.connect_ex


def _ok(addr: Any) -> bool:
    if isinstance(addr, str | bytes):
        return True  # AF_UNIX
    return bool(addr) and addr[0] in ("127.0.0.1", "::1", "localhost")


def _guard(self: socket.socket, addr: Any) -> None:
    if not _ok(addr):
        ATTEMPTS.append(addr)
        raise OSError(f"netguard: external connection refused: {addr!r}")
    _real(self, addr)


def _guard_ex(self: socket.socket, addr: Any) -> int:
    if not _ok(addr):
        ATTEMPTS.append(addr)
        raise OSError(f"netguard: external connection refused: {addr!r}")
    return _real_ex(self, addr)


socket.socket.connect = _guard  # type: ignore[method-assign]
socket.socket.connect_ex = _guard_ex  # type: ignore[method-assign]


def pytest_terminal_summary(terminalreporter: Any) -> None:
    terminalreporter.write_line(f"NETGUARD external connection attempts: {len(ATTEMPTS)}")


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if ATTEMPTS and exitstatus == 0:
        session.exitstatus = 1  # an attempt is a failure even if the test swallowed the OSError
