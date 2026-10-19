"""Phase 18: `tracewise.worker.main()` with real OS signals, in-process in the main thread (signal handlers need it),
with the fake GitHub injected through `build` (the GitHub API host is fixed by design, so a subprocess must never
process a job). Asserts graceful shutdown, abort-and-recover, and exactly-once side effects."""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import Any

import pytest

from tests.db.test_analyze_worker import World, call, final, head, known, server  # noqa: F401 - module fixtures
from tracewise import worker as worker_main


def _runtime(world: World, closed: list[int]) -> Any:
    return lambda st, wid: worker_main.Runtime(world.worker(wid), lambda: closed.append(1))


def _later(fn: Any, *a: Any) -> threading.Thread:
    t = threading.Thread(target=fn, args=a, daemon=True)
    t.start()
    return t


def _side(world: World) -> tuple[int, int]:
    return world.state.count("POST", "cc"), world.state.count("POST", "cr")


def test_sigterm_mid_job_finishes_the_job_then_exits_cleanly(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    started = threading.Event()

    def slow(req: Any) -> Any:
        started.set()
        time.sleep(1.0)  # the signal arrives while the job is running
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), slow]],
    )
    jid = w.enqueue()

    def send() -> None:
        assert started.wait(30)
        os.kill(os.getpid(), signal.SIGTERM)

    _later(send)
    closed: list[int] = []
    handlers_before = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
    code = worker_main.main(["--idle-sleep", "0.05", "--worker-id", "wm1"], build=_runtime(w, closed))
    assert code == 0 and closed == [1]
    assert w.jobrow(jid)["status"] == "succeeded" and _side(w) == (1, 1)
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == handlers_before  # restored


def test_second_signal_aborts_and_the_job_is_recovered_exactly_once(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    started, never = threading.Event(), threading.Event()

    def hang(req: Any) -> Any:
        started.set()
        never.wait(30)  # interrupted by the second SIGINT
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), hang], *[known() for _ in range(3)]],
    )
    jid = w.enqueue()

    def send_twice() -> None:
        assert started.wait(30)
        os.kill(os.getpid(), signal.SIGINT)  # graceful stop requested
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGINT)  # impatient operator: abort now

    _later(send_twice)
    closed: list[int] = []
    with pytest.raises(KeyboardInterrupt):
        worker_main.main(["--idle-sleep", "0.05", "--worker-id", "wm2"], build=_runtime(w, closed))
    never.set()
    assert closed == [1]  # resources released even on abort
    assert w.jobrow(jid)["status"] == "running" and _side(w) == (0, 0)  # nothing published by the aborted run
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))
    w.http = w.gh.http()  # a new process
    w.tokens = w.gh.provider(w.http)
    assert worker_main.main(["--once", "--worker-id", "wm3"], build=_runtime(w, closed)) == 0
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("succeeded", 2) and _side(w) == (1, 1)


def test_unexpected_error_in_the_loop_stops_with_exit_1(pool, owner, server, tmp_path, head, monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    from tracewise.jobs import queue

    calls = {"n": 0}

    def broken_claim(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        raise RuntimeError("unexpected")

    monkeypatch.setattr(queue, "claim", broken_claim)
    closed: list[int] = []
    assert worker_main.main(["--idle-sleep", "0.01"], build=_runtime(w, closed)) == 1
    assert calls["n"] == 1 and closed == [1]  # stops on the first unexpected error: no spinning


def test_worker_wires_the_log_retention_setting_into_the_analysis(pg, owner, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Phase 31 (C-CFG-1): LOG_MAX_BYTES_PER_JOB reaches the analyze handler through the real build path."""
    from pydantic import SecretStr

    from tests.github_fake import test_key_pem as _key_pem
    from tests.pg import APP, SYSTEM
    from tracewise.config import Settings
    from tracewise.jobs.handlers import analyze as a

    key = tmp_path / "k.pem"
    key.write_bytes(_key_pem())
    seen: list[Any] = []
    real = a.make_analyze_handler
    monkeypatch.setattr(a, "make_analyze_handler", lambda deps: seen.append(deps) or real(deps))
    st = Settings(
        tw_env="test",
        llm_provider="fake",
        database_url=SecretStr(pg.url(APP)),
        database_url_system=SecretStr(pg.url(SYSTEM)),
        github_app_id=1,
        github_app_private_key_path=key,
        log_max_bytes_per_job=12345,
    )
    rt = worker_main.build_from_settings(st, "wiring")
    try:
        assert seen and seen[0].log_max_bytes == 12345
    finally:
        rt.close()


def test_signal_after_startup_but_before_the_loop_claims_nothing(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """Phase 43 (W-1): the window between 'worker.started' and the first claim. The handler stops the runtime that
    already exists, so the loop exits at once and the queued job is untouched."""
    from tracewise.jobs.worker import Worker

    w = World(pool, owner, server, tmp_path / "ws", head)
    jid = w.enqueue()

    class SignalsFirst(Worker):
        def run_forever(self, idle_sleep_s: float = 1.0, max_db_backoff_s: float = 30.0) -> None:
            os.kill(os.getpid(), signal.SIGTERM)  # arrives after start-up, before any claim
            super().run_forever(idle_sleep_s, max_db_backoff_s)

    base = w.worker("pre")
    closed: list[int] = []
    rt = worker_main.Runtime(SignalsFirst(base.pool, base.handlers, "pre"), lambda: closed.append(1))
    assert worker_main.main(["--idle-sleep", "0.05"], build=lambda st, wid: rt) == 0
    assert closed == [1] and w.jobrow(jid)["status"] == "queued" and w.state.writes == []
