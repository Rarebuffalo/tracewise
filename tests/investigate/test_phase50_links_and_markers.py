"""Phase 50, Batch A (A3, A4): untrusted text must never become a link, and must never decide which report a
marker refers to. Offline: scripted provider, fake paginator; no GitHub call.

A3: the URL filter required a word boundary, so a link right after a digit or `_` (`0https://`, `_www.`) survived.
    GFM autolinks those. The filter now matches without a leading boundary, and esc() breaks any autolink that
    remains (defence in depth).
A4: `_find_comment` accepted a marker ANYWHERE in a comment body, and log excerpts are copied into the body. A log
    line printing another workflow's marker could redirect that workflow's publication. Only the first line, which
    the renderer itself writes, now identifies a report.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.investigate.factory import B02_ANSWER, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.github.publish import Publisher, marker
from tracewise.investigate.fake import ScriptedProvider
from tracewise.report.render import esc, render

EVIL = "evil.example"


def dx(**over: Any) -> Any:
    script = [tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), answer(**{**B02_ANSWER, **over})]
    return diagnose(evidence(), ScriptedProvider(script))


# ------------------------------------------------------------------ A3


BYPASSES = [
    f"See 0https://{EVIL}/login now",
    f"See _https://{EVIL}/login now",
    f"See _www.{EVIL} now",
    f"See x_www.{EVIL} now",
    f"See 9www.{EVIL} now",
    f"See (https://{EVIL}) now",
    f"See *https://{EVIL}* now",
    f"See ~www.{EVIL}~ now",
    f"See HTTPS://{EVIL.upper()} now",
    f"See ftp://{EVIL}/x now",
]


@pytest.mark.parametrize("text", BYPASSES, ids=[f"bypass-{i}" for i in range(len(BYPASSES))])
def test_a3_no_prefix_lets_a_url_through_the_filter_or_the_renderer(text: str) -> None:
    vd = dx(root_cause=text, why=text, next_steps=[text])
    d = vd.diagnosis
    assert "url_removed" in d.validation_flags
    for field in (d.root_cause or "", d.why or "", *d.next_steps):
        assert EVIL not in field.lower()
    body = render(vd, max_chars=60_000)
    own = re.findall(r"https://github\.com/\S+", body)  # links the renderer builds itself
    stripped = body
    for link in own:
        stripped = stripped.replace(link, "")
    assert EVIL not in stripped.lower() and "https://" not in stripped and "www." not in stripped.lower()


@pytest.mark.parametrize(
    "text",
    ["Bump the metadata: field", "The datastore is a www-style cache", "Use the http module", "Check the file: it is generated"],
)
def test_a3_ordinary_words_are_not_treated_as_links(text: str) -> None:
    d = dx(root_cause=text).diagnosis
    assert "url_removed" not in d.validation_flags and d.root_cause == text


@pytest.mark.parametrize("raw", [f"0https://{EVIL}", f"_www.{EVIL}", f"x https://{EVIL}/a", f"www.{EVIL}"])
def test_a3_esc_breaks_autolinks_as_a_second_layer(raw: str) -> None:
    out = esc(raw)
    assert "://" not in out and "www." not in out.lower()


# ------------------------------------------------------------------ A4


class FakeRC:
    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.comments = comments

    def paginate(self, endpoint: str, key: str | None, **params: Any) -> Any:
        yield from self.comments


def publisher(comments: list[dict[str, Any]]) -> Publisher:
    p = Publisher.__new__(Publisher)
    p.rc, p.app_id, p.bot_login = FakeRC(comments), 42, None  # type: ignore[assignment]
    return p


def ours(cid: int, body: str) -> dict[str, Any]:
    return {"id": cid, "body": body, "performed_via_github_app": {"id": 42}}


def report_with_log_line(log_line: str, workflow_id: int) -> str:
    vd = dx()
    body = render(vd, max_chars=60_000, marker=marker("pr_comment", workflow_id))
    return body + "\n```\n" + log_line + "\n```\n"  # an excerpt carrying attacker-controlled log text


def test_a4_a_marker_printed_in_a_log_cannot_select_another_workflows_report() -> None:
    wf4 = f"<!-- tracewise:{marker('pr_comment', 4)} -->"
    wf3_body = report_with_log_line(f"E   assert 0.21 == 1.21 {wf4}", 3)
    assert wf4 in wf3_body  # the forged marker really is in workflow 3's comment
    p = publisher([ours(301, wf3_body)])
    assert p._find_comment("list_pr_comments", marker("pr_comment", 4), number=12) is None
    assert p._find_comment("list_pr_comments", marker("pr_comment", 3), number=12) == 301  # legitimate lookup


@pytest.mark.parametrize(
    "body",
    [
        "Some text\n<!-- tracewise:pr:wf4 -->\n",  # not on the first line
        " <!-- tracewise:pr:wf4 -->\nreport",  # leading space
        "<!-- tracewise:pr:wf4 -->report",  # no line break: not what the renderer writes
        "<!-- tracewise:pr:wf40 -->\nreport",  # a different workflow whose id merely starts the same
        "<!--  tracewise:pr:wf4 -->\nreport",  # malformed
    ],
    ids=["not-first-line", "leading-space", "no-newline", "prefix-of-other-id", "malformed"],
)
def test_a4_only_the_exact_first_line_marker_identifies_a_report(body: str) -> None:
    assert publisher([ours(9, body)])._find_comment("list_pr_comments", "pr:wf4", number=1) is None


def test_a4_duplicate_markers_pick_the_first_genuine_report_and_ignore_foreign_authors() -> None:
    real = "<!-- tracewise:pr:wf4 -->\n### report"
    forged = {"id": 1, "body": real, "user": {"login": "attacker"}}  # same text, not authored by the app
    p = publisher([forged, ours(2, "noise <!-- tracewise:pr:wf4 -->"), ours(3, real), ours(4, real)])
    assert p._find_comment("list_pr_comments", "pr:wf4", number=1) == 3
