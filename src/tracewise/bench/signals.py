"""Offline evaluation of the P2 signals against the frozen benchmark (T-903 now; T-901 has no benchmark evidence).

    python -m tracewise.bench signals [--out FILE]

For every benchmark run (case, C1 and C2) the dependency-drift signal (`analysis.drift.assess`) is computed from what the
product would see: the trigger diff between the previous snapshot and the run's snapshot (the same snapshots the
harness commits), and the run's raw job logs. No install output exists in the fixtures, so upstream drift can never
be corroborated here; that is reported, not hidden.

The truth is read, never written: a run is **dependency** when `dependency` is in its accepted category set, **other**
when the set is non-empty without it, and **unlabelled** when the set is empty (unanswerable). Predictions:
`corroborated` (manifest_change or upstream_drift with corroboration), `flagged` (a drift kind without
corroboration), `none`, `unknown`.

B-05 and B-06 were read while T-903 was written: they are reported as **development** runs. The other runs were not
used to develop the signal, but their logs and truths are public in this repository, so they are an unseen-by-design
check, not an independent held-out set. Nothing here changes a truth, a lock or a score of the synthetic benchmark.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from tracewise.analysis.drift import assess
from tracewise.bench.fixture import ORDER, snapshot
from tracewise.bench.harness import raw_log
from tracewise.bench.model import REQUIRED_CASES, CaseSpec, load_case
from tracewise.context.trigger import ChangedFile, TriggerDiff

DEVELOPMENT_CASES = frozenset({"B-05", "B-06"})
_HEAD, _BASE = "1" * 40, "0" * 40


@dataclass(frozen=True)
class RunSignal:
    case: str
    run: str
    split: str  # development | unseen
    label: str  # dependency | other | unlabelled
    prediction: str  # corroborated | flagged | none | unknown | skipped
    kind: str
    statement: str
    skipped_reason: str | None = None


def trigger_diff(spec: CaseSpec, run: str) -> TriggerDiff:
    """The trigger diff of `run` (C1 or C2) against the previous snapshot, with unified-diff patches for text files."""
    before, after = snapshot(spec, ORDER[ORDER.index(run) - 1]), snapshot(spec, run)
    files: list[ChangedFile] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        status = "added" if old is None else "removed" if new is None else "modified"
        try:
            a = (old or b"").decode().splitlines(True)
            b = (new or b"").decode().splitlines(True)
            patch: str | None = "".join(difflib.unified_diff(a, b, n=3))
        except UnicodeDecodeError:
            patch = None
        files.append(ChangedFile(path, status, 0, 0, None, patch))
    return TriggerDiff(_HEAD, _BASE, tuple(files))


def _label(categories: list[Any]) -> str:
    values = {str(getattr(c, "value", c)) for c in categories}
    return "unlabelled" if not values else "dependency" if "dependency" in values else "other"


def evaluate() -> list[RunSignal]:
    out: list[RunSignal] = []
    for case_id in sorted(REQUIRED_CASES):
        spec, truth, _ = load_case(case_id)
        split = "development" if case_id in DEVELOPMENT_CASES else "unseen"
        for run, rt in sorted(truth.runs.items()):
            label = _label(list(rt.category))
            if spec.synthetic_log:
                out.append(RunSignal(case_id, run, split, label, "skipped", "", "", "log generated at run time"))
                continue
            try:
                lines = [ln for job in spec.jobs for ln in raw_log(spec, job, run).splitlines()]
            except FileNotFoundError:
                out.append(RunSignal(case_id, run, split, label, "skipped", "", "", "no recorded log for this run"))
                continue
            sig = assess(trigger_diff(spec, run), lines)
            if sig.kind == "unknown":
                pred = "unknown"
            elif sig.kind == "none":
                pred = "none"
            else:
                pred = "corroborated" if sig.corroborated else "flagged"
            out.append(RunSignal(case_id, run, split, label, pred, sig.kind, sig.statement))
    return out


def summarise(rows: list[RunSignal], split: str) -> dict[str, Any]:
    """Confusion counts for one split. Positive = `corroborated`; `flagged` is reported separately (it is never a
    claim), and unlabelled or skipped runs are excluded from the rates."""
    scored = [r for r in rows if r.split == split and r.label != "unlabelled" and r.prediction != "skipped"]
    c = Counter((r.label, r.prediction) for r in scored)
    tp, fn_flag = c[("dependency", "corroborated")], c[("dependency", "flagged")]
    fp, fp_flag = c[("other", "corroborated")], c[("other", "flagged")]
    fn = sum(v for (lab, pred), v in c.items() if lab == "dependency" and pred in ("none", "unknown"))
    tn = sum(v for (lab, pred), v in c.items() if lab == "other" and pred == "none")
    return {
        "runs_scored": len(scored),
        "dependency_runs": sum(r.label == "dependency" for r in scored),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "flagged_uncorroborated_on_dependency": fn_flag,
        "flagged_uncorroborated_on_other": fp_flag,
        "inconclusive": sum(r.prediction == "unknown" for r in scored),
        "excluded_unlabelled": sum(r.split == split and r.label == "unlabelled" for r in rows),
        "skipped": sum(r.split == split and r.prediction == "skipped" for r in rows),
    }


def report() -> dict[str, Any]:
    rows = evaluate()
    return {
        "signal": "dependency drift (T-903; analysis/drift.py); not surfaced in reports (ADR-13)",
        "separate_from_benchmark_scores": True,
        "development": summarise(rows, "development"),
        "unseen": summarise(rows, "unseen"),
        "lane_history": "not evaluable on this benchmark: no case has a run history (see META P-01/P-02, not held out)",
        "runs": [asdict(r) for r in rows],
    }
