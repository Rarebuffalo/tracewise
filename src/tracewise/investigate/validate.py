"""Evidence validation and the final Diagnosis (T-403; SPEC §3.2 rules 1-8, FS-DX-4/5/8, FS-SEC-1).

Everything the report shows as fact is built here by code from the evidence; model text is only
accepted after it passes the rules, and is still labelled as an assessment by the renderer.

Spec rules:
  1 primary_errors log refs resolve in the retained log; the excerpt is that exact text.
  2 problem_location lies inside a read_file range from the tool log; files_examined = tool log.
  3 fix.replacement targets the location's file and existing lines (else the replacement is dropped).
  4 paths named in model text must exist at head_sha (lines ≤ EOF), else "[unverified path]".
  5 attribution is computed by code (T-306) from pre-pass paths PLUS the validated location.
  6 rule 1 or 2 failure → inconclusive, fix removed, next steps kept.
  7 URL-like text from the model is removed (links are built by the renderer from IDs).
  8 high confidence needs deterministic corroboration (confidence.assess, D-5).
Additional hardening (documented in DECISIONS, flagged for review):
  H-1 sentences in model text claiming the push/commit caused or introduced the failure are removed
      (FS-ATR-1 forbids "caused by"; attribution is code-only).
  H-2 a fix or next step containing download-and-execute or destructive shell patterns is dropped (AT-SEC-08).
  H-3 a code category with no validated location, or category "unknown", is inconclusive (unsupported).

`ValidatedDiagnosis` carries a SHA-256 of the canonical JSON taken at validation time; the renderer
refuses a diagnosis whose content no longer matches (protection against alteration in between).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from tracewise.analysis.collect import Evidence
from tracewise.context.paths import UnsafePath, validate_repo_path
from tracewise.context.source import ReadStatus
from tracewise.context.trigger import relevance, to_attribution
from tracewise.contracts import (
    Band,
    Category,
    Confidence,
    Diagnosis,
    FileExamined,
    Fix,
    Limits,
    Location,
    LogRef,
    PrimaryError,
    Replacement,
    RunInfo,
    Siblings,
    Status,
    Usage,
)
from tracewise.investigate import confidence as conf
from tracewise.investigate.loop import InvestigationResult, has_error_line
from tracewise.investigate.schema import ModelDraft
from tracewise.prepass.sanitize import redact

MAX_EXCERPT_LINES = 15
MAX_SNIPPET_LINES = 15
_URL = re.compile(r"(?i)\b(?:https?|ftp|file|javascript|data|vbscript):[^\s<>\"')\]]*|\bwww\.[^\s<>\"')\]]+")
_MD_LINK = re.compile(r"\[([^\]\n]{0,200})\]\([^)\n]{0,2000}\)")
_PATH_TOKEN = re.compile(
    r"(?<![\w/.@-])((?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|cfg|ini|txt|md|lock|sh|go|rs|"
    r"java|rb|php|c|h|cpp|css|html|vue|svelte|sql|env))(?::(\d{1,7}))?(?![\w/])"
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_CAUSAL_VERB = re.compile(
    r"(?i)\b(?:caus(?:ed|es|ing)|introduc(?:ed|es|ing)|broke|broken by|responsible for|regress(?:ed|ion))\b"
)
_TRIGGER_REF = re.compile(r"(?i)\b(?:push|commit|pull request|PR)\b|\b(?:this|latest|recent|last|triggering|new)\s+change\b")
_DANGEROUS = re.compile(
    r"(?i)(?:\b(?:curl|wget|iwr|invoke-webrequest)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python\d?|perl|iex)\b"
    r"|\brm\s+-[a-z]*r[a-z]*f?\s+(?:/|~|\*)|\bbase64\s+-d[^\n|]{0,100}\|\s*(?:sh|bash)\b|\binvoke-expression\b|\biex\s*\("
    r"|\bchmod\s+\+x\b[^\n]{0,100}&&|\beval\s*\$\(|\bmkfifo\b|/dev/tcp/)"
)
DEFAULT_NEXT_STEPS = {
    "no_error_line": [
        "Open the failed step's log and look for the first error above the exit code.",
        "Re-run the job with step debug logging (ACTIONS_STEP_DEBUG=true).",
    ],
    "logs_unavailable": ["Check whether the run's logs expired or were deleted, then re-run the job."],
    "permission_denied": ["Grant the Tracewise app read access to Actions for this repository."],
}
GENERIC_NEXT_STEPS = [
    "Inspect the failed step's log around the first error.",
    "Re-run the job; if it passes, treat the failure as possibly flaky.",
]


@dataclass(frozen=True)
class ValidatedDiagnosis:
    diagnosis: Diagnosis
    digest: str

    def verify(self) -> Diagnosis:
        if _digest(self.diagnosis) != self.digest:
            raise ValueError("diagnosis changed after validation")
        return self.diagnosis


def _digest(d: Diagnosis) -> str:
    return hashlib.sha256(json.dumps(d.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class _Text:
    """Applies rules 4 and 7 and H-1 to model text, collecting flags."""

    def __init__(self, ev: Evidence, flags: list[str]) -> None:
        self.ev, self.flags = ev, flags
        self._eof: dict[str, int | None] = {}

    def _lines(self, path: str) -> int | None:
        if path not in self._eof:
            r = self.ev.source.read(path) if self.ev.source.available else None
            self._eof[path] = len(r.text.splitlines()) if r and r.status is ReadStatus.ok and r.text is not None else None
        return self._eof[path]

    def clean(self, text: str | None, limit: int) -> str | None:
        if text is None:
            return None
        out = _MD_LINK.sub(lambda m: m.group(1), text)
        if _URL.search(out):
            out = _URL.sub("[link removed]", out)
            self._flag("url_removed")

        def causal(m: re.Match[str]) -> str:
            sentence = m.group(0)
            if _CAUSAL_VERB.search(sentence) and _TRIGGER_REF.search(sentence):
                self._flag("causal_claim_removed")
                return " [attribution claim removed; see the attribution line]."
            return sentence

        out = _SENTENCE.sub(causal, out)

        def check(m: re.Match[str]) -> str:
            path, line = m.group(1), m.group(2)
            try:
                rel = validate_repo_path(path)
            except UnsafePath:
                self._flag("unverified_path")
                return "[unverified path]"
            exists = self.ev.source.available and rel in self.ev.source.entries()
            if not exists:
                self._flag("unverified_path")
                return "[unverified path]"
            if line is not None:
                eof = self._lines(rel)
                if eof is None or int(line) > eof or int(line) < 1:
                    self._flag("unverified_line")
                    return rel
            return m.group(0)

        out = _PATH_TOKEN.sub(check, out)
        out = redact(" ".join(out.split()))
        return out[:limit]

    def _flag(self, f: str) -> None:
        if f not in self.flags:
            self.flags.append(f)


def _run_info(ev: Evidence, pr_number: int | None) -> RunInfo:
    j = ev.job
    return RunInfo(
        repo_id=j.repo_id,
        repo=j.repo,
        run_id=j.run_id,
        attempt=j.attempt,
        head_sha=j.head_sha,
        event=j.event,
        pr_number=pr_number,
    )


def _primary_errors(ev: Evidence, flags: list[str]) -> list[PrimaryError]:
    out: list[PrimaryError] = []
    pre = ev.prepass
    for g in pre.primaries if pre else []:
        c = g.primary
        log = pre.logs.get(c.job_id) if pre else None
        start, end = c.span
        end = min(end, start + MAX_EXCERPT_LINES - 1)
        text = log.text(start, end) if log else None
        if text is None and log is not None:  # rule 1: shrink to the first line if the range is not fully retained
            end = start
            text = log.text(start, start)
        if text is None or (log is not None and text != log.text(start, end)):
            flags.append("primary_error_unresolved")
            continue
        excerpt = redact(text)[:2048]
        out.append(
            PrimaryError(
                log_ref=LogRef(job_id=c.job_id, line_start=start, line_end=end),
                excerpt=excerpt,
                fingerprint=g.fingerprint,
                siblings=Siblings(count=len(g.members) - 1, names=[n[:200] for n in g.sibling_names]),
            )
        )
    return out


def _examined(ev: Evidence, draft: ModelDraft | None, text: _Text) -> list[FileExamined]:
    verdicts = {v.path: v.verdict for v in (draft.file_verdicts if draft else [])}
    out = []
    for fe in ev.tools.files_examined():
        verdict = text.clean(verdicts.get(fe["path"], ""), 140) or ""
        out.append(FileExamined(path=fe["path"], start=fe["start"], end=fe["end"], verdict=verdict))
    return out


def _location(ev: Evidence, draft: ModelDraft, examined: list[FileExamined]) -> tuple[Location, str] | str:
    """Rule 2 + FS-DX-4. Returns (location, system-copied snippet) or a failure code."""
    loc = draft.problem_location
    assert loc is not None
    try:
        path = validate_repo_path(loc.path)
    except UnsafePath:
        return "location_invalid_path"
    if loc.line_end < loc.line_start:
        return "location_invalid_range"
    if not any(fe.path == path and fe.start <= loc.line_start and loc.line_end <= fe.end for fe in examined):
        return "location_not_examined"
    r = ev.source.read(path)
    if r.status is not ReadStatus.ok or r.text is None:
        return "location_unreadable"
    lines = r.text.splitlines(keepends=True)
    if loc.line_end > len(lines):
        return "location_beyond_eof"
    snippet = "".join(lines[loc.line_start - 1 : min(loc.line_end, loc.line_start + MAX_SNIPPET_LINES - 1)])
    snippet = redact(snippet)  # P-1: the snippet is persisted (FS-SEC-3: redacted excerpts only)
    return Location(path=path, line_start=loc.line_start, line_end=loc.line_end), snippet


def _fix(ev: Evidence, draft: ModelDraft, loc: Location | None, text: _Text, flags: list[str]) -> Fix | None:
    f = draft.fix
    if f is None:
        return None
    if draft.category not in conf.CODE_CATEGORIES:
        flags.append("fix_removed_non_code_category")
        return None
    if _DANGEROUS.search(f.description) or (f.replacement and _DANGEROUS.search(f.replacement.new_text)):
        flags.append("fix_removed_unsafe_command")
        return None
    desc = text.clean(f.description, 600) or ""
    repl = None
    if f.replacement is not None:
        r = f.replacement
        ok = loc is not None and r.path == loc.path and r.line_start <= r.line_end
        if ok and loc is not None:
            eof = text._lines(loc.path)
            ok = eof is not None and r.line_end <= eof and (r.line_end - r.line_start) < 20 and r.new_text.count("\n") < 20
        if ok:
            repl = Replacement(path=r.path, line_start=r.line_start, line_end=r.line_end, new_text=redact(r.new_text))
        else:
            flags.append("fix_replacement_removed")
    if not desc.strip():
        return None
    return Fix(description=desc, replacement=repl, size=f.size)


def _next_steps(draft: ModelDraft | None, text: _Text, flags: list[str]) -> list[str]:
    out = []
    for s in draft.next_steps if draft else []:
        if _DANGEROUS.search(s):
            flags.append("next_step_removed_unsafe_command")
            continue
        cleaned = text.clean(s, 160)
        if cleaned:
            out.append(cleaned)
    return out[:3]


def finalize(ev: Evidence, inv: InvestigationResult | None, *, pr_number: int | None = None) -> ValidatedDiagnosis:
    flags: list[str] = []
    text = _Text(ev, flags)
    run = _run_info(ev, pr_number)
    failed = ev.prepass.failed if ev.prepass else []
    primaries = _primary_errors(ev, flags) if ev.status == "ok" else []
    draft = inv.draft if inv and inv.outcome == "answered" else None
    examined = _examined(ev, draft, text)
    limits = Limits(
        log_truncated=ev.log_truncated,
        files_skipped=sorted(ev.source.skipped)[:50],
        budget_exhausted=bool(inv and inv.budget_exhausted),
        diff_truncated=ev.trigger.truncated,
    )
    usage = Usage(
        provider=inv.provider if inv else "none",
        model=inv.model if inv else None,
        input_tokens=inv.input_tokens if inv else 0,
        output_tokens=inv.output_tokens if inv else 0,
        tool_calls=min(12, inv.tool_calls) if inv else 0,
        latency_ms=inv.latency_ms if inv else 0,
    )
    if inv and inv.ignored_fields:
        flags.append("model_fields_ignored")

    status = Status.diagnosed
    reason: str | None = None
    location: Location | None = None
    snippet: str | None = None
    if ev.status in ("logs_unavailable", "permission_denied"):
        status, reason = Status(ev.status), ev.status
    elif ev.status == "no_failed_jobs":
        status, reason = Status.inconclusive, "no_failed_jobs"
    elif inv is None or inv.outcome != "answered" or draft is None:
        status, reason = Status.inconclusive, inv.outcome if inv else "not_investigated"
    elif primaries == [] and ev.prepass is not None and ev.prepass.primaries:
        status, reason = Status.inconclusive, "primary_error_unresolved"  # rule 1 → rule 6
    elif draft.category is Category.unknown:
        status, reason = Status.inconclusive, "model_abstained"  # H-3
    if status is Status.diagnosed and draft is not None and draft.problem_location is not None:
        got = _location(ev, draft, examined)
        if isinstance(got, str):
            status, reason = Status.inconclusive, got  # rule 2 → rule 6
            flags.append(got)
        else:
            location, snippet = got
    if status is Status.diagnosed and draft is not None and location is None and draft.category in conf.CODE_CATEGORIES:
        status, reason = Status.inconclusive, "no_location_for_code_category"  # H-3

    category = draft.category if draft is not None and status is Status.diagnosed else Category.unknown
    root_cause = text.clean(draft.root_cause, 300) if draft and status is Status.diagnosed else None
    why = text.clean(draft.why, 800) if draft and status is Status.diagnosed else None
    fix = _fix(ev, draft, location, text, flags) if draft and status is Status.diagnosed else None
    steps = _next_steps(draft, text, flags)

    # Rule 5 / T-306: attribution from pre-pass paths PLUS the validated location. Without a validated
    # diagnosis the implicated set is unknown, so relevance is "unknown" and never a "not implicated" clearance.
    implicated = (set(ev.implicated_paths) | ({location.path} if location else set())) if status is Status.diagnosed else set()
    attribution = to_attribution(ev.trigger, relevance(ev.trigger, implicated))

    confidence = conf.assess(
        diagnosed=status is Status.diagnosed,
        reason=reason,
        category=category,
        location=location,
        pre=ev.prepass,
        diff=ev.trigger,
        flags=[f for f in flags if f != "model_fields_ignored"],
        log_truncated=ev.log_truncated,
        has_error_line=has_error_line(ev),
    )
    if fix is not None and confidence.band.value == "low":
        flags.append("fix_removed_low_confidence")
        fix = None
    if status is not Status.diagnosed:
        fix = None
        steps = steps or list(DEFAULT_NEXT_STEPS.get(reason or "", GENERIC_NEXT_STEPS))
        steps = steps[:3]

    try:
        d = Diagnosis(
            run=run,
            status=status,
            failed=failed,
            primary_errors=primaries[:3],
            category=category,
            root_cause=root_cause,
            why=why,
            problem_location=location,
            problem_snippet=snippet,
            fix=fix,
            next_steps=steps,
            files_examined=examined,
            attribution=attribution,
            confidence=confidence,
            limits=limits,
            usage=usage,
            inconclusive_reason=reason,
            validation_flags=sorted(set(flags))[:40],
        )
    except ValidationError:
        # Defensive: an internal inconsistency must never surface as a confident report.
        d = Diagnosis(
            run=run,
            status=Status.inconclusive if status is Status.diagnosed else status,
            failed=failed,
            primary_errors=primaries[:3],
            next_steps=GENERIC_NEXT_STEPS[:2],
            files_examined=examined,
            attribution=attribution,
            confidence=Confidence(band=Band.low, basis=["not_diagnosed:internal_inconsistency"]),
            limits=limits,
            usage=usage,
            inconclusive_reason="internal_inconsistency",
            validation_flags=sorted(set(flags))[:40],
        )
    return ValidatedDiagnosis(d, _digest(d))
