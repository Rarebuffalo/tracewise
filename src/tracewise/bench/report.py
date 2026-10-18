"""Human-readable benchmark report (T-603). Deterministic for fixed scores."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

LIMITATIONS = [
    "Synthetic fixtures only: results say nothing about real-world prevalence or real repositories (BENCHMARK §6).",
    "Public-metadata cases (P-01..P-03, Track D META) are T-604 and are reported separately, never merged here.",
    "B-15 and B-16 need P2 features (failure history, outcome tracking); they are listed as not applicable.",
    "Hand-written logs (synthetic-handwritten): jest/vitest/eslint and pip are not installed offline; B-03, B-06, B-08,"
    " B-12 (jest part), B-13, B-14, A-04, A-06 and E-05 use logs modelled on the tools' documented formats.",
    "One problem_location per diagnosis: cases with two independent defects (B-10, B-11) accept either location.",
    "The 'why' text is not graded here; BENCHMARK §4 requires blind human grading (not done).",
    "Track D here covers code-computed touches_implicated only; lane logic (FS-ATR-2) is P2.",
]


def _p(m: dict[str, Any]) -> str:
    return "n/a (0 runs)" if not m["of"] else f"{m['n']}/{m['of']} ({m['rate']:.0%})"


def render_report(scores: dict[str, Any]) -> str:
    s = scores["summary"]
    prov = scores["provider"]
    scripted = prov["kind"] == "scripted"
    out = [f"# Tracewise synthetic benchmark: run `{scores['run_id']}`", ""]
    out.append(f"- Benchmark version {scores['benchmark_version']}; truth lock `{scores['truth_lock'][:16]}`")
    out.append(f"- Provider: `{prov['name']}` ({prov['kind']}); data: **{scores['data_kind']}**")
    if scripted:
        out.append("")
        out.append(
            "> **Protocol validation, not model accuracy.** A scripted provider replays fixed answers. These numbers "
            "show that the harness, pipeline and scorer behave as designed; they are not evidence of diagnostic quality "
            "and must not be quoted as such. Real-model results require T-605."
        )
    c = s["counts"]
    runs_row = " | ".join(
        str(c[k]) for k in ("required_runs", "executed", "errored", "missing", "not_executed", "not_applicable")
    )
    outcome_keys = ("correct", "partial", "justified_abstention", "unjustified_abstention", "wrong", "overconfident")
    out += [
        "",
        "## Runs",
        "",
        "| required | executed | errored | missing | not executed | not applicable (P2) | complete |",
        "|---|---|---|---|---|---|---|",
        f"| {runs_row} | {'yes' if s['complete'] else '**no**'} |",
        "",
        "| " + " | ".join(k.replace("_", " ") for k in outcome_keys) + " |",
        "|---|---|---|---|---|---|",
        "| " + " | ".join(str(c[k]) for k in outcome_keys) + " |",
    ]
    b = s["track_b"]
    out += [
        "",
        "## Metrics (denominators shown)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Track B points | {b['points']} of {b['max_points']} |",
        f"| Category accuracy (answerable runs) | {_p(b['category_accuracy'])} |",
        f"| Location accuracy (runs requiring a location) | {_p(b['location_accuracy'])} |",
        f"| Confident-wrong rate (diagnosed runs) | {_p(b['confident_wrong_rate'])} |",
        f"| False-blame rate (runs whose push is not implicated) | {_p(b['false_blame_rate'])} |",
        f"| Abstention precision (abstentions that were justified) | {_p(b['abstention_precision'])} |",
        f"| Abstention recall (unanswerable runs abstained) | {_p(b['abstention_recall'])} |",
        f"| Track A extraction (cases passing all checks) | {_p(s['track_a'])} |",
        f"| Track C evidence validity (diagnosed runs) | {_p(s['track_c_evidence_validity'])} |",
        f"| Track D attribution (diagnosed runs with an expected value) | {_p(s['track_d_attribution'])}; "
        f"unknown {s['track_d_attribution_unknown']}, wrong {s['track_d_attribution_wrong']} |",
        f"| Track E security properties (runs passing all) | {_p(s['track_e_security'])} |",
        f"| Track R report checks (analysis runs) | {_p(s['track_r_report'])} |",
        f"| Mean tokens per analysis run | {s['tokens_mean']} |",
        f"| Latency p50 / p95 (ms, includes local git fetch) | {s['latency_ms_p50']} / {s['latency_ms_p95']} |",
        f"| Execution failures by reason | {s['reliability'] or 'none'} |",
        f"| Repetitions with differing outcomes | {', '.join(b['inconsistent_repetitions']) or 'none'} |",
    ]
    t = s["mvp_targets"]
    out += [
        "",
        "## MVP targets (" + t["label"] + ")",
        "",
        f"- Category + location ≥80%: {_p(t['category_and_location_ge_80pct'])}",
        f"- Confident-wrong ≤2%: {_p(t['confident_wrong_le_2pct'])}",
        f"- Justified abstention on B-13/B-14: {_p(t['b13_b14_justified_abstention'])}",
    ]
    out += ["", "## Safety failures", ""]
    out += [f"- {x}" for x in s["safety_failures"]] or ["- none"]
    out += [
        "",
        "## Per-case results",
        "",
        "| Case | Run | Expected | Got | Location | Band | Evidence | Attribution | Outcome | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in scores["runs"]:
        grouped[(r["case"], r["commit"])].append(r)
    for (case, commit), rows in sorted(grouped.items()):
        r = rows[0]
        same = len({x["outcome"] for x in rows}) == 1
        notes = []
        if r.get("e"):
            notes.append("violated: " + ", ".join(r["e"]["violated"]) if r["e"]["violated"] else "all properties hold")
        if r.get("a"):
            failed = [k for k, v in r["a"]["checks"].items() if not v]
            notes.append("extraction: " + ("pass" if r["a"]["passed"] else f"FAIL {failed}"))
        if r.get("report_problems"):
            notes.append("report: " + "; ".join(r["report_problems"]))
        if r.get("inconclusive_reason"):
            notes.append(f"reason: {r['inconclusive_reason']}")
        if r.get("detail"):
            notes.append(str(r["detail"]))
        if not same:
            notes.append("outcomes differ across repetitions: " + ", ".join(x["outcome"] for x in rows))
        loc = r.get("location_result") or "—"
        run = commit + (f" ×{len(rows)}" if len(rows) > 1 else "")
        expected = ", ".join(r["expected_categories"]) or "(abstain)"
        evidence = "—" if r.get("evidence_valid") is None else ("valid" if r["evidence_valid"] else "INVALID")
        attribution = {"ok": "ok", "unknown": "unknown", "wrong": "WRONG"}.get(r.get("attribution_result") or "", "—")
        cells = [
            case,
            run,
            expected,
            r.get("category") or "—",
            loc,
            r.get("band") or "—",
            evidence,
            attribution,
            r["outcome"],
            "; ".join(notes),
        ]
        out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in cells) + " |")
    out += ["", "## Limitations", ""] + [f"- {x}" for x in LIMITATIONS]
    return "\n".join(out) + "\n"
