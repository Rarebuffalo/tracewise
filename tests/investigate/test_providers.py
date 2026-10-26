"""Phase 32: provider selection boundary (no real model). The fake is refused in every non-test environment,
`openai` refuses (Phase 45D: the codec is offline-verified only and enabling is gated), and nothing
falls back to another provider."""

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
def test_openai_refuses_in_every_environment_until_enabling_is_approved(env: str) -> None:
    st = Settings(tw_env=env, llm_provider="openai", openai_api_key=SecretStr("placeholder-not-a-key"), llm_model="m")
    with pytest.raises(providers.ProviderConfigError) as e:
        providers.provider_factory(st)
    assert "not enabled" in str(e.value) and "§2b" in str(e.value) and "placeholder-not-a-key" not in str(e.value)


def test_fake_in_test_env_fails_closed_and_there_is_no_fallback() -> None:
    p = providers.provider_factory(Settings(tw_env="test", llm_provider="fake"))()
    with pytest.raises(ProviderError):  # an empty script: every call fails → could_not_complete, never a guess
        p.step(StepRequest((), (), False, 100, 1.0))
    src = inspect.getsource(providers)
    assert "except" not in src  # no error path that could switch to another provider
    assert src.count("return ") == 1  # one provider per configuration (the test-only fake)


def test_no_product_code_path_can_reach_a_real_model() -> None:
    """Phase 39, revised deliberately for the benchmark's model mode (T-605 preparation): the only network-capable
    provider (HTTPProvider) is constructed in exactly one place outside its own module, `bench/model_provider.py`,
    which only the owner-run benchmark CLI imports. Product selection still never constructs it, and no product
    module imports the benchmark's model mode or the key-file guards. Widening this must change this test again."""
    import re
    from pathlib import Path

    from tracewise.bench.providers import SCRIPTED

    src = Path(__file__).resolve().parents[2] / "src" / "tracewise"

    def mentioning(pattern: str, *, besides: str) -> list[str]:
        return sorted(
            str(p.relative_to(src)) for p in src.rglob("*.py") if p.name != besides and re.search(pattern, p.read_text())
        )

    assert mentioning(r"\bHTTPProvider\(", besides="http_adapter.py") == ["bench/model_provider.py"]
    assert mentioning(r"\bmodel_provider\b", besides="model_provider.py") == ["bench/__main__.py"]
    assert mentioning(r"\bmodel_access\b", besides="model_access.py") == ["bench/__main__.py", "bench/model_provider.py"]
    assert all("openai" not in name.lower() and "http" not in name.lower() for name in SCRIPTED)
    codecs = [
        p for p in src.rglob("*.py") if re.search(r"class \w*Wire\b|WireCodec\)", p.read_text()) and p.name != "http_adapter.py"
    ]
    # Phase 45D, widened deliberately on 2026-10-26: exactly two vendor codecs ship, both offline-tested only; product
    # selection wires neither, and only the benchmark's model mode imports them.
    assert sorted(p.name for p in codecs) == ["gemini_generate.py", "openai_responses.py"]
    assert mentioning(r"\bgemini_generate\b", besides="gemini_generate.py") == ["bench/model_provider.py"]
    selection = (src / "investigate" / "providers.py").read_text()
    assert "openai_responses" not in selection.split('"""', 2)[2] and "OpenAIResponsesWire" not in selection
    assert "model_provider" not in selection and "HTTPProvider" not in selection
    assert "gemini" not in selection.lower()
