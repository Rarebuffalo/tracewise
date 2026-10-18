"""Generate benchmark logs from REAL local tool runs (T-601).

For every job with `exec`, the case's commit snapshot is written to a private temp checkout and the
listed tools run there (pytest/mypy via this interpreter, ruff from this environment, tsc from PATH).
Output is normalised so it is reproducible: checkout and environment paths become runner-style paths,
timings and version banners are fixed. `--check` regenerates into memory and reports differences from
the committed logs without writing. Only our own fixture code runs here (never customer code), with
no network access required.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tracewise.bench.fixture import snapshot
from tracewise.bench.model import CaseSpec, JobSpec, case_dir, load_case

RUNNER_PY = "/opt/hostedtoolcache/Python/3.12.7/x64"
SITE = f"{RUNNER_PY}/lib/python3.12/site-packages"
_TIMING = re.compile(r"\bin \d+\.\d+s\b")
_PLATFORM = re.compile(r"^platform \S+ -- Python [^,]+, pytest-[^,]+, pluggy-\S+.*$", re.M)
_MYPY_FOUND = re.compile(r"\(checked \d+ source files?\)")


def _argv(cmd: list[str]) -> list[str]:
    tool, rest = cmd[0], cmd[1:]
    if tool in ("pytest", "mypy"):
        return [sys.executable, "-m", tool, *rest]
    if tool == "ruff":
        return [str(Path(sys.executable).parent / "ruff"), *rest]
    found = shutil.which(tool)
    if found is None:
        raise RuntimeError(f"{tool} is not installed; cannot regenerate this log")
    return [found, *rest]


def _normalise(text: str, checkout: Path, spec: CaseSpec, extra: list[Path]) -> str:
    name = spec.repo.split("/")[1]
    tmp_root = str(checkout.parent)
    for p in sorted(extra, key=lambda x: -len(str(x))):
        text = text.replace(str(p), SITE)
    text = text.replace(str(checkout), f"/home/runner/work/{name}/{name}")
    text = text.replace(tmp_root, "/home/runner")  # the private temp HOME
    for prefix in {sys.base_prefix, sys.prefix, os.path.realpath(sys.base_prefix)}:
        text = text.replace(prefix, RUNNER_PY)
    text = text.replace(str(Path.home()), "/home/runner")
    text = _PLATFORM.sub("platform linux -- Python 3.12.7, pytest-8.3.3, pluggy-1.5.0", text)
    text = _MYPY_FOUND.sub("(checked N source files)", text)
    return _TIMING.sub("in 0.01s", text)


def run_job(spec: CaseSpec, job: JobSpec, commit: str) -> str:
    assert job.exec
    with tempfile.TemporaryDirectory(prefix="twgen-") as d:
        checkout = Path(d) / spec.repo.split("/")[1]
        for rel, data in snapshot(spec, commit).items():
            f = checkout / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        extra = [(case_dir(spec.id) / p).resolve() for p in job.pythonpath]
        env = {
            "PATH": os.pathsep.join([str(Path(sys.executable).parent), "/usr/local/bin", "/usr/bin", "/bin"]),
            "HOME": d,
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_COLOR": "1",
            "PYTHONPATH": os.pathsep.join([*map(str, extra), str(checkout)]),
            **job.env,
        }
        out = []
        for cmd in job.exec:
            p = subprocess.run(_argv(cmd), cwd=checkout, env=env, capture_output=True, text=True, timeout=120, check=False)  # noqa: S603
            out.append(p.stdout + p.stderr)
        return _normalise("".join(out), checkout, spec, extra)


def generate(case_id: str, *, check: bool = False) -> list[str]:
    """Write (or, with check=True, compare) logs/<commit>/<job>.log. Returns the paths that differ."""
    spec, _, _ = load_case(case_id)
    diffs = []
    for commit in spec.runs:
        for job in spec.jobs:
            if not job.exec:
                continue
            path = case_dir(case_id) / "logs" / commit / f"{job.id}.log"
            text = run_job(spec, job, commit)
            if check:
                if not path.exists() or path.read_text() != text:
                    diffs.append(str(path.relative_to(case_dir(case_id).parent)))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
    return diffs
