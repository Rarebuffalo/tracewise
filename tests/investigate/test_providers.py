"""Phase 32: provider selection boundary (no real model). The fake is refused in every non-test environment,
`openai` refuses until a recorded-contract codec exists, and nothing falls back to another provider."""

from __future__ import annotations

import inspect

import pytest
from pydantic import SecretStr

from tracewise.config import Settings
from tracewise.investigate import providers
from tracewise.investigate.provider import ProviderError, StepRequest


@pytest.mark.parametrize("env", ["local", "staging", "prod"])
def test_fake_provider_is_refused_outside_test(env: str) -> None:
    with pytest.raises(providers.ProviderConfigError, match="only allowed with TW_ENV=test"):
        providers.provider_factory(Settings(tw_env=env, llm_provider="fake"))


@pytest.mark.parametrize("env", ["test", "local", "staging", "prod"])
def test_openai_refuses_in_every_environment_until_the_codec_exists(env: str) -> None:
    st = Settings(tw_env=env, llm_provider="openai", openai_api_key=SecretStr("placeholder-not-a-key"), llm_model="m")
    with pytest.raises(providers.ProviderConfigError) as e:
        providers.provider_factory(st)
    assert "contract is not recorded" in str(e.value) and "placeholder-not-a-key" not in str(e.value)


def test_fake_in_test_env_fails_closed_and_there_is_no_fallback() -> None:
    p = providers.provider_factory(Settings(tw_env="test", llm_provider="fake"))()
    with pytest.raises(ProviderError):  # an empty script: every call fails → could_not_complete, never a guess
        p.step(StepRequest((), (), False, 100, 1.0))
    src = inspect.getsource(providers)
    assert "except" not in src  # no error path that could switch to another provider
    assert src.count("return ") == 1  # one provider per configuration (the test-only fake)
