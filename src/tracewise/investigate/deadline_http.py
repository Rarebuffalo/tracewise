"""A real wall-clock deadline for an HTTP exchange (moved here from the API smoke harness under `scripts/`, Phase 49).

httpx timeouts apply to each socket operation, so a peer that trickles bytes can keep a request alive far past
any intended total. This module bounds the whole exchange instead:

* `Deadline`: one monotonic deadline shared by the caller, the transport and the socket backend.
* `DeadlineBackend` / `DeadlineStream`: name resolution runs in a thread abandoned at the deadline; connect, the TLS
  handshake and every read and write get at most the time left; a watchdog thread shuts the socket down once the
  clock passes the deadline, which interrupts an operation already blocked in the kernel.
* `DeadlineHTTPTransport`: httpx's transport rebuilt on that backend.
* `RequestDeadlineTransport`: sets the deadline of each request from the request's own timeout (the benchmark's
  model mode: the investigation's remaining time), so no request outlives it.

Bound: an exchange ends no later than the deadline plus `WATCHDOG_INTERVAL_S` plus scheduling jitter. Not covered:
the OS scheduler, and time spent before the request reaches this transport.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

import httpcore
import httpx

WATCHDOG_INTERVAL_S = 0.02  # how often the watchdog compares the wall clock with the deadline


class DeadlineExceeded(Exception):
    """The wall-clock deadline was reached; the in-flight exchange was abandoned."""


class Deadline:
    """One monotonic deadline shared by the caller, its transport and the socket backend.

    `at` is the deadline of the current exchange (None: not started). `start_step` sets it to
    min(now + step_timeout_s, overall_at), never past an overall deadline that the caller fixes once; `set_at` sets it
    directly. `expired` is sticky until the next start."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.at: float | None = None
        self.expired = False

    def start_step(self, overall_at: float, step_timeout_s: float) -> None:
        now = self.clock()
        if now >= overall_at:
            self.expired = True
            raise DeadlineExceeded()
        self.at = min(now + step_timeout_s, overall_at)

    def set_at(self, at: float) -> None:
        """A new exchange with its own deadline (the benchmark: the investigation's remaining time)."""
        self.expired = False
        self.at = at
        if self.clock() >= at:
            self.expired = True
            raise DeadlineExceeded()

    def remaining(self) -> float:
        if self.at is None:
            return float("inf")
        left = self.at - self.clock()
        if left <= 0:
            self.expired = True
        return left


def _clamp(deadline: Deadline, timeout: float | None, exc: type[Exception]) -> float:
    """The socket timeout for one operation: never longer than the time left; nothing starts after the deadline."""
    left = deadline.remaining()
    if left <= 0:
        raise exc("deadline reached")
    return left if timeout is None else min(timeout, left)


def _bounded[T](deadline: Deadline, timeout: float | None, exc: type[Exception], op: Callable[[float], T]) -> T:
    """Run one socket operation under the clamped timeout. If it times out while the deadline was the binding
    limit, the deadline is what ended it, even if the clock reads a hair before `at` (socket timers are not exact)."""
    t = _clamp(deadline, timeout, exc)
    try:
        return op(t)
    except httpcore.TimeoutException:
        if timeout is None or t < timeout:
            deadline.expired = True
        raise


class DeadlineStream(httpcore.NetworkStream):
    """Every blocking socket operation gets at most the remaining time; the watchdog can shut the socket down."""

    def __init__(self, inner: httpcore.NetworkStream, deadline: Deadline, backend: DeadlineBackend | None = None) -> None:
        self.inner, self.deadline, self.backend = inner, deadline, backend

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return _bounded(self.deadline, timeout, httpcore.ReadTimeout, lambda t: self.inner.read(max_bytes, t))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        _bounded(self.deadline, timeout, httpcore.WriteTimeout, lambda t: self.inner.write(buffer, t))

    def close(self) -> None:
        if self.backend is not None:
            self.backend.untrack(self)
        self.inner.close()

    def start_tls(self, ssl_context: Any, server_hostname: str | None = None, timeout: float | None = None) -> DeadlineStream:
        tls = _bounded(
            self.deadline, timeout, httpcore.ConnectTimeout, lambda t: self.inner.start_tls(ssl_context, server_hostname, t)
        )
        upgraded = DeadlineStream(tls, self.deadline, self.backend)
        if self.backend is not None:
            self.backend.untrack(self)
            self.backend.track(upgraded)
        return upgraded

    def get_extra_info(self, info: str) -> Any:
        return self.inner.get_extra_info(info)


