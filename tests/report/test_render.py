"""T-501 renderer: AT-RPT-01..09, AT-RPT-11, AT-SEC-07 (offline; fake provider)."""

from __future__ import annotations

import re

import pytest

from tests.helpers import fixture
from tests.investigate.factory import B02_ANSWER, HEAD, PRICING, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.provider import ProviderTimeout
from tracewise.investigate.validate import ValidatedDiagnosis
from tracewise.report.render import esc, fence, render

URL_RE = re.compile(r"\((https://[^)\s]+)\)")


def vd(ev=None, **over):  # type: ignore[no-untyped-def]
    return diagnose(
        ev or evidence(),
        ScriptedProvider([tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), answer(**{**B02_ANSWER, **over})]),
    )


def test_rpt01_summary() -> None:
    out = render(vd())
    assert "## Tracewise: Code regression in `Tests (Python 3.11)` › `Run pytest`" in out
    assert "**Command:** `pytest --tb=short -v`" in out  # code span: literal, not backslash-escaped
    assert "**Likely root cause (assessment):**" in out and "**Confidence:** Medium" in out
    assert "**Fix size:** trivial" in out


def test_rpt02_verbatim_log_lines_and_siblings() -> None:
    v = vd()
    out = render(v)
    block = out.split("### What failed (observed in the log)")[1].split("```")[1]
    retained = set(fixture("pytest_b02.out").splitlines())
    lines = [ln for ln in block.strip("\n").splitlines() if ln]
    assert 1 <= len(lines) <= 15 and lines == ["E   assert 0.21 == 1.21"]
    assert all(any(ln in r for r in retained) for ln in lines)  # each shown line exists in the real log
    assert "3 similar failure(s)" in out and "test\\_total\\_two" in out


def test_rpt03_rpt05_why_and_fix() -> None:
    out = render(vd())
    why = out.split("### Why it failed (assessment)\n\n")[1].split("\n\n")[0]
    assert 0 < len(why) <= 800 * 2  # escaped text may be longer than the 800-char source
    assert "### Suggested fix (text only; not applied)" in out and "(1 + TAX_RATE)" in out
    dep = render(vd(category="dependency", problem_location=None))
    assert "Suggested fix" not in dep


def test_rpt04_rpt09_location_and_code_built_links() -> None:
    out = render(vd())
    assert f"[`coffee_shop/pricing.py:41`](https://github.com/acme/coffee/blob/{HEAD}/coffee_shop/pricing.py#L41-L41)" in out
    assert "coffee_shop/coffee_shop" not in out
    assert PRICING.splitlines()[40] in out  # snippet from the file at head_sha
    urls = URL_RE.findall(out)
    assert urls and all(
        re.fullmatch(
            rf"https://github\.com/acme/coffee/(actions/runs/55/attempts/1|actions/runs/55/job/101|commit/{HEAD}|"
            rf"blob/{HEAD}/coffee_shop/pricing\.py#L41-L41)",
            u,
        )
        for u in urls
    )


def test_rpt06_files_examined_equal_tool_log() -> None:
    v = vd()
    out = render(v)
    section = out.split("### Files examined (from the tool log)\n\n")[1].split("\n\n")[0]
    assert section == "- `coffee_shop/pricing.py` lines 30–41 — line 41 returns only the tax"
    assert [(f.path, f.start, f.end) for f in v.diagnosis.files_examined] == [("coffee_shop/pricing.py", 30, 41)]


def test_rpt07_attribution_always_present() -> None:
    for v in (vd(), vd(evidence(changed="readme")), diagnose(evidence(), ScriptedProvider([ProviderTimeout("t")]))):
        assert "### Attribution (computed from the push's diff)" in render(v)


def test_rpt08_agent_block_complete_without_urls() -> None:
    out = render(vd())
    block = out.split("### For AI agents\n\n")[1].split("```")[1]
    for key in (
        "repository: acme/coffee",
        f"commit: {HEAD}",
        "job: Tests (Python 3.11) / step: Run pytest",
        "reproduce: pytest --tb=short -v",
        "location: coffee_shop/pricing.py:41",
        "fix: ",
        "verify: ",
    ):
        assert key in block
    assert "://" not in block and "http" not in block
    assert "For AI agents" not in render(vd(category="dependency", problem_location=None))


