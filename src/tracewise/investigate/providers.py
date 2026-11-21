"""Provider selection from settings. Explicit, never an automatic fallback.

* `openai`: the OpenAI Responses API (`openai_responses.OpenAIResponsesWire`), with the operator's own key
  (`OPENAI_API_KEY`) and an explicit model (`LLM_MODEL`).
* `gemini`: the Gemini `generateContent` API (`gemini_generate.GeminiGenerateContentWire`), with `GEMINI_API_KEY` and
  `LLM_MODEL`.
* `fake`: ONLY with `TW_ENV=test`. A real worker with a fake model would publish meaningless
  "could not complete" notices, so any other environment refuses it at startup.

Both real codecs follow recorded API contracts (research/*-api-reference-*) and are tested offline against them; they
have not been exercised against the live APIs by this project (docs/MODEL-ADAPTER.md).

One provider is built per worker process, at startup, so a configuration error stops the worker before it claims a
job. A worker runs one job at a time, so the provider (and its request deadline) is never shared by two investigations
at once. A failure of the configured provider is never retried on a different one.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from pydantic import SecretStr

from tracewise.config import LLM_KEY_SETTING, Settings, llm_config_problem
from tracewise.investigate import deadline_http
from tracewise.investigate.gemini_generate import GeminiGenerateContentWire
from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider, WireCodec
from tracewise.investigate.openai_responses import OpenAIResponsesWire
from tracewise.investigate.provider import Provider


class ProviderConfigError(ValueError):
    """Provider configuration refused; the message names settings, never values."""


def provider_factory(st: Settings, *, transport: httpx.BaseTransport | None = None) -> Callable[[], Provider]:
    """`transport` is a test seam (a mock transport, no network); production passes nothing."""
    if st.llm_provider == "fake":
        if st.tw_env != "test":
            raise ProviderConfigError("LLM_PROVIDER=fake is only allowed with TW_ENV=test")
        from tracewise.investigate.fake import ScriptedProvider

        return lambda: ScriptedProvider([])  # every call fails → could_not_complete; process smoke tests only
    provider = _http_provider(st, transport)
    return lambda: provider


def _http_provider(st: Settings, transport: httpx.BaseTransport | None) -> HTTPProvider:
    name = st.llm_provider
    problem = llm_config_problem(st)
    if problem is not None:
        raise ProviderConfigError(problem)
    key: SecretStr | None = st.openai_api_key if name == "openai" else st.gemini_api_key
    assert st.llm_model is not None  # checked by llm_config_problem
    try:
        config = AdapterConfig(st.llm_model)
        codec: WireCodec = OpenAIResponsesWire() if name == "openai" else GeminiGenerateContentWire(st.llm_model)
    except ValueError:
        raise ProviderConfigError("LLM_MODEL is malformed") from None
    # The same transport stack as the benchmark's model mode: every request gets a real wall-clock deadline equal to
    # the investigation's remaining time, enforced at the socket layer.
    deadline = deadline_http.Deadline()
    network = transport or deadline_http.DeadlineHTTPTransport(deadline)
    client = httpx.Client(
        transport=deadline_http.RequestDeadlineTransport(network, deadline), follow_redirects=False, trust_env=False
    )
    try:
        return HTTPProvider(codec, key, config, client=client)
    except ValueError:
        client.close()
        raise ProviderConfigError(f"{LLM_KEY_SETTING[name]} is malformed") from None
