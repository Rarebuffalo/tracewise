"""Provider boundary (T-401; FS-DX-3, ADR-08).

The investigator talks to a model only through `Provider.step()`. A provider receives the
conversation so far, the fixed tool specs and limits, and returns either tool-call requests or a
final text answer. It never sees credentials, never executes anything and never reaches the
tools itself: the investigator loop validates and dispatches every tool call.

Offline tests use `tracewise.investigate.fake.ScriptedProvider`. A real (OpenAI) adapter is a
later task (T-605 batch); this module has no network or SDK dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    # Provider-originated items that the provider requires back on the next turn (OpenAI reasoning items; the Gemini
    # codec's signed copy of the whole model turn). Passed back verbatim and unredacted, never interpreted, never
    # evidence. Not opaque in every case: a model turn can echo repository text it was shown (already redacted at
    # the provider boundary). The redaction exception is owner decision O-5. In the loop's history it holds sealed
    # `replay.ReplayEnvelope`s; a codec receives the verified raw items. Never part of `repr` (P5).
    replay: tuple[Any, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: Any  # untrusted: validated by the investigator before dispatch


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class StepRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...]
    allow_tools: bool
    max_output_chars: int
    timeout_s: float


@dataclass(frozen=True)
class StepUsage:
    """`input_tokens` and `output_tokens` are totals, defined the same way for every codec (budgets use them). The
    breakdown is a subset of those totals, mapped only from fields the provider sends: cached input inside
    `input_tokens`, reasoning ("thinking") output inside `output_tokens`. `None` means the provider did not report the
    field (unknown), which is never the same as a reported 0. Never invented, never estimated from text."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.cached_input_tokens is not None and not (0 <= self.cached_input_tokens <= max(0, self.input_tokens)):
            raise ValueError("cached input must be part of the input total")
        if self.reasoning_output_tokens is not None and not (0 <= self.reasoning_output_tokens <= max(0, self.output_tokens)):
            raise ValueError("reasoning output must be part of the output total")


@dataclass(frozen=True)
class StepResponse:
    text: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    usage: StepUsage = field(default_factory=StepUsage)
    replay: tuple[Any, ...] = field(default=(), repr=False)  # see Message.replay


class ProviderError(Exception):
    """The provider failed (transport, refusal, invalid response). Messages must not carry secrets."""


class ProviderTimeout(ProviderError):
    pass


class ProviderRefusal(ProviderError):
    """The model refused, or the provider blocked the prompt or the response (design step 4). Never a diagnosis."""


class ProviderTruncated(ProviderError):
    """The response stopped at the output limit: a partial answer is never taken for a complete one."""


class Provider(Protocol):
    @property
    def name(self) -> Literal["openai", "gemini", "fake"]: ...

    @property
    def model(self) -> str: ...

    def step(self, request: StepRequest) -> StepResponse: ...

    # Optional: the assistant turns whose state must come back ("none", "tool_turns", "all_turns"; default
    # "tool_turns"). Declared by the provider's protocol (O-5); the loop applies it without provider branches.