class DeadlineBackend(httpcore.NetworkBackend):
    """httpcore network backend that enforces `Deadline` (no new dependency: httpcore ships with httpx).

    * Name resolution runs in a worker thread that is abandoned at the deadline (getaddrinfo has no timeout).
    * Connect, TLS handshake, every read and every write are clamped to the remaining time (`DeadlineStream`).
    * A watchdog thread shuts down every open socket once the wall clock passes the deadline. That interrupts an
      operation already blocked in the kernel (a slow multi-step TLS handshake, a write split into several sends, a
      peer that trickles bytes) so that no exchange outlives the deadline by more than about WATCHDOG_INTERVAL_S."""

    def __init__(
        self,
        deadline: Deadline,
        inner: httpcore.NetworkBackend | None = None,
        resolver: Callable[..., Any] = socket.getaddrinfo,
    ) -> None:
        self.deadline, self.resolver = deadline, resolver
        self.inner = inner or httpcore.SyncBackend()
        self._streams: set[DeadlineStream] = set()
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._watchdog = threading.Thread(target=self._watch, name="deadline-watchdog", daemon=True)
        self._watchdog.start()

    def track(self, s: DeadlineStream) -> None:
        with self._lock:
            self._streams.add(s)

    def untrack(self, s: DeadlineStream) -> None:
        with self._lock:
            self._streams.discard(s)

    def close(self) -> None:
        self._closed.set()

    def _watch(self) -> None:
        while not self._closed.wait(WATCHDOG_INTERVAL_S):
            if self.deadline.at is not None and self.deadline.clock() >= self.deadline.at:
                self.deadline.expired = True
                with self._lock:
                    streams = list(self._streams)
                for s in streams:
                    _shutdown(s)

    def _resolve(self, host: str, port: int) -> list[Any]:
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["addrs"] = self.resolver(host, port, type=socket.SOCK_STREAM)
            except OSError as e:
                box["error"] = e

        t = threading.Thread(target=work, name="deadline-resolver", daemon=True)
        t.start()
        t.join(_clamp(self.deadline, None, httpcore.ConnectTimeout))
        if t.is_alive():
            self.deadline.expired = True
            raise httpcore.ConnectTimeout("deadline reached during name resolution")
        if "error" in box or not box.get("addrs"):
            raise httpcore.ConnectError("name resolution failed")
        addrs: list[Any] = box["addrs"]
        return addrs

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> DeadlineStream:
        last: Exception = httpcore.ConnectError("no address")
        for *_info, sockaddr in self._resolve(host, port):
            addr = str(sockaddr[0])

            def connect(t: float, addr: str = addr) -> httpcore.NetworkStream:
                return self.inner.connect_tcp(addr, port, t, local_address, socket_options)

            try:  # a literal address: no further name lookup inside create_connection
                raw = _bounded(self.deadline, timeout, httpcore.ConnectTimeout, connect)
            except httpcore.ConnectTimeout:
                if self.deadline.expired:
                    raise
                last = httpcore.ConnectTimeout("connect timed out")
                continue
            except httpcore.ConnectError as e:
                last = e
                continue
            s = DeadlineStream(raw, self.deadline, self)
            self.track(s)
            return s
        raise last

    def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None) -> DeadlineStream:
        raise httpcore.ConnectError("unix sockets are not used")

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, min(seconds, self.deadline.remaining())))


def _shutdown(s: DeadlineStream) -> None:
    """Shut the connection down through a duplicate descriptor, so the (possibly TLS) socket object used by the
    blocked thread is not touched from this thread; the blocked call then returns with an error."""
    sock = s.get_extra_info("socket")
    fd = sock.fileno() if sock is not None else -1
    if fd < 0:
        return
    try:
        dup = socket.socket(fileno=os.dup(fd))
    except OSError:
        return
    try:
        dup.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    finally:
        dup.close()


class DeadlineHTTPTransport(httpx.HTTPTransport):
    """httpx's own transport with the connection pool rebuilt on `DeadlineBackend`: one connection, no keep-alive, no
    retries, no proxy or certificate settings from the environment."""

    def __init__(self, deadline: Deadline) -> None:
        super().__init__(trust_env=False, retries=0)
        self._pool.close()
        self.backend = DeadlineBackend(deadline)
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=self.backend,
        )

    def close(self) -> None:
        super().close()
        self.backend.close()


class RequestDeadlineTransport(httpx.BaseTransport):
    """Gives every request a total deadline equal to its own timeout: `now + max(connect, read, write, pool)`. The
    adapter sets that timeout to the investigation's remaining time, so the deadline is the investigation's. A request
    without a timeout is refused (no unbounded exchange). Reading the response body stays under the same deadline:
    the socket backend enforces it while the caller streams."""

    def __init__(self, inner: DeadlineHTTPTransport | httpx.BaseTransport, deadline: Deadline) -> None:
        self.inner, self.deadline = inner, deadline

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        t = request.extensions.get("timeout")
        values = [v for v in t.values() if isinstance(v, int | float)] if isinstance(t, dict) else []
        if not values:
            raise DeadlineExceeded("a request without a timeout is never sent")
        self.deadline.set_at(self.deadline.clock() + max(values))
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
