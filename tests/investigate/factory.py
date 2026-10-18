"""Offline Evidence bundles for investigator/validator/renderer tests (no git, no network).

Logs are real tool output (tests/fixtures/logs) wrapped in a GitHub-shaped envelope; the code is the
B-02 coffee-shop replica (defect at coffee_shop/pricing.py:41) held in memory.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from tests.context.memsource import MemSource
from tests.helpers import build_job, fixture
from tracewise.analysis.collect import Evidence
from tracewise.context.source import CodeSource
from tracewise.context.tools import ToolBox, ToolLimits
from tracewise.context.trigger import ChangedFile, TriggerDiff
from tracewise.contracts import AnalysisJob
from tracewise.investigate.provider import StepResponse, StepUsage, ToolCallRequest
from tracewise.prepass.primary import run_prepass

_spec = importlib.util.spec_from_file_location("gen", Path(__file__).resolve().parents[2] / "scripts" / "gen_python_fixtures.py")
assert _spec and _spec.loader
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
PRICING: str = _gen.PRICING
TESTS: str = _gen.TESTS
HEAD = "c1" * 20
PARENT = "c0" * 20
B02_FILES: dict[str, bytes | str] = {
    "coffee_shop/__init__.py": "",
    "coffee_shop/pricing.py": PRICING,
    "tests/test_pricing.py": TESTS,
    "README.md": "# Coffee shop\n",
}
PRICING_PATCH = (
    "@@ -40,2 +40,2 @@\n     # B-02 defect\n"
    "-    return round(subtotal_ * (1 + TAX_RATE), 2)\n+    return round(subtotal_ * TAX_RATE, 2)"
)


def job(event: str = "push") -> AnalysisJob:
    return AnalysisJob(
        installation_id=9,
        repo_id=7,
        repo="acme/coffee",
        run_id=55,
        attempt=1,
        workflow_id=3,
        head_sha=HEAD,
        event=event,
        conclusion="failure",
        delivery_id="d-1",
    )


def evidence(
    *,
    log: str | None = None,
    files: dict[str, bytes | str] | None = None,
    changed: str = "pricing",
    source: CodeSource | None = None,
    event: str = "push",
    step: str = "Run pytest",
    command: str = "pytest --tb=short -v",
    status: str = "ok",
    tool_limits: ToolLimits | None = None,
    truncated_log: bool = False,
) -> Evidence:
    info, lines = build_job(101, "Tests (Python 3.11)", step, command, log if log is not None else fixture("pytest_b02.out"))
    pre = run_prepass([(info, lines)])
    if truncated_log:
        for r in pre.logs.values():
            r.truncated = True
    diff = {
        "pricing": TriggerDiff(HEAD, PARENT, (ChangedFile("coffee_shop/pricing.py", "modified", 1, 1, None, PRICING_PATCH),)),
        "readme": TriggerDiff(
            HEAD, PARENT, (ChangedFile("README.md", "modified", 1, 0, None, "@@ -1 +1,2 @@\n # Coffee shop\n+x"),)
        ),
        "unknown": TriggerDiff(HEAD, None, known=False, reason="compare unavailable (NotFound)"),
    }[changed]
    src = source or MemSource(files if files is not None else B02_FILES)
    tools = ToolBox(src, diff_text=diff.render(), limits=tool_limits or ToolLimits())
    return Evidence(job(event), status, [info], pre if status == "ok" else None, diff, src, tools)  # type: ignore[arg-type]


def tool(name: str, cid: str = "c1", **args: Any) -> StepResponse:
    return StepResponse(tool_calls=(ToolCallRequest(cid, name, args),), usage=StepUsage(100, 20))


def answer(**fields: Any) -> StepResponse:
    return StepResponse(text=json.dumps(fields), usage=StepUsage(200, 80))


B02_ANSWER: dict[str, Any] = {
    "category": "code_regression",
    "root_cause": "total() returns only the tax (subtotal_ * TAX_RATE) instead of subtotal plus tax.",
    "why": "coffee_shop/pricing.py:41 multiplies the subtotal by TAX_RATE alone, so total([(1.0, 1)]) is 0.21 "
    "instead of 1.21; all four pricing tests compare against subtotal plus tax.",
    "problem_location": {"path": "coffee_shop/pricing.py", "line_start": 41, "line_end": 41},
    "fix": {
        "description": "Multiply by (1 + TAX_RATE) so the total includes the subtotal.",
        "replacement": {
            "path": "coffee_shop/pricing.py",
            "line_start": 41,
            "line_end": 41,
            "new_text": "    return round(subtotal_ * (1 + TAX_RATE), 2)",
        },
        "size": "trivial",
    },
    "next_steps": ["Run pytest tests/test_pricing.py after the change."],
    "file_verdicts": [{"path": "coffee_shop/pricing.py", "verdict": "line 41 returns only the tax"}],
}


def b02_script() -> list[StepResponse]:
    return [tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), answer(**B02_ANSWER)]
