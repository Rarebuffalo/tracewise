"""Provider selection from settings (T-605 seam). Explicit, never an automatic fallback.

* `openai`: the HTTP adapter (`tracewise.investigate.openai_adapter`), when available in this build.
* `fake`: ONLY with `TW_ENV=test`. A real worker with a fake model would publish meaningless
  "could not complete" notices, so any other environment refuses it at startup.
No other provider exists, and a failure of the configured provider is never retried on a different one.
"""

from __future__ import annotations

from collections.abc import Callable

from tracewise.config import Settings
from tracewise.investigate.provider import Provider


class ProviderConfigError(ValueError):
    """Provider configuration refused; the message names settings, never values."""


def provider_factory(st: Settings) -> Callable[[], Provider]:
    if st.llm_provider == "fake":
        if st.tw_env != "test":
            raise ProviderConfigError("LLM_PROVIDER=fake is only allowed with TW_ENV=test")
        from tracewise.investigate.fake import ScriptedProvider

        return lambda: ScriptedProvider([])  # every call fails → could_not_complete; process smoke tests only
    if st.llm_provider == "openai":
        raise ProviderConfigError(
            "LLM_PROVIDER=openai: no OpenAI wire codec in this build; its API contract is not recorded (docs/MODEL-ADAPTER.md)"
        )
    raise ProviderConfigError("LLM_PROVIDER must be 'openai' or 'fake'")  # pragma: no cover - Settings restricts it
