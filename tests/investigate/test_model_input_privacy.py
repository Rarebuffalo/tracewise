"""Phase 29: what reaches the model provider.

* AT-SEC-04 (explicit requirement): an AWS key, a `ghp_` token, a JWT and a Postgres URL in a LOG must be absent from
  the fake-provider request capture. Only the redaction half was tested before (test_sanitize.py).
* P-2 (APPROVED option A, Phase 45): secrets in REPOSITORY content (source windows, grep lines, directory listings,
  the trigger diff) and anything replayed to the model (its own malformed answers, its tool-call
  arguments) are redacted at the provider boundary. Checked on the fake-provider capture AND on the bytes the HTTP
  adapter actually serialises. Pattern-based: encoded, split or unfamiliar secrets can still pass (P-4).
"""

from __future__ import annotations

from tests.helpers import fixture
from tests.investigate.factory import B02_FILES, PRICING, b02_script, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.fake import ScriptedProvider

LOG_SECRETS = {
    "aws": "AKIA" + "ZQXWCEVRBTNYMUZQ",
    "ghp": "ghp_" + "Zq8" * 12,
    "jwt": "eyJzqLogAAA1." + "eyJzqLogBBB2." + "sigzqLogCC3",
    "pg": "postgresql://svc:LogPwZq7766@db.internal/app",
}
NEEDLES = {"aws": "ZQXWCEVRBTNYMUZQ", "ghp": "Zq8Zq8Zq8Zq8", "jwt": "eyJzqLogBBB2", "pg": "LogPwZq7766"}


def _sent(p: ScriptedProvider) -> str:
    return "\n".join(m.content + " " + " ".join(str(tc.arguments) for tc in m.tool_calls) for r in p.requests for m in r.messages)


def test_at_sec_04_log_secrets_never_reach_the_provider() -> None:
    planted = " ".join(LOG_SECRETS.values())
    log = fixture("pytest_b02.out").replace("E   assert 0.21 == 1.21", f"E   assert 0.21 == 1.21 {planted}")
    p = ScriptedProvider(b02_script())
    diagnose(evidence(log=log), p)
    sent = _sent(p)
    assert "assert 0.21 == 1.21" in sent  # the error line itself was sent (the check is meaningful)
    assert [k for k, n in NEEDLES.items() if n in sent] == []


REPO = {  # one distinct synthetic secret per repository-content path
    "window": "ghp_" + "Rq7" * 12,
    "grep": "AKIA" + "RQGREPLINEZZZZZZ",
    "diff": "xoxb-" + "4455667788-rqdiffrqdiff",
    "listing": "sk-proj-" + "RqList" * 5,
    "replayed": "eyJrqReplay1." + "eyJrqReplay2." + "sigrqReplay3",
    "argument": "AKIA" + "RQARGUMENTZZZZZZ",
}
REPO_NEEDLES = {
    "window": "Rq7Rq7Rq7Rq7",
    "grep": "RQGREPLINE",
    "diff": "rqdiffrqdiff",
    "listing": "RqListRqList",
    "replayed": "eyJrqReplay2",
    "argument": "RQARGUMENT",
}


def _repo_evidence(monkeypatch):  # type: ignore[no-untyped-def]
    import tests.investigate.factory as f

    lines = PRICING.splitlines(keepends=True)
    lines[35] = lines[35].rstrip("\n") + f"  # TAX_RATE note {REPO['window']} {REPO['grep']}\n"  # in window and grep hits
    monkeypatch.setattr(f, "PRICING_PATCH", f.PRICING_PATCH + f"\n+    # {REPO['diff']}")
    files = {**B02_FILES, "coffee_shop/pricing.py": "".join(lines), f"coffee_shop/{REPO['listing']}.txt": "x\n"}
    ev = evidence(files=files)
    return ev


def _script() -> list:  # type: ignore[type-arg]
    from tests.investigate.factory import B02_ANSWER, answer
    from tracewise.investigate.provider import StepResponse, StepUsage

    return [
        tool("read_file", "c1", path="coffee_shop/pricing.py", start=30, end=41),
        tool("grep", "c2", pattern="TAX_RATE"),
        tool("get_diff", "c3"),
        tool("list_dir", "c4", path="coffee_shop"),
        tool("grep", "c5", pattern=REPO["argument"]),  # the model puts a secret into a tool argument
        StepResponse(text="{not json " + REPO["replayed"], usage=StepUsage(1, 1)),  # malformed: replayed for repair
        answer(**B02_ANSWER),
    ]


def test_p2_repository_content_is_redacted_at_the_provider_boundary(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = ScriptedProvider(_script())
    vd = diagnose(_repo_evidence(monkeypatch), p)
    sent = _sent(p) + "\n".join(str(r.tools) for r in p.requests)
    leaked = [k for k, n in REPO_NEEDLES.items() if n in sent]
    assert leaked == []
    assert len(p.requests) == 7  # every tool round, the repair round and the final answer were really sent
    # ordinary, non-sensitive context still reaches the model, and the diagnosis is still made
    for ordinary in ("return round(subtotal_ * TAX_RATE, 2)", "coffee_shop/pricing.py", "TAX_RATE"):
        assert ordinary in sent
    assert vd.diagnosis.status.value == "diagnosed" and vd.diagnosis.problem_location is not None


def test_p2_redaction_holds_in_the_bytes_the_http_adapter_sends(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import httpx
    from pydantic import SecretStr

    from tests.investigate.test_http_adapter import Server, TestWire
    from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider

    server = Server(*_script())
    prov = HTTPProvider(
        TestWire(),
        SecretStr("adapter-key-0000001"),
        AdapterConfig("test-model-1"),
        client=httpx.Client(transport=httpx.MockTransport(server)),
    )
    vd = diagnose(_repo_evidence(monkeypatch), prov)
    wire = "\n".join(r.content.decode() for r in server.requests)
    assert [k for k, n in REPO_NEEDLES.items() if n in wire] == []
    assert vd.diagnosis.status.value == "diagnosed" and "return round(subtotal_" in wire
