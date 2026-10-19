"""Bounded investigation loop (T-402; FS-DX-3, FS-DX-8, FS-SEC-1, ADR-08).

Budgets are enforced here, not by the model: ≤`max_tool_calls` tool calls (FS-DX-3: 12), ≤`timeout_s`
wall clock (120 s), a token budget, an iteration cap, a per-call argument size cap and a limit on
consecutive unproductive steps. Tool calls are validated (name, argument keys and types) before
dispatch to the read-only `ToolBox`; repeated identical calls are not re-executed but still count.
The final answer gets exactly one repair turn (FS-DX-3), then the outcome is `invalid_output`.
Every non-answer outcome is turned into an inconclusive diagnosis by the caller; nothing is invented.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tracewise.analysis.collect import Evidence
from tracewise.config import Settings
from tracewise.context.tools import TOOL_NAMES, ToolResult
from tracewise.investigate.prompt import TOOL_SPECS, Delimiter, render_bundle, system_prompt
from tracewise.investigate.provider import (
    Message,
    Provider,
    ProviderError,
    ProviderTimeout,
    StepRequest,
    ToolCallRequest,
)
from tracewise.investigate.schema import MAX_FINAL_CHARS, DraftError, ModelDraft, parse_draft
from tracewise.prepass.sanitize import redact

log = logging.getLogger(__name__)

Outcome = Literal[
    "answered",
    "no_error_line",
    "provider_failed",
    "provider_timeout",
    "budget_exhausted",
    "invalid_output",
    "unproductive",
]
# Kinds that are real error lines. Runner exit codes, job timeouts and OOM kills are not (FS-DX-8).
_ERROR_KINDS = frozenset({"compile", "lint", "test", "exception", "missing_module", "install", "generic"})
_NOT_ERROR_CODES = frozenset({"timeout", "oom"})

_ARGS: dict[str, dict[str, type]] = {
    "read_file": {"path": str, "start": int, "end": int},
    "grep": {"pattern": str, "glob": str, "ignore_case": bool},
    "list_dir": {"path": str},
    "get_diff": {},
}
_REQUIRED = {"read_file": {"path"}, "grep": {"pattern"}, "list_dir": set(), "get_diff": set()}


@dataclass(frozen=True)
class InvestigationLimits:
    max_tool_calls: int = 12
    timeout_s: float = 120.0
    max_iterations: int = 16
    max_total_tokens: int = 200_000
    max_args_chars: int = 1024
    max_unproductive_steps: int = 3
    max_output_chars: int = MAX_FINAL_CHARS

    @classmethod
    def from_settings(cls, settings: Settings) -> InvestigationLimits:
        """Configured values; the Settings model already caps them at 12 calls and 120 s (FS-DX-3)."""
        return cls(max_tool_calls=settings.investigation_max_tool_calls, timeout_s=float(settings.investigation_timeout_s))


@dataclass(frozen=True)
class InvestigationResult:
    outcome: Outcome
    draft: ModelDraft | None
    provider: str
    model: str | None
    tool_calls: int = 0
    rejected_calls: int = 0
    duplicate_calls: int = 0
    repaired: bool = False
    ignored_fields: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def budget_exhausted(self) -> bool:
        return self.outcome in ("budget_exhausted", "unproductive")


def provider_view(messages: list[Message]) -> tuple[Message, ...]:
    """The ONLY form in which the conversation crosses the provider boundary (P-2, approved option A).

    Every message text and every string inside replayed tool-call arguments goes through the same redaction as logs
    (`prepass.sanitize.redact`). That covers the evidence bundle, all tool results (`read_file` windows, `grep`
    lines, `list_dir` names, `get_diff` patches), the model's own replayed turns and repair prompts, and anything
    added later. Internal state (duplicate detection, the validator) keeps the original text. Pattern-based: encoded,
    split or unfamiliar secrets can still pass (P-4)."""
    return tuple(
        Message(
            m.role,
            redact(m.content),
            tool_call_id=m.tool_call_id,
            tool_calls=tuple(ToolCallRequest(tc.id, tc.name, _redact_args(tc.arguments)) for tc in m.tool_calls),
        )
        for m in messages
    )


def _redact_args(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, dict):
        return {k: _redact_args(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_redact_args(x) for x in v]
    return v


def has_error_line(ev: Evidence) -> bool:
    pre = ev.prepass
    if pre is None:
        return False
    return any(c.kind in _ERROR_KINDS and c.code not in _NOT_ERROR_CODES for g in pre.primaries for c in g.members)


def validate_call(tc: ToolCallRequest, max_args_chars: int) -> tuple[str, dict[str, Any]] | str:
    """Return (name, args) or a rejection reason. Never raises."""
    if tc.name not in TOOL_NAMES:
        return f"unknown tool {tc.name[:40]!r}"
    args = tc.arguments
    if isinstance(args, str):
        if len(args) > max_args_chars:
            return "arguments too large"
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return "arguments are not valid JSON"
    if not isinstance(args, dict):
        return "arguments must be an object"
    if len(json.dumps(args, default=str)) > max_args_chars:
        return "arguments too large"
    allowed = _ARGS[tc.name]
    extra = set(args) - set(allowed)
    if extra:
        return f"unexpected argument(s): {', '.join(sorted(extra))[:80]}"
    if missing := _REQUIRED[tc.name] - set(args):
        return f"missing argument(s): {', '.join(sorted(missing))}"
    for k, v in args.items():
        want = allowed[k]
        if want is int and (isinstance(v, bool) or not isinstance(v, int)):
            return f"argument {k} must be an integer"
        if want is not int and not isinstance(v, want):
            return f"argument {k} has the wrong type"
    return tc.name, args


def investigate(
    ev: Evidence,
    provider: Provider,
    limits: InvestigationLimits | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
    delimiter: Delimiter | None = None,
) -> InvestigationResult:
    lim = limits or InvestigationLimits()
    if not has_error_line(ev):
        return InvestigationResult("no_error_line", None, provider.name, provider.model)
    d = delimiter or Delimiter.new()
    messages: list[Message] = [
        Message("system", system_prompt(lim.max_tool_calls)),
        Message("user", "Diagnose this CI failure. Evidence follows.\n\n" + render_bundle(ev, d)),
    ]
    start = clock()
    deadline = start + lim.timeout_s
    calls = rejected = duplicates = unproductive = tokens_in = tokens_out = 0
    seen: dict[str, ToolResult] = {}
    repaired = final_only = False

    def result(outcome: Outcome, draft: ModelDraft | None = None, ignored: tuple[str, ...] = ()) -> InvestigationResult:
        log.info("investigation finished", extra={"tw": {"outcome": outcome, "tool_calls": calls, "rejected": rejected}})
        return InvestigationResult(
            outcome,
            draft,
            provider.name,
            provider.model,
            calls,
            rejected,
            duplicates,
            repaired,
            ignored,
            tokens_in,
            tokens_out,
            int((clock() - start) * 1000),
        )

    for _ in range(lim.max_iterations):
        remaining = deadline - clock()
        if remaining <= 0:
            return result("budget_exhausted")
        allow_tools = not final_only and calls < lim.max_tool_calls
        req = StepRequest(
            provider_view(messages), TOOL_SPECS if allow_tools else (), allow_tools, lim.max_output_chars, remaining
        )
        try:
            resp = provider.step(req)
        except ProviderTimeout:
            return result("provider_timeout")
        except ProviderError:
            return result("provider_failed")
        except Exception:
            # Deliberately broad: any adapter defect becomes a provider failure (an inconclusive result),
            # never a crash or a guessed diagnosis. BaseException (cancellation) still propagates.
            log.warning("provider raised an unexpected exception", exc_info=False)
            return result("provider_failed")
        tokens_in += max(0, resp.usage.input_tokens)
        tokens_out += max(0, resp.usage.output_tokens)
        if tokens_in + tokens_out > lim.max_total_tokens or clock() > deadline:
            return result("budget_exhausted")

        if resp.tool_calls:
            if not allow_tools or calls + len(resp.tool_calls) > lim.max_tool_calls:
                return result("budget_exhausted")  # the model tried to exceed its budget (FS-DX-8)
            messages.append(Message("assistant", resp.text or "", tool_calls=resp.tool_calls))
            productive = False
            for tc in resp.tool_calls:
                calls += 1
                checked = validate_call(tc, lim.max_args_chars)
                if isinstance(checked, str):
                    rejected += 1
                    content = f"REJECTED: {checked}"
                else:
                    name, args = checked
                    key = name + json.dumps(args, sort_keys=True)
                    if key in seen:
                        duplicates += 1
                        content = "DUPLICATE: identical call already made; see the earlier result."
                    else:
                        res = ev.tools.call(name, args)
                        seen[key] = res
                        productive = productive or res.ok
                        content = d.wrap(f"tool {name}", res.content)
                messages.append(Message("tool", content, tool_call_id=tc.id[:64]))
            unproductive = 0 if productive else unproductive + 1
            if unproductive >= lim.max_unproductive_steps:
                return result("unproductive")
            continue

        try:
            draft, ignored = parse_draft(resp.text if resp.text is None else resp.text[: lim.max_output_chars + 1])
        except DraftError as e:
            if repaired:
                return result("invalid_output")
            repaired = final_only = True
            messages.append(Message("assistant", (resp.text or "")[:2000]))
            messages.append(
                Message(
                    "user",
                    f"Your answer was rejected ({e.detail}). Reply with ONE corrected JSON "
                    "object only, following the required keys. No tools are available now.",
                )
            )
            continue
        return result("answered", draft, tuple(ignored))
    return result("budget_exhausted")
