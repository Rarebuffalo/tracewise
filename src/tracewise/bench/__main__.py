"""CLI: python -m tracewise.bench {verify|generate|run|score|meta|signals}. Offline; no credentials; no network,
except `run --kind model` (below), which is owner-run only.

  verify                         integrity of all cases + truth lock
  generate [--check] [CASE...]   (re)generate logs from local tool runs, or check they reproduce
  run --provider NAME [--case ID ...] [--reps 3] [--include-slow] --out DIR
                                 writes DIR/results.json, DIR/scores.json, DIR/report.md
  run --kind model --model ID --key-file PATH --authorization-ref REF --max-requests N [--case ID ...] --out DIR
                                 the product's OpenAI adapter against the real endpoint (bench/model_provider.py).
                                 Refused under a test runner or CI, without a written authorisation reference, or
                                 with a key file that is a symlink, group/world-readable or inside the repository.
                                 Retries 0; at most N requests in total. Owner-run only (T-605 approval).
  score RESULTS.json --out DIR   re-score saved results
  meta --recorded DIR [--out F]  META cases P-01..P-03 from anonymous metadata recorded earlier, read in place from
                                 DIR (bench/meta.py RECORDED_INDEX). Separate from the synthetic benchmark; no network
  signals [--out FILE]           P2 signal evaluation (dependency drift) over the frozen cases; truth is read only
Scripted providers: oracle, wrong_cause, wrong_location, fabricated, abstain, timeout, malformed, adversarial.
Product provider selection is unaffected: `LLM_PROVIDER=openai` is still refused (investigate/providers.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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


def _outputs(results: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The exact text of every artifact, built before anything is written (the model mode checks these bytes)."""
    scores = score_results(results)
    texts = {
        "results.json": json.dumps(results, indent=1, sort_keys=True),
        "scores.json": json.dumps(scores, indent=1, sort_keys=True),
        "report.md": render_report(scores),
    }
    return scores, texts


def _run_model(a: argparse.Namespace, env: Mapping[str, str], inner: Any) -> int:
    """`run --kind model`: every refusal happens before the key is read; nothing is written on a refusal.

    The leak check runs on the exact bytes that would be written, before anything is written. An unexpected error
    ends with a fixed, content-free message and exit 3 (no traceback, nothing written): a traceback is never checked
    by the canary, so none is printed here."""
    from tracewise.bench.model_provider import build_model_run
    from tracewise.investigate.model_access import AccessRefused

    try:
        run = build_model_run(
            model=a.model,
            key_file=a.key_file,
            authorization_ref=a.authorization_ref,
            max_requests=a.max_requests,
            env=env,
            inner=inner,
        )
    except AccessRefused as e:
        print(f"refused: {e}", file=sys.stderr)  # fixed text; never a key or a response
        return 2
    try:
        try:
            results: dict[str, Any] = run_suite(
                f"model:{run.model}",
                run.factory(),
                provider_kind="model",
                case_ids=a.cases,
                repetitions=a.reps,
                include_slow=a.include_slow,
                budget=run,  # stops the evaluation at the cap; cut-off and unstarted runs are `interrupted`
            )
        finally:
            run.close()
        results["provider"] = {**results["provider"], **run.summary()}
        scores, texts = _outputs(results)
    except Exception as e:  # contained: the type name only, never a message, traceback or partial output
        print(f"error: the evaluation stopped unexpectedly ({type(e).__name__}); nothing written", file=sys.stderr)
        return 3
    if run.leak_check.found_in(*texts.values()):
        print("refused: the output would contain the key; nothing written", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():  # exactly the checked bytes
        (a.out / name).write_text(text)
    print(texts["report.md"])
    return 0 if scores["summary"]["complete"] and results.get("interrupted") is None else 1


def main(argv: list[str] | None = None, *, env: Mapping[str, str] | None = None, inner: Any = None) -> int:
    """`env` and `inner` are test seams for `run --kind model`: the automation refusal reads `env` (the process
    environment by default) and `inner` (an httpx transport) replaces the network transport with a mock."""
    ap = argparse.ArgumentParser(prog="python -m tracewise.bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    g = sub.add_parser("generate")
    g.add_argument("--check", action="store_true")
    g.add_argument("cases", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("--kind", choices=("scripted", "model"), default="scripted")
    r.add_argument("--provider", choices=SCRIPTED, help="scripted kind only")
    r.add_argument("--model", help="model kind only: explicit model id; no default, no fallback")
    r.add_argument("--key-file", help="model kind only: owner-only key file outside the repository")
    r.add_argument("--authorization-ref", help="model kind only: the owner's written authorisation reference")
    r.add_argument("--max-requests", type=int, help="model kind only: hard cap on requests for the whole run")
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
        model_opts = (a.model, a.key_file, a.authorization_ref, a.max_requests)
        if a.kind == "scripted" and (a.provider is None or any(o is not None for o in model_opts)):
            ap.error("--kind scripted needs --provider and takes no model options")
        if a.kind == "model" and a.provider is not None:
            ap.error("--kind model takes no --provider")
        problems = check_all()
        if problems:
            print("refusing to run; integrity problems:\n" + "\n".join(problems), file=sys.stderr)
            return 2
        if a.kind == "model":
            return _run_model(a, dict(os.environ) if env is None else env, inner)
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


def configure_logging() -> None:
    """For the `python -m tracewise.bench` entry point only: JSON to stderr at WARNING through the shared secret
    filter (the model adapter registers its key with it), so a log line can never carry the key. Not called by
    `main()`, which tests and other callers use with their own handlers."""
    import logging

    from tracewise.logging import configure

    configure(level=logging.WARNING)


if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
