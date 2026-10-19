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
    # Opaque, provider-originated items that the provider requires back on the next turn (e.g. OpenAI reasoning
    # items with encrypted content). Never repository content; passed back verbatim, never interpreted.
    replay: tuple[Any, ...] = ()


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
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class StepResponse:
    text: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    usage: StepUsage = field(default_factory=StepUsage)
    replay: tuple[Any, ...] = ()  # see Message.replay


class ProviderError(Exception):
    """The provider failed (transport, refusal, invalid response). Messages must not carry secrets."""


class ProviderTimeout(ProviderError):
    pass


class Provider(Protocol):
    @property
    def name(self) -> Literal["openai", "fake"]: ...

    @property
    def model(self) -> str: ...

    def step(self, request: StepRequest) -> StepResponse: ...
