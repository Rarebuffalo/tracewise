"""Deterministic scripted provider for offline tests (T-401). No network, no randomness.

Each script entry is a `StepResponse`, an exception instance to raise, or a callable that builds a
response from the request (to react to tool results). Every request is recorded for inspection.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from tracewise.investigate.provider import ProviderError, StepRequest, StepResponse

ScriptItem = StepResponse | BaseException | Callable[[StepRequest], StepResponse]


class ScriptedProvider:
    name: Literal["fake"] = "fake"

    def __init__(self, script: Sequence[ScriptItem], model: str = "fake-scripted-1") -> None:
        self.model = model
        self._script = list(script)
        self.requests: list[StepRequest] = []

    def step(self, request: StepRequest) -> StepResponse:
        self.requests.append(request)
        if not self._script:
            raise ProviderError("fake provider script exhausted")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(request)
        return item
