"""The only structure the model may return (T-402). Everything else in Diagnosis v2 is code-built.

Strict: unknown keys are rejected, except a fixed set of fields the model is not allowed to set
(attribution, confidence, files_examined, primary_errors, status, usage, limits, links). Those are
dropped and recorded, never used (SPEC §3.2 rule 5, ADR-18).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tracewise.contracts import Category

MAX_FINAL_CHARS = 16_000
IGNORED_MODEL_FIELDS = frozenset(
    {
        "attribution",
        "confidence",
        "files_examined",
        "primary_errors",
        "status",
        "usage",
        "limits",
        "links",
        "run",
        "schema_version",
        "failed",
        "siblings",
        "snippet",
        "problem_snippet",
    }
)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DraftLocation(_M):
    path: str = Field(min_length=1, max_length=512)
    line_start: int = Field(ge=1, le=10_000_000)
    line_end: int = Field(ge=1, le=10_000_000)


class DraftReplacement(DraftLocation):
    new_text: str = Field(max_length=4000)


class DraftFix(_M):
    description: str = Field(min_length=1, max_length=600)
    replacement: DraftReplacement | None = None
    size: Literal["trivial", "small", "larger", "n/a"] = "n/a"


class DraftVerdict(_M):
    path: str = Field(min_length=1, max_length=512)
    verdict: str = Field(max_length=140)


class ModelDraft(_M):
    category: Category
    root_cause: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=800)
    problem_location: DraftLocation | None = None
    fix: DraftFix | None = None
    next_steps: list[str] = Field(default_factory=list, max_length=3)
    file_verdicts: list[DraftVerdict] = Field(default_factory=list, max_length=30)

    @field_validator("next_steps")
    @classmethod
    def _steps(cls, v: list[str]) -> list[str]:
        if any(len(s) > 160 or not s.strip() for s in v):
            raise ValueError("each next step must be 1-160 characters")
        return v


class DraftError(Exception):
    """The final answer is not a valid draft. `detail` is safe to show the model in one repair turn."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def parse_draft(text: str | None) -> tuple[ModelDraft, list[str]]:
    """Parse the model's final answer. Returns the draft and the names of ignored (forbidden) fields."""
    if not text or not text.strip():
        raise DraftError("empty answer; return one JSON object")
    if len(text) > MAX_FINAL_CHARS:
        raise DraftError("answer too long")
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{") :] if "{" in raw else raw
    try:
        doc = json.loads(raw)
    except ValueError:
        raise DraftError("answer is not valid JSON") from None
    if not isinstance(doc, dict):
        raise DraftError("answer must be a JSON object")
    ignored = sorted(k for k in doc if k in IGNORED_MODEL_FIELDS)
    for k in ignored:
        doc.pop(k)
    try:
        return ModelDraft.model_validate(doc), ignored
    except ValidationError as e:
        fields = sorted({".".join(str(p) for p in err["loc"]) or "(root)" for err in e.errors()})
        raise DraftError("schema violation in: " + ", ".join(fields[:10])) from None
