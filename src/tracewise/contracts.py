"""Data contracts (T-103): webhook event subset, job payload, Diagnosis v2 (SPEC section 3.1).

Length limits here are the schema half of the validator; cross-field rules live in
`tracewise.investigate.validate` (SPEC section 3.2).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]


def _rel_path(p: str) -> str:
    """Repository-relative, no absolute paths, no `..` segments, no NUL/backslash."""
    if not p or p.startswith("/") or "\\" in p or "\x00" in p or ".." in p.split("/"):
        raise ValueError("path must be repository-relative without '..'")
    return p


RelPath = Annotated[str, StringConstraints(min_length=1, max_length=512), AfterValidator(_rel_path)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- webhook (subset)

ANALYSED_CONCLUSIONS = frozenset({"failure", "timed_out"})  # FS-EVT-1; startup_failure gated (G-PLAT-1)


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class RepoRef(_Lenient):
    id: int
    full_name: str
    private: bool = False


class HeadRepoRef(_Lenient):
    id: int
    full_name: str


class WorkflowRun(_Lenient):
    id: int
    run_attempt: int = 1
    workflow_id: int | None = None
    head_sha: Sha
    head_branch: str | None = None
    event: str
    status: str
    conclusion: str | None = None
    name: str | None = None
    repository: RepoRef
    head_repository: HeadRepoRef | None = None


class Installation(_Lenient):
    id: int


class WorkflowRunEvent(_Lenient):
    action: str
    workflow_run: WorkflowRun
    repository: RepoRef
    installation: Installation

    @property
    def dedupe_key(self) -> str:
        """FS-EVT-4: one analysis per (repo, run, attempt)."""
        r = self.workflow_run
        return f"analyze:{self.repository.id}:{r.id}:{r.run_attempt}"

    def should_analyse(self) -> bool:
        return self.action == "completed" and self.workflow_run.conclusion in ANALYSED_CONCLUSIONS

    @property
    def is_fork(self) -> bool:
        head = self.workflow_run.head_repository
        return head is not None and head.id != self.repository.id


class AnalysisJob(_Strict):
    """Queue payload: identifiers only, never content."""

    installation_id: int
    repo_id: int
    repo: str
    run_id: int
    attempt: int = Field(ge=1)
    workflow_id: int | None = None
    head_sha: Sha
    head_branch: str | None = None
    head_repo: str | None = None
    head_repo_id: int | None = None
    event: str
    conclusion: Literal["failure", "timed_out"]
    delivery_id: str

    @classmethod
    def from_event(cls, ev: WorkflowRunEvent, delivery_id: str) -> AnalysisJob:
        run = ev.workflow_run
        if not ev.should_analyse():
            raise ValueError("event is not analysable")
        return cls(
            installation_id=ev.installation.id,
            repo_id=ev.repository.id,
            repo=ev.repository.full_name,
            run_id=run.id,
            attempt=run.run_attempt,
            head_sha=run.head_sha,
            head_branch=run.head_branch,
            workflow_id=run.workflow_id,
            head_repo=run.head_repository.full_name if run.head_repository else None,
            head_repo_id=run.head_repository.id if run.head_repository else None,
            event=run.event,
            conclusion=cast(Literal["failure", "timed_out"], run.conclusion),
            delivery_id=delivery_id,
        )


# ---------------------------------------------------------------- Diagnosis v2


class Status(StrEnum):
    diagnosed = "diagnosed"
    inconclusive = "inconclusive"
    logs_unavailable = "logs_unavailable"
    permission_denied = "permission_denied"


class Category(StrEnum):
    code_regression = "code_regression"
    test_defect = "test_defect"
    dependency = "dependency"
    config_secret = "config_secret"
    infra_runner = "infra_runner"
    flaky_suspect = "flaky_suspect"
    workflow_invalid = "workflow_invalid"
    unknown = "unknown"


CODE_CATEGORIES = frozenset({Category.code_regression, Category.test_defect})


class Band(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class RunInfo(_Strict):
    repo_id: int
    repo: str
    run_id: int
    attempt: int = Field(ge=1)
    head_sha: Sha
    event: str
    pr_number: int | None = None


class FailedStep(_Strict):
    job_id: int
    job: str = Field(max_length=200)
    step: str | None = Field(default=None, max_length=200)
    command: str | None = Field(default=None, max_length=500)


class LogRef(_Strict):
    job_id: int
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> LogRef:
        if self.line_end < self.line_start:
            raise ValueError("line_end < line_start")
        return self


class Siblings(_Strict):
    count: int = Field(0, ge=0)
    names: list[str] = Field(default_factory=list, max_length=20)


class PrimaryError(_Strict):
    log_ref: LogRef
    excerpt: str = Field(max_length=2048)
    fingerprint: Fingerprint
    siblings: Siblings = Siblings()


class Location(_Strict):
    path: RelPath
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> Location:
        if self.line_end < self.line_start:
            raise ValueError("line_end < line_start")
        return self


class Replacement(Location):
    new_text: str

    @model_validator(mode="after")
    def _small(self) -> Replacement:
        if self.line_end - self.line_start + 1 > 20 or self.new_text.count("\n") >= 20:
            raise ValueError("replacement exceeds 20 lines (FS-DX-5)")
        return self


class Fix(_Strict):
    description: str = Field(max_length=600)
    replacement: Replacement | None = None
    size: Literal["trivial", "small", "larger", "n/a"] = "n/a"


class FileExamined(_Strict):
    path: RelPath
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    verdict: str = Field(max_length=140)


class Attribution(_Strict):
    trigger_sha: Sha
    trigger_changed_files: list[str] = Field(default_factory=list)
    touches_implicated: bool | None  # FS-ATR-1: true / false / unknown
    statement: str = Field(max_length=400)
    basis: list[str] = Field(default_factory=list)


class Confidence(_Strict):
    band: Band
    basis: list[str] = Field(min_length=1)  # AT-DX-12: every diagnosis has >=1 basis


class Limits(_Strict):
    log_truncated: bool = False
    files_skipped: list[str] = Field(default_factory=list)
    budget_exhausted: bool = False
    diff_truncated: bool = False


class Usage(_Strict):
    provider: Literal["openai", "fake", "none"] = "none"
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = Field(0, ge=0, le=12)
    latency_ms: int = 0


class Diagnosis(_Strict):
    schema_version: Literal["2"] = "2"
    run: RunInfo
    status: Status
    failed: list[FailedStep] = Field(default_factory=list)
    primary_errors: list[PrimaryError] = Field(default_factory=list, max_length=3)  # FS-DX-2: <=3 independent
    category: Category = Category.unknown
    root_cause: str | None = Field(default=None, max_length=300)
    why: str | None = Field(default=None, max_length=800)
    problem_location: Location | None = None
    problem_snippet: str | None = Field(default=None, max_length=4000)  # FS-DX-4: copied by the system, never the model
    fix: Fix | None = None
    next_steps: list[Annotated[str, StringConstraints(max_length=160)]] = Field(default_factory=list, max_length=3)
    files_examined: list[FileExamined] = Field(default_factory=list)
    attribution: Attribution | None = None
    confidence: Confidence
    limits: Limits = Limits()
    usage: Usage = Usage()
    inconclusive_reason: str | None = Field(default=None, max_length=64, pattern=r"^[a-z_:]+$")  # fixed code, not prose
    validation_flags: list[Annotated[str, StringConstraints(max_length=64, pattern=r"^[a-z_:0-9.]+$")]] = Field(
        default_factory=list, max_length=40
    )

    @model_validator(mode="after")
    def _status_shape(self) -> Diagnosis:
        if self.status is not Status.diagnosed:
            if self.fix is not None:
                raise ValueError("non-diagnosed status carries no fix (FS-DX-8)")
            if self.confidence.band is Band.high:
                raise ValueError("non-diagnosed status cannot be high confidence")
        if self.status is Status.inconclusive and not 1 <= len(self.next_steps) <= 3:
            raise ValueError("inconclusive needs 1-3 next steps (FS-DX-8)")
        if self.fix is not None and self.category not in CODE_CATEGORIES:
            raise ValueError("non-code categories get next_steps, not a code fix (FS-DX-6)")
        if self.fix is not None and self.confidence.band is Band.low:
            raise ValueError("fix is omitted at low confidence (FS-DX-5)")
        return self
