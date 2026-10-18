"""Ground-truth and fixture integrity checks (T-602). Run before any benchmark run and in the test suite.

Every check is independent of any provider or diagnosis output: it only compares truth.yaml with the
fixture it describes.
"""

from __future__ import annotations

from tracewise.bench.fixture import snapshot
from tracewise.bench.harness import raw_log, verify_lock
from tracewise.bench.model import CASES_DIR, REQUIRED_CASES, case_dir, load_case
from tracewise.prepass.sanitize import clean


def check_case(case_id: str) -> list[str]:
    problems: list[str] = []

    def bad(msg: str) -> None:
        problems.append(f"{case_id}: {msg}")

    d = case_dir(case_id)
    for f in ("case.yaml", "truth.yaml"):
        if not (d / f).is_file():
            bad(f"{f} missing")
    if problems:
        return problems
    try:
        spec, truth, ref = load_case(case_id)
    except Exception as e:
        return [f"{case_id}: schema invalid ({type(e).__name__})"]
    if spec.id != case_id or truth.case != case_id:
        bad("id does not match its directory")
    if truth.version != spec.version or truth.source_type != spec.source_type or truth.phase != spec.phase:
        bad("truth.yaml version/source_type/phase differ from case.yaml")
    if set(truth.runs) != set(spec.runs):
        bad(f"truth runs {sorted(truth.runs)} != case runs {sorted(spec.runs)}")
    if spec.phase == "p2":
        if not spec.p2_reason:
            bad("P2 case without p2_reason")
        return problems
    if spec.track != "A" and ref is None:
        bad("reference.yaml missing (needed for protocol validation)")
    for rel in [*(j.handwritten for j in spec.jobs if j.handwritten), *(p for j in spec.jobs for p in j.pythonpath)]:
        target = (d / rel).resolve()
        if not str(target).startswith(str(d.resolve()) + "/") or not target.exists():
            bad(f"{rel} is missing or outside the case directory (external state)")
    for commit in spec.runs:
        rt = truth.runs[commit]
        files = snapshot(spec, commit) if spec.track != "A" else {}
        if spec.synthetic_log is None:
            for j in spec.jobs:
                if j.conclusion != "failure":
                    continue
                if not j.handwritten and not (d / "logs" / commit / f"{j.id}.log").is_file():
                    bad(f"log for job {j.id} at {commit} missing")
        if rt.answerable is True and not rt.category and spec.track == "B":
            bad(f"{commit}: answerable run without an accepted category")
        for loc in rt.location:
            data = files.get(loc.path)
            if data is None:
                bad(f"{commit}: expected location {loc.path} does not exist at that commit")
            elif loc.line > len(data.decode(errors="replace").splitlines()):
                bad(f"{commit}: expected line {loc.path}:{loc.line} is beyond EOF")
        if rt.location_required and not rt.location:
            bad(f"{commit}: location_required without locations")
        for ev in rt.evidence:
            if ev.log is not None:
                job = next((j for j in spec.jobs if j.id == ev.log), None)
                if job is None:
                    bad(f"{commit}: evidence names unknown job {ev.log}")
                    continue
                text = "\n".join(clean(x) for x in raw_log(spec, job, commit).splitlines())
                if ev.contains not in text:
                    bad(f"{commit}: evidence {ev.contains!r} not in the log of job {ev.log}")
            if ev.file is not None:
                data = files.get(ev.file)
                lines = data.decode(errors="replace").splitlines() if data is not None else []
                hay = lines[ev.line - 1] if ev.line and ev.line <= len(lines) else "\n".join(lines) if not ev.line else ""
                if data is None or ev.contains not in hay:
                    bad(f"{commit}: evidence {ev.contains!r} not found in {ev.file}" + (f":{ev.line}" if ev.line else ""))
    return problems


def check_all() -> list[str]:
    problems: list[str] = []
    present = {p.name for p in CASES_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    for cid in REQUIRED_CASES:
        if cid not in present:
            problems.append(f"{cid}: required case missing")
        else:
            problems.extend(check_case(cid))
    for extra in sorted(present - set(REQUIRED_CASES)):
        problems.append(f"{extra}: unexpected case directory (not in REQUIRED_CASES)")
    problems.extend(verify_lock())
    return problems
