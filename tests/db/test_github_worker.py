"""AT-REL-02 (offline, fake GitHub + real queue/worker): a 403 rate limit with reset +60 s reschedules the
job no earlier than the reset; the next attempt rides out a 502 and completes. "No duplicate publish"
needs the publishers (T-502) and is not claimed here."""

from __future__ import annotations

from tests.github_fake import FakeGitHub, jresp
from tracewise.db.session import transaction
from tracewise.github.client import RepoClient
from tracewise.jobs import queue
from tracewise.jobs.worker import JobContext, Worker

JOBS = r"^/repos/acme/app/actions/runs/5/attempts/1/jobs$"


def test_rel02_rate_limit_reschedules_then_completes(pool, owner) -> None:  # type: ignore[no-untyped-def]
    gh = FakeGitHub()
    gh.add_token_route()
    gh.route(
        "GET",
        JOBS,
        [
            jresp(403, {}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(gh.now) + 60)}),
            jresp(502),
            jresp(200, {"jobs": [{"id": 1, "conclusion": "failure"}]}),
        ],
    )
    http = gh.http()
    tokens = gh.provider(http)

    def handler(ctx: JobContext) -> dict[str, int]:
        rc = RepoClient(http, tokens, installation_id=9, repo_id=1, full_name="acme/app", scope="analysis")
        return {"failed_jobs": len(rc.failed_jobs(5, 1))}

    with transaction(pool) as c:
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="analyze:1:5:1", payload={}, run_key="1:5")
    w = Worker(pool, {"analyze": handler}, "w1", heartbeat_s=10)
    assert w.run_once()
    row = owner.execute("SELECT status, extract(epoch FROM run_after - now()) FROM job WHERE id = %s", (jid,)).fetchone()
    assert row[0] == "retry_wait" and float(row[1]) >= 59
    owner.execute("UPDATE job SET run_after = now() WHERE id = %s", (jid,))  # time passes
    assert w.run_once()
    status, result, attempts = owner.execute("SELECT status, result, attempts FROM job WHERE id = %s", (jid,)).fetchone()
    assert (status, result, attempts) == ("succeeded", {"failed_jobs": 1}, 2)