def test_rpt11_pr_merge_caveat() -> None:
    assert "merge of the pull request with its base branch" in render(vd(evidence(event="pull_request")))
    assert "merge of the pull request" not in render(vd())


def test_sec07_untrusted_text_is_escaped() -> None:
    hostile = "Ping @acme/security-team <img src=x onerror=alert(1)> [click](http://evil.example) #123 **bold**"
    out = render(vd(root_cause=hostile[:300], why="See ![x](https://evil.example/p.png) and <script>alert(1)</script>"))
    assert "@acme" not in out and "@​acme/security\\-team" in out
    assert "<img" not in out and "<script" not in out and "&lt;img" in out
    assert "evil.example" not in out and "](http" not in out.replace("](https://github.com", "")
    assert "#123" not in out and "\\*\\*bold\\*\\*" in out


def test_code_spans_are_literal_and_cannot_break_out() -> None:
    from tracewise.report.render import code

    assert code("Tests (Python 3.11)") == "`Tests (Python 3.11)`"
    assert code("a`b") == "``a`b``" and code("`x`") == "`` `x` ``"
    assert code("x\n## Injected heading") == "`x ## Injected heading`"


def test_fence_and_escape_helpers() -> None:
    assert fence("a ``` b").startswith("````\n") and fence("x").startswith("```\n")
    assert esc("a\nb\x1b[31m") == "a b[31m".replace("[", "\\[")


def test_inconclusive_report_is_explicit() -> None:
    out = render(diagnose(evidence(), ScriptedProvider([ProviderTimeout("t")])))
    assert "could not determine the root cause" in out and "the AI investigation timed out" in out
    assert "No fix is suggested" in out and "### What would help" in out
    assert "Suggested fix" not in out and "For AI agents" not in out
    assert "E   assert 0.21 == 1.21" in out  # observed facts still shown


def test_logs_unavailable_and_permission_reports() -> None:
    assert "logs unavailable" in render(diagnose(evidence(status="logs_unavailable"), ScriptedProvider([])))
    assert "missing permission" in render(diagnose(evidence(status="permission_denied"), ScriptedProvider([])))


def test_determinism() -> None:
    outs = {render(vd()) for _ in range(5)}
    assert len(outs) == 1


def test_size_cap_drops_whole_sections_and_keeps_fences_balanced() -> None:
    v = vd()
    full = render(v)
    small = render(v, max_chars=1500)
    assert len(small) <= 1500 < len(full)
    assert small.count("```") % 2 == 0
    assert "some sections were omitted" in small and "## Tracewise:" in small
    tiny = render(v, max_chars=300)
    assert len(tiny) <= 300 and "truncated" in tiny


def test_marker_and_tamper_and_secrets() -> None:
    v = vd(why="Token ghp_" + "A" * 36 + " was printed. pricing.py:41 drops the subtotal.")
    out = render(v, marker="run:55")
    assert out.startswith("<!-- tracewise:run:55 -->\n") and "ghp_" not in out
    assert not render(v, marker="--><script>").startswith("<!--")
    with pytest.raises(ValueError):
        render(ValidatedDiagnosis(v.diagnosis.model_copy(update={"why": "x"}), v.digest))


def test_truncated_log_without_error_line_never_claims_the_log_has_no_error() -> None:
    """Phase 37: with a truncated log, 'no error line' only describes the RETAINED part. The report must not assert
    that the log has none (the error may lie beyond the download cap or the retention budget)."""
    from tracewise.report.render import check_output

    quiet = "\n".join(f"step output line {i}" for i in range(30)) + "\nProcess completed with exit code 1."
    complete = diagnose(evidence(log=quiet), ScriptedProvider([]))
    truncated = diagnose(evidence(log=quiet, truncated_log=True), ScriptedProvider([]))
    assert complete.diagnosis.inconclusive_reason == truncated.diagnosis.inconclusive_reason == "no_error_line"
    assert "the log has no error line" in render(complete)  # a complete log may say so
    for text in (render(truncated), check_output(truncated, render(truncated)).summary):
        assert "the log has no error line" not in text
        assert "retained" in text and "incomplete" in text  # it says what was actually checked
