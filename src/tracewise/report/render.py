"""Deterministic Markdown report from a validated diagnosis (T-501; FS-RPT-1..10, FS-CTX-6, FS-SEC-1).

* Input is a `ValidatedDiagnosis`; its digest is checked first (no alteration after validation).
* Observed facts (log excerpts, code snippet, files examined, attribution) are labelled separately
  from the assessment (root cause, why, fix), which is model text that passed validation.
* Untrusted text is escaped: HTML and Markdown metacharacters, @mentions and #refs neutralised,
  control characters removed. Code and log text go in fences longer than any backtick run inside.
* Every link is built here from validated IDs (rule 7); no model or log text becomes a link.
* The suggested fix is text only; nothing is applied anywhere.
* Size: whole low-priority sections are dropped first, so fences are never cut; hard cap last.
* Output has no timestamps or randomness: same input → byte-identical report. A final redaction
  pass removes secret-shaped strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from tracewise.context.paths import validate_owner_repo
from tracewise.contracts import Category, Diagnosis, Status
from tracewise.investigate.validate import ValidatedDiagnosis
from tracewise.prepass.sanitize import redact

DEFAULT_MAX_CHARS = 60_000  # FS-RPT-10 provisional cap
GITHUB = "https://github.com"
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|~>-])")
_MARKER = re.compile(r"^[a-z0-9:._-]{1,80}$")

CATEGORY_LABEL = {
    Category.code_regression: "Code regression",
    Category.test_defect: "Test defect",
    Category.dependency: "Dependency problem",
    Category.config_secret: "Configuration or secret problem",
    Category.infra_runner: "Runner or infrastructure problem",
    Category.flaky_suspect: "Suspected flaky failure",
    Category.workflow_invalid: "Invalid workflow",
    Category.unknown: "Unknown",
}
NO_ERROR_IN_RETAINED_LOG = (
    "no error line was found in the retained part of the log; the log was incomplete (truncated or partly "
    "unavailable), so the error may be in the part that is missing"
)


def reason_text(d: Diagnosis, default: str) -> str:
    """Reason wording. With a truncated log, 'no error line' describes only what was retained (Phase 37)."""
    if d.inconclusive_reason == "no_error_line" and d.limits.log_truncated:
        return NO_ERROR_IN_RETAINED_LOG
    return REASON_TEXT.get(d.inconclusive_reason or "", default)


REASON_TEXT = {
    "no_error_line": "the log has no error line to anchor a diagnosis (only an exit code, timeout or kill)",
    "provider_timeout": "the AI investigation timed out",
    "provider_failed": "the AI investigation could not be completed",
    "budget_exhausted": "the investigation reached its tool-call or time budget",
    "unproductive": "the investigation stopped making progress",
    "invalid_output": "the AI answer did not match the required structure",
    "model_abstained": "the evidence was not sufficient to name a cause",
    "location_not_examined": "the proposed code location was not among the code actually read",
    "location_invalid_path": "the proposed code location was not a valid repository path",
    "location_invalid_range": "the proposed line range was invalid",
    "location_beyond_eof": "the proposed lines do not exist in the file",
    "location_unreadable": "the proposed file could not be read at this commit",
    "no_location_for_code_category": "a code cause was proposed without a verified code location",
    "primary_error_unresolved": "the error lines could not be verified in the retained log",
    "no_failed_jobs": "no failed job was found for this run attempt",
    "not_investigated": "no investigation was run",
    "logs_unavailable": "the job logs are no longer available",
    "permission_denied": "Tracewise lacks permission to read this run's logs",
    "internal_inconsistency": "the result failed internal consistency checks",
}
BASIS_TEXT = {
    "location_examined": "the cited lines were read at this commit",
    "error_references_location": "the error output points at the cited lines",
    "changed_line_at_location": "the push changed the cited lines",
    "error_references_file": "the error output mentions the cited file",
    "not_corroborated": "no deterministic corroboration of the cited lines",
    "corroborated_but_degraded": "corroborated, but downgraded by other checks",
    "log_truncated": "the log was truncated",
    "no_location": "no code location",
    "error_line_present": "an error line is present",
}


_AUTOLINK = re.compile(r"(?i):/|www\\?\.")  # `scheme://` and `www.` (the dot may already be escaped)


def esc(text: str | None, *, single_line: bool = True) -> str:
    """Escape untrusted text for inline Markdown on GitHub."""
    if not text:
        return ""
    t = _CTRL.sub("", text)
    if single_line:
        t = " ".join(t.split())
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = _MD_SPECIAL.sub(r"\\\1", t)
    t = re.sub(r"@(?=[A-Za-z0-9])", "@​", t)  # break @user / @org/team mentions
    t = _AUTOLINK.sub(lambda m: m.group(0)[:-1] + "​" + m.group(0)[-1], t)  # break autolinks (A3, 2nd layer)
    return re.sub(r"(?<![\w&])\\?#(?=\d)", "#​", t)  # break #123 auto-references


def code(text: str | None) -> str:
    """Inline code span. Content is literal on GitHub (no Markdown, HTML or mentions), so it is not
    backslash-escaped; only control characters are removed and the fence outgrows inner backticks."""
    t = " ".join(_CTRL.sub("", text or "").split()) or " "
    longest = max((len(m) for m in re.findall(r"`+", t)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if t.startswith("`") or t.endswith("`") else ""
    return f"{ticks}{pad}{t}{pad}{ticks}"


def fence(text: str, lang: str = "") -> str:
    body = _CTRL.sub("", text).replace("\r", "").rstrip("\n")
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{body}\n{ticks}"


@dataclass(frozen=True)
class Links:
    run: str
    commit: str
    jobs: dict[int, str]

    def blob(self, sha: str, path: str, start: int, end: int) -> str:
        return f"{self.commit.rsplit('/commit/', 1)[0]}/blob/{sha}/{quote(path, safe='/')}#L{start}-L{end}"


def build_links(d: Diagnosis) -> Links:
    owner, repo = validate_owner_repo(d.run.repo)
    base = f"{GITHUB}/{quote(owner)}/{quote(repo)}"
    run = f"{base}/actions/runs/{int(d.run.run_id)}/attempts/{int(d.run.attempt)}"
    jobs = {f.job_id: f"{base}/actions/runs/{int(d.run.run_id)}/job/{int(f.job_id)}" for f in d.failed}
    return Links(run=run, commit=f"{base}/commit/{d.run.head_sha}", jobs=jobs)


def _basis(codes: list[str]) -> str:
    out = []
    for c in codes:
        key = c.split(":", 1)[0]
        if key == "conflicts_with_error_location":
            out.append("a compiler/linter error points at a different file")
        elif key == "validation_flags":
            out.append("some unverifiable details were removed")
        elif key == "not_diagnosed":
            out.append("not diagnosed")
        else:
            out.append(BASIS_TEXT.get(key, key.replace("_", " ")))
    return "; ".join(out)


def _what_failed(d: Diagnosis, links: Links) -> str:
    jobs = {f.job_id: f for f in d.failed}
    parts = ["### What failed (observed in the log)"]
    for i, p in enumerate(d.primary_errors, 1):
        j = jobs.get(p.log_ref.job_id)
        where = f"[{esc(j.job)}]({links.jobs[j.job_id]})" if j and j.job_id in links.jobs else "job"
        parts.append(f"**Error {i}** in {where}, log lines {p.log_ref.line_start}–{p.log_ref.line_end}:")
        parts.append(fence("\n".join(p.excerpt.splitlines()[:15])))
        if p.siblings.count:
            names = ", ".join(esc(n) for n in p.siblings.names[:5])
            more = f" and {p.siblings.count - 5} more" if p.siblings.count > 5 else ""
            parts.append(f"{p.siblings.count} similar failure(s) with the same signature: {names}{more}.")
    return "\n\n".join(parts) if d.primary_errors else ""


def _files(d: Diagnosis) -> str:
    if not d.files_examined:
        return ""
    rows = [f"- {code(f.path)} lines {f.start}–{f.end}" + (f" — {esc(f.verdict)}" if f.verdict else "") for f in d.files_examined]
    return "### Files examined (from the tool log)\n\n" + "\n".join(rows)


def _agent_block(d: Diagnosis) -> str:
    """FS-RPT-8: plain text, no URLs, only for diagnosed code/test categories."""
    if d.status is not Status.diagnosed or d.category not in (Category.code_regression, Category.test_defect):
        return ""
    f = d.failed[0] if d.failed else None
    loc = d.problem_location
    cmd = re.sub(r"\S*://\S*", "[url removed]", f.command or "") if f else ""
    lines = [
        f"repository: {d.run.repo}",
        f"commit: {d.run.head_sha}",
        f"job: {f.job if f else '?'} / step: {f.step if f and f.step else '?'}",
        f"reproduce: {cmd or 'see the failed step'}",
        f"location: {loc.path}:{loc.line_start}" + (f"-{loc.line_end}" if loc and loc.line_end != loc.line_start else "")
        if loc
        else "location: none",
        f"fix: {d.fix.description if d.fix else 'none suggested'}",
        f"verify: {cmd or 're-run the failed step'}",
    ]
    text = "\n".join(re.sub(r"\S*://\S*", "[url removed]", ln) for ln in lines)
    return "### For AI agents\n\n" + fence(text, "text")


def render(vd: ValidatedDiagnosis, *, max_chars: int = DEFAULT_MAX_CHARS, marker: str | None = None) -> str:
    d = vd.verify()
    links = build_links(d)
    sections: list[tuple[int, str]] = []  # (priority: lower = keep longer, text)
    head = f"<!-- tracewise:{marker} -->\n" if marker and _MARKER.match(marker) else ""
    f0 = d.failed[0] if d.failed else None
    where = f"{code(f0.job)} › {code(f0.step or 'unknown step')}" if f0 else "this run"

    if d.status is Status.diagnosed:
        sections.append((0, f"{head}## Tracewise: {CATEGORY_LABEL[d.category]} in {where}"))
        summary = [
            f"- **Job / step:** {where}",
            f"- **Command:** {code(f0.command)}" if f0 and f0.command else "- **Command:** not identified",
            f"- **Likely root cause (assessment):** {esc(d.root_cause)}",
            f"- **Confidence:** {d.confidence.band.value.capitalize()} — {esc(_basis(d.confidence.basis))}",
            f"- **Fix size:** {d.fix.size if d.fix else 'no code fix suggested'}",
        ]
        sections.append((0, "\n".join(summary)))
        sections.append((1, _what_failed(d, links)))
        sections.append((2, "### Why it failed (assessment)\n\n" + esc(d.why)))
        if d.problem_location:
            loc = d.problem_location
            link = links.blob(d.run.head_sha, loc.path, loc.line_start, loc.line_end)
            block = (
                f"### Problematic code (observed at `{d.run.head_sha[:12]}`)\n\n[{code(f'{loc.path}:{loc.line_start}')}]({link})"
            )
            if d.problem_snippet:
                block += "\n\n" + fence(d.problem_snippet)
            sections.append((2, block))
        if d.fix:
            fx = "### Suggested fix (text only; not applied)\n\n" + esc(d.fix.description)
            if d.fix.replacement:
                r = d.fix.replacement
                fx += f"\n\nReplace lines {r.line_start}–{r.line_end} of {code(r.path)} with:\n\n" + fence(r.new_text)
            sections.append((2, fx))
        if d.next_steps:
            sections.append((3, "### Next steps\n\n" + "\n".join(f"{i}. {esc(s)}" for i, s in enumerate(d.next_steps, 1))))
        sections.append((4, _files(d)))
        sections.append((5, _agent_block(d)))
    else:
        title = {Status.logs_unavailable: "logs unavailable", Status.permission_denied: "missing permission"}.get(
            d.status, "could not determine the root cause"
        )
        sections.append((0, f"{head}## Tracewise: {title} for {where}"))
        reason = reason_text(d, "the evidence was insufficient")
        sections.append(
            (
                0,
                f"Tracewise did not name a root cause because {reason}. "
                "No fix is suggested. This is a deliberate outcome, not an error in your build.",
            )
        )
        sections.append((1, _what_failed(d, links)))
        sections.append((1, "### What would help\n\n" + "\n".join(f"{i}. {esc(s)}" for i, s in enumerate(d.next_steps, 1))))
        sections.append((4, _files(d)))

    if d.attribution is not None:
        sections.append((1, "### Attribution (computed from the push's diff)\n\n" + esc(d.attribution.statement)))
    notes = []
    if d.limits.log_truncated:
        notes.append("Part of the log was not retained or was unavailable.")
    if d.limits.diff_truncated:
        notes.append("The push's diff was truncated.")
    if d.limits.files_skipped:
        notes.append(f"{len(d.limits.files_skipped)} file(s) were skipped (too large, binary, submodule or unsafe link).")
    if d.validation_flags:
        notes.append("Some details proposed by the AI could not be verified and were removed or downgraded.")
    if d.run.event == "pull_request":
        notes.append(
            "This run tested the merge of the pull request with its base branch, so the base branch may also "
            "contribute to the failure."
        )  # FS-CTX-6
    if notes:
        sections.append((1, "### Limits\n\n" + "\n".join(f"- {n}" for n in notes)))
    job_links = " · ".join(f"[Job: {esc(f.job)}]({links.jobs[f.job_id]})" for f in d.failed if f.job_id in links.jobs)
    sections.append(
        (0, f"[Run]({links.run}) · [Commit `{d.run.head_sha[:12]}`]({links.commit})" + (f" · {job_links}" if job_links else ""))
    )
    sections.append(
        (
            0,
            "<sub>Generated by Tracewise. The root cause, explanation and fix are an automated assessment "
            "checked against the log and the code at this commit; review before applying.</sub>",
        )
    )

    kept = [(p, s) for p, s in sections if s]
    omitted = False
    while True:
        body = [s for _, s in kept]
        if omitted:
            body.insert(-1, "… (some sections were omitted to fit the size limit)")
        out = redact("\n\n".join(body) + "\n")
        if len(out) <= max_chars:
            return out
        droppable = [i for i, (p, _) in enumerate(kept) if p > 0]
        if not droppable:
            return out[: max_chars - 45] + "\n\n… (report truncated to the size limit)\n"
        del kept[max(droppable, key=lambda i: (kept[i][0], i))]  # lowest priority, latest first
        omitted = True


# ---------------------------------------------------------------- publication helpers (T-502/T-503)

CHECK_TEXT_MAX = 65_535  # GitHub check-run output.text limit
_PERMISSION_TEXT = {
    "pull_requests": "Pull requests: write",
    "checks": "Checks: write",
    "contents": "Contents: read",
    "actions": "Actions: read",
}


@dataclass(frozen=True)
class CheckOutput:
    title: str
    summary: str
    text: str
    annotations: tuple[dict[str, object], ...] = ()


def check_output(vd: ValidatedDiagnosis, text: str) -> CheckOutput:
    """Check Run fields (FS-PUB-3). `text` is the rendered report; title/summary state the uncertainty."""
    d = vd.verify()
    if d.status is Status.diagnosed:
        title = f"{CATEGORY_LABEL[d.category]} ({d.confidence.band.value} confidence)"
        summary = f"**Likely root cause (assessment):** {esc(d.root_cause)}"
    else:
        title = {Status.logs_unavailable: "Logs unavailable", Status.permission_denied: "Missing permission"}.get(
            d.status, "Root cause not determined"
        )
        summary = "Tracewise did not name a root cause: " + reason_text(d, "insufficient evidence") + "."
    annotations: list[dict[str, object]] = []
    if d.status is Status.diagnosed and d.problem_location is not None:
        loc = d.problem_location
        annotations.append(
            {
                "path": loc.path,
                "start_line": loc.line_start,
                "end_line": loc.line_end,
                "annotation_level": "notice",
                "title": "Tracewise",
                "message": redact(_CTRL.sub("", d.root_cause or ""))[:1000] or "See the Tracewise report.",
            }
        )
    return CheckOutput(title[:120], summary[:2000], text[:CHECK_TEXT_MAX], tuple(annotations[:10]))


def render_could_not_complete(
    repo: str, run_id: int, attempt: int, head_sha: str, reason: str, *, marker: str | None = None, permission: str | None = None
) -> str:
    """FS-ERR-1 / FS-ERR-3: a short, safe notice. Never includes exception text, paths or provider errors."""
    owner, name = validate_owner_repo(repo)
    base = f"{GITHUB}/{quote(owner)}/{quote(name)}"
    head = f"<!-- tracewise:{marker} -->\n" if marker and _MARKER.match(marker) else ""
    if reason == "permission_denied":
        need = _PERMISSION_TEXT.get((permission or "").split("=")[0].split(":")[0], "a required permission")
        body = (
            f"Tracewise could not read this run because the app lacks **{esc(need)}** on this repository. "
            "No analysis was performed; grant the permission and re-run the job."
        )
        title = "missing permission"
    else:
        body = (
            "Tracewise could not complete the analysis of this run after several attempts. "
            "No root cause is claimed and no fix is suggested. Re-running the job will trigger a new analysis."
        )
        title = "could not complete the analysis"
    links = (
        f"[Run]({base}/actions/runs/{int(run_id)}/attempts/{int(attempt)}) · [Commit `{head_sha[:12]}`]({base}/commit/{head_sha})"
    )
    return redact(f"{head}## Tracewise: {title}\n\n{body}\n\n{links}\n")


def publication_notes(text: str, missing: dict[str, str | None]) -> str:
    """Append which surfaces could not be written and why (AT-REL-05), within the Check Run limit."""
    if not missing:
        return text
    label = {"pr_comment": "pull request comment", "commit_comment": "commit comment"}
    rows = [
        f"- The {label.get(s, s)} could not be posted: the app lacks "
        f"**{esc(_PERMISSION_TEXT.get((p or '').split('=')[0].split(':')[0], p or 'a required permission'))}**."
        for s, p in sorted(missing.items())
    ]
    note = "\n\n### Publication\n\n" + "\n".join(rows) + "\n"
    return (text[: CHECK_TEXT_MAX - len(note) - 1] + note) if len(text) + len(note) > CHECK_TEXT_MAX else text + note
