"""Phase 52: the network guard's decision logic is tested permanently (the session-level behaviour, failing the
run when a test swallows the refusal, was verified with a deliberate probe in Phase 51 and is exercised by CI)."""

from __future__ import annotations

import socket

import pytest

from tests import netguard as ng

ALLOWED = [("127.0.0.1", 5432), ("::1", 80), ("localhost", 8080), "/run/tracewise/.s.PGSQL.5432", b"\0abstract"]


@pytest.mark.parametrize("addr", ALLOWED)
def test_loopback_and_unix_sockets_are_allowed(addr: object) -> None:
    assert ng._ok(addr)


@pytest.mark.parametrize("addr", [("192.0.2.1", 443), ("140.82.112.3", 443), ("api.openai.com", 443), ("10.0.0.5", 5432)])
def test_every_other_address_is_refused_and_counted(addr: object) -> None:
    assert not ng._ok(addr)
    before = len(ng.ATTEMPTS)
    s = socket.socket()
    try:
        with pytest.raises(OSError, match="netguard: external connection refused"):
            ng._guard(s, addr)
        assert len(ng.ATTEMPTS) == before + 1  # recorded even though the caller catches the OSError
    finally:
        s.close()
        del ng.ATTEMPTS[before:]  # this deliberate probe must not fail the surrounding session
