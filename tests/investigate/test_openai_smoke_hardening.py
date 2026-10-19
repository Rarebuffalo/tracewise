"""Phase 49: smoke-harness hardening (findings D-48-1 and D-48-2). Offline: mock transports, a fake clock, and a
loopback-only socket server for the real-socket deadline checks (permitted by the network guard).

D-48-1: valid JSON with an unsupported schema is `unsupported_response` (exit 8), with evidence, no traceback, no
        response text, never success.
D-48-2: the per-step (30 s) and overall (90 s) limits are wall-clock deadlines. They cover name resolution,
        connect, TLS, writes and the complete response body; a trickling or silent peer is cut off at the deadline;
        the outcome is the content-free class `deadline` (exit 10).
"""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpcore
import httpx
import pytest

from tests.investigate.test_openai_smoke_harness import S

LEAK = "LEAKMARKER-response-text"
OK, REASONING, CALL = S.OK, S.REASONING, S.CALL
BASE = {"object": "response", "status": "completed", "usage": {"input_tokens": 1, "output_tokens": 1}}


def run_main(monkeypatch: pytest.MonkeyPatch, script: list[Any], **kw: Any) -> tuple[int, dict[str, Any], str]:
    monkeypatch.setitem(S.SCENARIOS, "probe", script)
    buf = io.StringIO()
    code = S.main(["--offline", "probe", "--model", "offline-model"], env={}, out=buf, **kw)
    text = buf.getvalue()
    return code, json.loads(text), text


# ------------------------------------------------------------------ D-48-1: malformed schemas


def _msg(content: Any) -> dict[str, Any]:
    return {"type": "message", "role": "assistant", "content": content}


MALFORMED_FIRST = {  # the first response (plain text step) is malformed
    "output-int": {**BASE, "output": 5},
    "output-dict": {**BASE, "output": {"text": LEAK}},
    "output-string": {**BASE, "output": LEAK},
    "item-not-object": {**BASE, "output": [5, LEAK]},
    "content-int": {**BASE, "output": [_msg(5)]},
    "content-string": {**BASE, "output": [_msg(LEAK)]},
    "content-part-not-object": {**BASE, "output": [_msg([LEAK])]},
    "content-missing": {**BASE, "output": [{"type": "message", "role": "assistant"}]},
    "text-not-string": {**BASE, "output": [_msg([{"type": "output_text", "text": 5}])]},
    "item-type-not-string": {**BASE, "output": [{"type": 5, "text": LEAK}]},
    "error-not-object": {**BASE, "error": LEAK, "output": [_msg([{"type": "output_text", "text": "OK"}])]},
    "usage-not-object": {**BASE, "usage": LEAK, "output": [_msg([{"type": "output_text", "text": "OK"}])]},
    "top-level-list": [LEAK],
}
MALFORMED_SECOND = {  # the tool-call step is malformed after a valid first step
    "summary-int": {**BASE, "output": [{**REASONING, "summary": 5}, CALL]},
    "summary-string": {**BASE, "output": [{**REASONING, "summary": LEAK}, CALL]},
    "call-args-object": {**BASE, "output": [{**CALL, "arguments": {"path": LEAK}}]},
    "call-id-int": {**BASE, "output": [{**CALL, "call_id": 7}]},
}


