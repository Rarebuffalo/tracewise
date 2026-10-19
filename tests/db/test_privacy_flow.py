"""Phase 29: independent end-to-end privacy audit with synthetic secrets (real DB, worker, publisher; fake GitHub,
scripted model, local git host). Secrets are planted in the workflow log, in every model-written field (including
nested lists, replacement code and fields the model may not set), in a malformed first model answer, in a tool-call
argument, and in a GitHub error body that forces a retry. Assertions report only WHERE a leak happened, never the
value. The run must still end `diagnosed`, so the full persistence and publication path is exercised.

Known, documented limit (not asserted here): redaction is pattern-based. A secret that is split across lines, encoded
(base64, hex) or in an unrecognised format is not detected (SECURITY-AUDIT §6, P-4)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator

import httpx
import pytest

from tests.db.test_analyze_worker import World, call, final, head, server  # noqa: F401 - module fixtures
from tests.github_fake import jresp
from tracewise.investigate.provider import StepResponse, StepUsage
from tracewise.logging import JsonFormatter, quiet_libraries, secret_filter

# Distinctive synthetic markers inside canonical secret shapes (never real credentials).
MARK = {
    "github_pat": "ghp_" + "Zq9" * 12,  # 36 chars after the prefix
    "aws_key_id": "AKIA" + "QWERTYUIOPASDFGH",
    "slack": "xoxb-" + "1234567890-zqzqzqzqzq",
    "jwt": "eyJzqzqzqzq1." + "eyJzqzqzqzq2." + "sigzqzqzqzq3",
    "pg_password": "postgresql://svc:PwZqZqZq9988@db.internal/app",
    "bearer": "Authorization: Bearer ZqBearer0123456789",
    "openai": "sk-proj-" + "Zq" * 15,
    "private_key": "-----BEGIN RSA PRIVATE KEY-----MIIEZqZqZqKeyBody",
}
# What must never appear (the secret-bearing part of each marker).
NEEDLES = {
    "github_pat": "Zq9Zq9Zq9Zq9",
    "aws_key_id": "QWERTYUIOPASDFGH",
    "slack": "zqzqzqzqzq",
    "jwt": "eyJzqzqzqzq2",
    "pg_password": "PwZqZqZq9988",
    "bearer": "ZqBearer0123456789",
    "openai": "ZqZqZqZqZqZqZqZq",
    "private_key": "MIIEZqZqZqKeyBody",
}
ALL = " ".join(MARK.values())


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(JsonFormatter())
        self.addFilter(secret_filter)  # as configured in production
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def logs() -> Iterator[Capture]:
    h = Capture()
    root = logging.getLogger()
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.DEBUG)
    quiet_libraries()
    try:
        yield h
    finally:
        root.removeHandler(h)
        root.setLevel(old)


def leaks(where: str, text: str) -> list[str]:
    return [f"{name}@{where}" for name, n in NEEDLES.items() if n in text]


def test_no_synthetic_secret_reaches_db_logs_or_github(pool, owner, server, tmp_path, head, logs) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    secret_answer = {
        "root_cause": f"total() returns only the tax; {MARK['github_pat']} {MARK['aws_key_id']} {MARK['pg_password']}",
        "why": f"coffee_shop/pricing.py:41 multiplies by TAX_RATE alone. {ALL}",
        "fix": {
            "description": f"Multiply by (1 + TAX_RATE). {MARK['github_pat']} {MARK['aws_key_id']}",
            "replacement": {
                "path": "coffee_shop/pricing.py",
                "line_start": 41,
                "line_end": 41,
                "new_text": f"    return round(subtotal_ * (1 + TAX_RATE), 2)  # {MARK['github_pat']} {MARK['openai']}",
            },
            "size": "trivial",
        },
        "next_steps": [f"Rotate {MARK['slack']}", f"Check {MARK['jwt']}", f"Remove {MARK['pg_password']}"],
        "file_verdicts": [{"path": "coffee_shop/pricing.py", "verdict": f"line 41 {MARK['bearer']}"}],
        "attribution": {"statement": ALL},  # a field the model may not set: dropped
        "confidence": ALL,
    }
    malformed = StepResponse(text="{not json " + ALL, usage=StepUsage(10, 10))
    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[
            [
                call("grep", "g", pattern=MARK["aws_key_id"]),
                call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41),
                malformed,
                final(**secret_answer),
            ],
            [call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), final(**secret_answer)],
        ],
    )
    # Secrets in the workflow log, on the failing assertion line (so they are inside the stored excerpt).
    blob = re.compile(r"^//productionresultssa1\.blob\.core\.windows\.net/logs/101\.txt$")
    original = next(h for m, p, h in w.gh.routes if m == "GET" and p.pattern == blob.pattern)

    def secret_log(req: httpx.Request) -> httpx.Response:
        text = original(req).text.replace("E   assert 0.21 == 1.21", f"E   assert 0.21 == 1.21  {ALL}")
        return httpx.Response(200, text=text)

    w.gh.routes.insert(0, ("GET", blob, secret_log))
    # A GitHub error whose body carries secrets, forcing a retry of the job.
    cr = re.compile(r"^/repos/acme/coffee/check-runs$")
    state = {"failed": False}
    orig_cr = next(h for m, p, h in w.gh.routes if m == "POST" and p.search("/repos/acme/coffee/check-runs"))

    def failing_once(req: httpx.Request) -> httpx.Response:
        if not state["failed"]:
            state["failed"] = True
            return jresp(500, {"message": f"backend exploded {ALL}"})
        return orig_cr(req)

    w.gh.routes.insert(0, ("POST", cr, failing_once))

    jid = w.enqueue()
    w.run()
    assert w.jobrow(jid)["status"] == "retry_wait"  # the failed publication was recorded, then retried
    w.ready(jid)
    w.run()
    assert w.jobrow(jid)["status"] == "succeeded"
    status, diag = owner.execute("SELECT status, diagnosis FROM analysis").fetchone()
    assert status == "diagnosed" and diag["problem_snippet"] and diag["fix"] and diag["next_steps"]  # path really exercised
    assert any("REDACTED" in pe["excerpt"] for pe in diag["primary_errors"])  # the log secrets were in the excerpt window

    found: list[str] = []
    tables = (
        "installation",
        "repository",
        "webhook_delivery",
        "workflow_run",
        "job",
        "analysis",
        "publication",
        "failure_signature",
        "usage_event",
        "audit_event",
        "recovery_checkpoint",
        "redelivery_request",
    )
    for t in tables:
        dump = "\n".join(r[0] for r in owner.execute(f"SELECT to_jsonb(x)::text FROM {t} x"))  # noqa: S608
        found += leaks(f"db.{t}", dump)
    found += leaks("logs", "\n".join(logs.lines))
    bodies = [c["body"] for c in w.all_ccs()] + [json.dumps(c.get("output")) for c in w.state.check_runs]
    found += leaks("github", "\n".join(bodies))
    assert found == [], f"{len(found)} leak(s): {sorted(found)}"  # names and locations only, never values
    assert w.all_ccs() and w.state.check_runs  # published
