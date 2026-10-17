"""AT-REL-04 end to end (offline): 50 failures from one installation arrive via the webhook;
real workers process them; at most 2 run concurrently for that installation while another
installation keeps progressing. The handler is a stub (the analysis pipeline is T-4xx/T-5xx)."""

from __future__ import annotations

import collections
import secrets
import threading
import time

from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.db.test_webhook import payload, post
from tracewise.config import Settings
from tracewise.jobs.worker import JobContext, Worker
from tracewise.web.app import create_app


def test_rel04_per_installation_concurrency_end_to_end(pool, owner) -> None:  # type: ignore[no-untyped-def]
    secret = secrets.token_hex(16)
    with TestClient(create_app(Settings(github_webhook_secret=SecretStr(secret)), pool)) as c:
        for i in range(50):
            assert post(c, secret, payload(run_id=5000 + i)).status_code == 202
        for i in range(5):
            other = payload(run_id=9000 + i)
            other["installation"]["id"] = 7777
            other["repository"]["id"] = other["workflow_run"]["repository"]["id"] = 2002
            assert post(c, secret, other).status_code == 202

    running: collections.Counter[int] = collections.Counter()
    peak: collections.Counter[int] = collections.Counter()
    finished_at: dict[int, list[float]] = collections.defaultdict(list)
    lock = threading.Lock()

    def handler(ctx: JobContext) -> dict[str, int]:
        inst = ctx.job.installation_id
        with lock:
            running[inst] += 1
            peak[inst] = max(peak[inst], running[inst])
        time.sleep(0.02)
        with lock:
            running[inst] -= 1
            finished_at[inst].append(time.perf_counter())
        return {"ok": 1}

    workers = [Worker(pool, {"analyze": handler}, f"w{i}", heartbeat_s=5) for i in range(6)]
    start = time.perf_counter()

    def loop(w: Worker) -> None:
        idle = 0
        while idle < 20:
            idle = 0 if w.run_once() else idle + 1
            if idle:
                time.sleep(0.01)

    threads = [threading.Thread(target=loop, args=(w,)) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)

    assert peak[4242] <= 2 and peak[7777] <= 2
    assert len(finished_at[4242]) == 50 and len(finished_at[7777]) == 5
    # The other installation was not starved behind the 50-job backlog.
    assert max(finished_at[7777]) - start < (max(finished_at[4242]) - start) * 0.5
    assert owner.execute("SELECT count(*) FROM job WHERE status = 'succeeded'").fetchone() == (55,)