@pytest.mark.parametrize("name", sorted(MALFORMED_FIRST) + sorted(MALFORMED_SECOND))
def test_unsupported_schema_is_exit_8_with_evidence_and_no_content(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    script = [MALFORMED_FIRST[name]] if name in MALFORMED_FIRST else [OK, MALFORMED_SECOND[name]]
    code, ev, text = run_main(monkeypatch, [*script, OK, OK])
    assert (ev["result"], code) == ("unsupported_response", 8)
    assert LEAK not in text and S.OFFLINE_OPAQUE not in text
    assert ev["exchanges"] and "response" in ev["exchanges"][-1]  # evidence of what was received, content-free
    assert ev["failure"]["detail"] is None


def test_missing_optional_fields_are_still_recorded_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    lean_reasoning = {"type": "reasoning", "id": "rs", "encrypted_content": "opaque-x"}  # no summary
    lean_call = {"type": "function_call", "call_id": "c1", "name": "list_dir", "arguments": "{}"}  # no item id
    code, ev, _ = run_main(monkeypatch, [OK, {**BASE, "output": [lean_reasoning, lean_call]}, OK])
    assert (ev["result"], code) == ("pass", 0)
    rec = ev["exchanges"][1]["response"]["output"]
    assert rec[0] == {"type": "reasoning", "encrypted_content_present": True, "summary_parts": 0}


def test_unexpected_internal_error_is_contained_without_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(LEAK)

    monkeypatch.setattr(S, "run_steps", boom)
    code, ev, text = run_main(monkeypatch, [OK])
    assert (ev["result"], code) == ("harness_error", 1) and LEAK not in text


# ------------------------------------------------------------------ D-48-2: deadlines (fake clock, mock streams)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_a_trickling_mock_body_is_cut_off_at_the_step_deadline_and_closed() -> None:
    clock = Clock()
    closed: list[bool] = []

    class Trickle(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            while True:  # never ends on its own
                clock.t += 5.0
                yield b" "

        def close(self) -> None:
            closed.append(True)

    deadline = S.Deadline(clock)
    deadline.at = clock() + S.STEP_TIMEOUT_S
    g = S.GuardedTransport(httpx.MockTransport(lambda r: httpx.Response(200, stream=Trickle())), deadline)
    with pytest.raises(S.DeadlineExceeded):
        g.handle_request(httpx.Request("POST", S.ENDPOINT, content=b"{}"))
    assert closed and deadline.expired and clock.t - 1000.0 <= S.STEP_TIMEOUT_S + 5.0
    assert g.records[0].get("deadline_exceeded") is True and "response" not in g.records[0]


def test_no_request_starts_after_the_deadline() -> None:
    clock = Clock()
    deadline = S.Deadline(clock)
    deadline.at = clock() - 0.001
    g = S.GuardedTransport(httpx.MockTransport(lambda r: pytest.fail("must not be sent")), deadline)
    with pytest.raises(S.DeadlineExceeded):
        g.handle_request(httpx.Request("POST", S.ENDPOINT, content=b"{}"))
    assert g.sent == 0 and g.records == []


def test_the_overall_deadline_spans_the_whole_run_and_never_restarts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each exchange takes 29 s (under the 30 s step limit). With a 60 s overall limit the third step may only run
    until t+60, so it is cut off there: the overall deadline is fixed at the start of the run."""
    clock = Clock()
    monkeypatch.setattr(S, "TOTAL_DEADLINE_S", 60.0)
    monkeypatch.setitem(S.SCENARIOS, "probe", [OK, {**BASE, "output": [REASONING, CALL]}, OK])
    real_init = S.OfflineTransport.__init__

    def init(self: Any, scenario: str) -> None:
        real_init(self, scenario)
        inner = self.handler

        def slow(req: httpx.Request) -> httpx.Response:
            clock.t += 29.0
            return inner(req)

        self.handler = slow

    monkeypatch.setattr(S.OfflineTransport, "__init__", init)
    buf = io.StringIO()
    code = S.main(["--offline", "probe", "--model", "offline-model"], env={}, out=buf, clock=clock)
    ev = json.loads(buf.getvalue())
    assert (ev["result"], code, ev["requests_sent"]) == ("deadline", 10, 3)
    assert [("response" in r, r.get("deadline_exceeded", False)) for r in ev["exchanges"]] == [
        (True, False),
        (True, False),
        (False, True),  # no claim of a completed third exchange
    ]
    assert [st.get("accepted", False) for st in ev["steps"]] == [True, True, False]


def test_a_step_deadline_never_exceeds_the_overall_deadline() -> None:
    clock = Clock()
    d = S.Deadline(clock)
    overall = clock() + 10.0
    d.start_step(overall)
    assert d.at == overall  # min(step 30 s, overall 10 s)
    clock.t += 11
    with pytest.raises(S.DeadlineExceeded):
        d.start_step(overall)


# ------------------------------------------------------------------ D-48-2: socket-level enforcement (stream clamps)


class FakeStream(httpcore.NetworkStream):
    def __init__(self) -> None:
        self.timeouts: list[float | None] = []

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self.timeouts.append(timeout)
        return b"x"

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.timeouts.append(timeout)

    def close(self) -> None:
        pass

    def get_extra_info(self, info: str) -> Any:
        return None


def test_every_socket_operation_is_clamped_to_the_remaining_time() -> None:
    clock = Clock()
    d = S.Deadline(clock)
    d.at = clock() + 2.0
    inner = FakeStream()
    s = S.DeadlineStream(inner, d)
    s.read(10, timeout=60.0)
    s.read(10, timeout=None)
    assert inner.timeouts == [2.0, 2.0]  # never longer than the deadline, even when httpx asks for 60 s or no limit
    clock.t += 2.0
    with pytest.raises(httpcore.ReadTimeout):
        s.read(10, timeout=60.0)
    with pytest.raises(httpcore.WriteTimeout):
        s.write(b"x", timeout=60.0)
    assert d.expired and len(inner.timeouts) == 2  # the expired operations never reached the socket


# ------------------------------------------------------------------ D-48-2: real loopback sockets (short real time)


class Server:
    """Loopback only. mode: 'trickle' (headers, then one byte every 50 ms forever) or 'silent' (accept, say nothing)."""

    def __init__(self, mode: str) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.mode, self.stop = mode, threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self) -> None:
        conn, _ = self.sock.accept()
        with conn:
            conn.recv(65536)
            if self.mode == "trickle":
                conn.sendall(b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ntransfer-encoding: chunked\r\n\r\n")
                while not self.stop.is_set():
                    try:
                        conn.sendall(b"1\r\n \r\n")
                    except OSError:
                        return
                    time.sleep(0.05)
            else:
                self.stop.wait(10)

    def close(self) -> None:
        self.stop.set()
        self.sock.close()


@pytest.mark.parametrize("mode", ["trickle", "silent"])
def test_real_socket_operation_is_cut_off_at_the_wall_clock_deadline(mode: str) -> None:
    srv = Server(mode)
    d = S.Deadline(time.monotonic)
    d.at = time.monotonic() + 0.5
    transport = S.DeadlineHTTPTransport(d)
    client = httpx.Client(transport=transport, timeout=60.0, trust_env=False)  # httpx alone would wait 60 s
    t0 = time.monotonic()
    try:
        with pytest.raises(httpx.TransportError), client.stream("POST", f"http://127.0.0.1:{srv.port}/", content=b"{}") as r:
            for _ in r.iter_bytes():
                pass
    finally:
        client.close()
        srv.close()
    elapsed = time.monotonic() - t0
    assert d.expired and elapsed < 1.5  # stopped at ~0.5 s (plus the watchdog interval), not after 60 s


def test_name_resolution_is_bounded_by_the_deadline() -> None:
    d = S.Deadline(time.monotonic)
    d.at = time.monotonic() + 0.3

    def slow_resolver(*_a: Any, **_k: Any) -> Any:
        time.sleep(3)
        return []

    backend = S.DeadlineBackend(d, resolver=slow_resolver)
    t0 = time.monotonic()
    with pytest.raises(httpcore.ConnectTimeout):
        backend.connect_tcp("example.invalid", 443, timeout=60.0)
    assert time.monotonic() - t0 < 1.0 and d.expired


def test_the_live_transport_uses_the_deadline_backend_and_no_retries() -> None:
    d = S.Deadline(time.monotonic)
    t = S.DeadlineHTTPTransport(d)
    pool = t._pool
    assert isinstance(pool, httpcore.ConnectionPool) and isinstance(pool._network_backend, S.DeadlineBackend)
    assert pool._retries == 0
    t.close()


def test_the_watchdog_interrupts_an_operation_already_blocked_past_the_clamp() -> None:
    """An operation that is not clamped (as inside a multi-step TLS handshake or a split write) is still stopped:
    the watchdog shuts the socket down at the deadline. Here a raw read blocks with a 10 s socket timeout."""
    srv = Server("silent")
    d = S.Deadline(time.monotonic)
    d.at = time.monotonic() + 0.3
    backend = S.DeadlineBackend(d)
    try:
        stream = backend.connect_tcp("127.0.0.1", srv.port, timeout=5.0)
        stream.inner.write(b"GET / HTTP/1.1\r\n\r\n", 5.0)
        t0 = time.monotonic()
        try:
            got = stream.inner.read(1024, 10.0)  # bypasses the clamp on purpose
        except httpcore.ReadError:
            got = b""
        elapsed = time.monotonic() - t0
        assert got == b"" and elapsed < 1.0 and d.expired  # woken at ~0.3 s by the shutdown, not after 10 s
        stream.close()
    finally:
        backend.close()
        srv.close()
