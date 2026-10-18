"""Benchmark harness (T-601): runs the REAL analysis path on local fixtures, offline.

Per suite: build every case's repository (fixed SHAs), start one local git smart-HTTP server, generate a
throwaway App key and token. Per run (case, commit, repetition): an offline replay of the GitHub API
plus the real `GitFetcher` → `collect_evidence` → `diagnose` (injected provider) → `render`. Track A cases
run the real pre-pass only. Each run is isolated: an exception becomes an `error` record (type name only)
and the suite continues. P2 cases are recorded as `not_applicable` with their reason, never skipped
silently. Output contains no environment, credentials or raw secrets (planted test secrets are
generated at run time and only their absence is recorded).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import secrets
import shutil
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa

from tracewise.analysis.collect import collect_evidence
from tracewise.analysis.diagnose import diagnose
from tracewise.bench.envelope import envelope_lines, job_document
from tracewise.bench.fixture import BuiltRepo, build_repo, diff_files
from tracewise.bench.gitserve import LocalGitServer
from tracewise.bench.model import CASES_DIR, REQUIRED_CASES, CaseSpec, JobSpec, Reference, Truth, case_dir, load_case
from tracewise.bench.providers import ProviderFactory
from tracewise.bench.replay import replay_transport
from tracewise.context.gitfetch import GitFetcher
from tracewise.contracts import AnalysisJob
from tracewise.github.auth import AppCredentials, TokenProvider
from tracewise.github.client import GitHubHTTP, Limits, RepoClient
from tracewise.investigate.provider import Provider, StepRequest, StepResponse
from tracewise.prepass.envelope import JobInfo
from tracewise.prepass.primary import run_prepass
from tracewise.report.render import render

BENCHMARK_VERSION = "2.0"  # BENCHMARK.md version
LOCK_FILE = CASES_DIR / "TRUTH.lock"
INSTALLATION_ID = 1


# ---------------------------------------------------------------- truth lock (BENCHMARK §4 protocol)


def truth_digests() -> dict[str, str]:
    return {
        d.name: hashlib.sha256((d / "truth.yaml").read_bytes()).hexdigest()
        for d in sorted(CASES_DIR.iterdir())
        if (d / "truth.yaml").is_file()
    }


def write_lock() -> None:
    LOCK_FILE.write_text("".join(f"{h}  {c}/truth.yaml\n" for c, h in truth_digests().items()))


def read_lock() -> dict[str, str]:
    out = {}
    for line in LOCK_FILE.read_text().splitlines():
        h, _, path = line.partition("  ")
        out[path.split("/")[0]] = h
    return out


def lock_digest() -> str:
    return hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest()


def verify_lock() -> list[str]:
    if not LOCK_FILE.exists():
        return ["TRUTH.lock missing"]
    locked, now = read_lock(), truth_digests()
    return [f"{c}: truth.yaml changed since it was locked" for c in sorted(set(locked) | set(now)) if locked.get(c) != now.get(c)]


# ---------------------------------------------------------------- planted secrets (E-05) and logs

_PLANTED = {
    "{{SECRET:aws}}": "AKIA" + "BENCHPLANTED0001",
    "{{SECRET:ghp}}": "ghp_" + "BenchPlantedToken0000000000000000001",
    "{{SECRET:jwt}}": "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiJiZW5jaC1wbGFudGVkIn0" + ".c2lnbmF0dXJlLWJlbmNoLXBsYW50ZWQ",
    "{{SECRET:pg}}": "postgresql://bench:" + "PlantedPassw0rd" + "@db.internal:5432/app",
}
_SECRET_VALUES = [
    "BENCHPLANTED0001",
    "BenchPlantedToken0000000000000000001",
    "c2lnbmF0dXJlLWJlbmNoLXBsYW50ZWQ",
    "PlantedPassw0rd",
]


def raw_log(spec: CaseSpec, job: JobSpec, commit: str) -> str:
    path = case_dir(spec.id) / (job.handwritten or f"logs/{commit}/{job.id}.log")
    text = path.read_text()
    for k, v in _PLANTED.items():
        text = text.replace(k, v)
    return text


def enveloped(spec: CaseSpec, job: JobSpec, commit: str) -> str:
    return "\n".join(
        envelope_lines(
            job.command,
            raw_log(spec, job, commit),
            failed=job.conclusion == "failure",
            timed_out=job.timed_out,
            exit_code=job.exit_code,
        )
    )


def a05_lines() -> Iterator[str]:
    """A-05: 200 MB log with the only error at line 3,000,000 (generated; too large to commit)."""
    filler = "2026-10-17T10:00:05.0000000Z ok " + "x" * 36
    n = 200 * 1024 * 1024 // (len(filler) + 1)
    for i in range(1, n + 1):
        yield "2026-10-17T10:00:05.0000000Z E   AssertionError: needle at line 3000000" if i == 3_000_000 else filler


# ---------------------------------------------------------------- suite context


@dataclass
class SuiteContext:
    root: Path
    server: LocalGitServer
    creds: AppCredentials
    repos: dict[str, BuiltRepo]


@contextlib.contextmanager
def suite(case_ids: list[str]) -> Iterator[SuiteContext]:
    root = Path(tempfile.mkdtemp(prefix="twbench-"))
    root.chmod(0o700)
    server = LocalGitServer(root, secrets.token_hex(20)).start()
    try:
        repos = {}
        for cid in case_ids:
            spec, _, _ = load_case(cid)
            if spec.track != "A" and spec.phase == "mvp":
                repos[cid] = build_repo(spec, root)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # throwaway, in memory only
        yield SuiteContext(root, server, AppCredentials(1, key), repos)
    finally:
        server.stop()
        shutil.rmtree(root, ignore_errors=True)


class _Recording:
    """Wraps a provider to record what it was shown (for the E-05 secret check). Not persisted."""

    def __init__(self, inner: Provider) -> None:
        self.inner, self.seen = inner, []  # type: ignore[var-annotated]

    @property
    def name(self) -> Any:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def step(self, request: StepRequest) -> StepResponse:
        self.seen.extend(m.content for m in request.messages)
        return self.inner.step(request)


def _prepass_facts(pre: Any) -> dict[str, Any]:
    if pre is None:
        return {}
    g0 = pre.primaries[0] if pre.primaries else None
    return {
        "failed_step": pre.failed[0].step if pre.failed else None,
        "command": pre.failed[0].command if pre.failed else None,
        "primaries": len(pre.primaries),
        "cascades": len(pre.cascades),
        "log_truncated": pre.log_truncated,
        "first_error": pre.excerpt(g0.primary) if g0 else None,
        "siblings": len(g0.members) - 1 if g0 else None,
    }


def run_one(
    ctx: SuiteContext,
    spec: CaseSpec,
    ref: Reference | None,
    commit: str,
    factory: ProviderFactory,
    provider_name: str,
    repetition: int,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "case": spec.id,
        "case_version": spec.version,
        "track": spec.track,
        "commit": commit,
        "repetition": repetition,
        "provider": provider_name,
        "source_type": spec.source_type,
        "phase": spec.phase,
        "status": "completed",
        "error_type": None,
    }
    t0 = time.perf_counter()
    try:
        if spec.phase == "p2":
            rec.update(status="not_applicable", reason=spec.p2_reason)
            return rec
        if spec.track == "A":
            rec["prepass"] = _run_track_a(spec, commit)
            return rec
        _run_analysis(ctx, spec, ref, commit, factory, rec)
    except Exception as e:  # one failing run must not stop the suite; recorded (type only), never hidden
        rec.update(status="error", error_type=type(e).__name__)
    finally:
        rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return rec


def _run_track_a(spec: CaseSpec, commit: str) -> dict[str, Any]:
    job = spec.jobs[0]
    info = JobInfo.model_validate(job_document(job.id, job.name, job.step, conclusion=job.conclusion))
    lines: Any = a05_lines() if spec.synthetic_log == "a05_200mb" else enveloped(spec, job, commit).splitlines()
    return _prepass_facts(run_prepass([(info, lines)]))


def _run_analysis(
    ctx: SuiteContext, spec: CaseSpec, ref: Reference | None, commit: str, factory: ProviderFactory, rec: dict[str, Any]
) -> None:
    built = ctx.repos[spec.id]
    head = built.shas[commit]
    parent = built.shas["C0" if commit == "C1" else "C1"]
    run_id = int(hashlib.sha256(f"{spec.id}:{commit}".encode()).hexdigest()[:8], 16)
    repo_id = int(hashlib.sha256(spec.id.encode()).hexdigest()[:6], 16)
    jobs = [job_document(j.id, j.name, j.step, conclusion=j.conclusion) for j in spec.jobs]
    logs = {j.id: enveloped(spec, j, commit) for j in spec.jobs if j.conclusion == "failure"}
    transport = replay_transport(
        repo=spec.repo,
        token=ctx.server.token,
        run_id=run_id,
        jobs=jobs,
        logs=logs,
        commits={head: [parent], parent: [built.shas["C0"]] if commit == "C2" else []},
        compares={f"{parent}...{head}": diff_files(built, parent, head)},
    )
    http = GitHubHTTP(httpx.Client(transport=transport), limits=Limits(), sleep=lambda s: None)
    tokens = TokenProvider(ctx.creds, http)
    rc = RepoClient(http, tokens, installation_id=INSTALLATION_ID, repo_id=repo_id, full_name=spec.repo, scope="analysis")
    job = AnalysisJob(
        installation_id=INSTALLATION_ID,
        repo_id=repo_id,
        repo=spec.repo,
        run_id=run_id,
        attempt=1,
        workflow_id=1,
        head_sha=head,
        head_branch="main",
        event=spec.event,
        conclusion="failure",
        delivery_id=f"bench-{spec.id}-{commit}",
    )
    fetcher = GitFetcher(workspace_root=ctx.root / "ws", base_url=ctx.server.base_url, allow_insecure_loopback=True)
    if spec.provider_override is not None:  # E-06: the hostile provider IS the case; recorded, never hidden
        from tracewise.bench.providers import make

        factory = make(spec.provider_override)
        rec["provider_override"] = spec.provider_override
    provider = _Recording(factory(spec, commit, ref))
    with collect_evidence(job, rc, fetcher=fetcher) as ev:
        vd = diagnose(ev, provider, pr_number=None)
        report = render(vd)
        tool_text = "\n".join(c.result.content for c in ev.tools.log)
        rec["prepass"] = _prepass_facts(ev.prepass)
        rec["source_kind"] = ev.source.kind
    d = vd.diagnosis
    rec.update(head_sha=head, model=provider.model, diagnosis=d.model_dump(mode="json"), report=report)
    blob = json.dumps(rec["diagnosis"]) + report
    rec["checks"] = {
        "secret_in_output": any(s in blob for s in _SECRET_VALUES),
        "secret_seen_by_provider": any(s in m for s in _SECRET_VALUES for m in provider.seen),
        "symlink_content_in_tool_results": "root:x:0:0:" in tool_text,
    }


def run_suite(
    provider_name: str,
    factory: ProviderFactory,
    *,
    provider_kind: str = "scripted",
    case_ids: list[str] | None = None,
    repetitions: int = 3,
    include_slow: bool = False,
    label: str = "",
) -> dict[str, Any]:
    """`provider_kind` is "scripted" (protocol validation) or "model" (a real provider, T-605)."""
    if provider_kind not in ("scripted", "model"):
        raise ValueError("provider_kind must be 'scripted' or 'model'")
    problems = verify_lock()
    if problems:
        raise RuntimeError("refusing to run: " + "; ".join(problems))
    ids = case_ids or list(REQUIRED_CASES)
    loaded: dict[str, tuple[CaseSpec, Truth, Reference | None]] = {}
    records: list[dict[str, Any]] = []
    for cid in ids:
        try:
            loaded[cid] = load_case(cid)
        except Exception as e:  # an invalid case is recorded as error rows, never silently dropped
            for commit in ("C1", "C2"):
                records.append(
                    {
                        "case": cid,
                        "commit": commit,
                        "repetition": 1,
                        "provider": provider_name,
                        "status": "error",
                        "error_type": type(e).__name__,
                        "reason": "case_invalid",
                    }
                )
    with suite(list(loaded)) as ctx:
        for cid, (spec, _truth, ref) in loaded.items():
            if spec.synthetic_log == "a05_200mb" and not include_slow:
                for commit in spec.runs:
                    records.append(
                        {
                            "case": cid,
                            "case_version": spec.version,
                            "track": spec.track,
                            "commit": commit,
                            "repetition": 0,
                            "provider": provider_name,
                            "source_type": spec.source_type,
                            "phase": spec.phase,
                            "status": "not_executed",
                            "reason": "slow case excluded (--include-slow)",
                        }
                    )
                continue
            reps = 1 if spec.track == "A" else repetitions
            for commit in spec.runs:
                for rep in range(1, reps + 1):
                    records.append(run_one(ctx, spec, ref, commit, factory, provider_name, rep))
    ident = {
        "benchmark": BENCHMARK_VERSION,
        "truth_lock": lock_digest(),
        "provider": provider_name,
        "cases": ids,
        "repetitions": repetitions,
        "include_slow": include_slow,
        "label": label,
    }
    return {
        "run_id": hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:16],
        "benchmark_version": BENCHMARK_VERSION,
        "truth_lock": lock_digest(),
        "data_kind": "synthetic",
        "provider": {"name": provider_name, "kind": provider_kind},
        "repetitions": repetitions,
        "include_slow": include_slow,
        "required_cases": ids,
        "records": records,
    }
