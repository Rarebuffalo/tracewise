"""Phase 29: what reaches the model provider.

* AT-SEC-04 (explicit requirement): an AWS key, a `ghp_` token, a JWT and a Postgres URL in a LOG must be absent from
  the fake-provider request capture. Only the redaction half was tested before (test_sanitize.py).
* P-2 (open decision, documented here, not changed): secrets in REPOSITORY content (source windows, grep lines, the
  trigger diff) currently reach the provider unredacted. This test pins that behaviour so a policy change is visible.
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


def test_p2_repository_content_reaches_the_provider_unredacted_today() -> None:
    """PENDING P-2: documents current behaviour, not a decision."""
    marker = "ghp_" + "Rq7" * 12
    lines = PRICING.splitlines(keepends=True)
    lines[35] = lines[35].rstrip("\n") + f"  # {marker}\n"
    p = ScriptedProvider([tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), *b02_script()[1:]])
    diagnose(evidence(files={**B02_FILES, "coffee_shop/pricing.py": "".join(lines)}), p)
    assert "Rq7Rq7Rq7Rq7" in _sent(p)  # the source window was sent as-is
