"""CLI: python -m tracewise.bench {verify|generate|run|score|meta|signals}. Offline; no credentials; no network.

  verify                         integrity of all cases + truth lock
  generate [--check] [CASE...]   (re)generate logs from local tool runs, or check they reproduce
  run --provider NAME [--case ID ...] [--reps 3] [--include-slow] --out DIR
                                 writes DIR/results.json, DIR/scores.json, DIR/report.md
  score RESULTS.json --out DIR   re-score saved results
  meta --recorded DIR [--out F]  META cases P-01..P-03 from anonymous metadata recorded earlier, read in place from
                                 DIR (bench/meta.py RECORDED_INDEX). Separate from the synthetic benchmark; no network
  signals [--out FILE]           P2 signal evaluation (dependency drift) over the frozen cases; truth is read only
Scripted providers only in this build (oracle, wrong_cause, wrong_location, fabricated, abstain, timeout,
malformed, adversarial); a real model is wired in T-605 with --kind model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tracewise.bench.generate import generate
from tracewise.bench.harness import run_suite
from tracewise.bench.integrity import check_all
from tracewise.bench.model import REQUIRED_CASES
from tracewise.bench.providers import SCRIPTED, make
from tracewise.bench.report import render_report
from tracewise.bench.score import score_results


def _write(out: Path, results: dict[str, object]) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1, sort_keys=True))  # saved before scoring
    scores = score_results(results)
    (out / "scores.json").write_text(json.dumps(scores, indent=1, sort_keys=True))
    (out / "report.md").write_text(render_report(scores))
    return scores


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    g = sub.add_parser("generate")
    g.add_argument("--check", action="store_true")
    g.add_argument("cases", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("--provider", required=True, choices=SCRIPTED)
    r.add_argument("--case", action="append", dest="cases")
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--include-slow", action="store_true")
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("results", type=Path)
    s.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("meta")
    m.add_argument("--recorded", type=Path, required=True)
    m.add_argument("--out", type=Path)
    sg = sub.add_parser("signals")
    sg.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "signals":
        from tracewise.bench import signals

        doc = signals.report()
        text = json.dumps(doc, indent=1, sort_keys=True)
        if a.out:
            a.out.write_text(text)
        print(json.dumps({"development": doc["development"], "unseen": doc["unseen"]}, sort_keys=True))
        return 0
    if a.cmd == "meta":
        from tracewise.bench import meta

        doc = meta.report(meta.run(meta.RecordedSource(a.recorded)))
        text = json.dumps(doc, indent=1, sort_keys=True)
        if a.out:
            a.out.write_text(text)
        print(text)
        return 0 if doc["summary"]["error"] == 0 else 1
    if a.cmd == "verify":
        problems = check_all()
        print("\n".join(problems) or f"OK: {len(REQUIRED_CASES)} cases, truth lock matches")
        return 1 if problems else 0
    if a.cmd == "generate":
        diffs = [d for c in (a.cases or REQUIRED_CASES) for d in generate(c, check=a.check)]
        print("\n".join(diffs) or ("logs reproduce exactly" if a.check else "logs written"))
        return 1 if diffs else 0
    if a.cmd == "run":
        problems = check_all()
        if problems:
            print("refusing to run; integrity problems:\n" + "\n".join(problems), file=sys.stderr)
            return 2
        results = run_suite(
            f"scripted:{a.provider}",
            make(a.provider),
            provider_kind="scripted",
            case_ids=a.cases,
            repetitions=a.reps,
            include_slow=a.include_slow,
        )
        scores = _write(a.out, results)
        print((a.out / "report.md").read_text())
        return 0 if scores["summary"]["complete"] else 1  # type: ignore[index]
    results = json.loads(a.results.read_text())
    _write(a.out, results)
    print((a.out / "report.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
