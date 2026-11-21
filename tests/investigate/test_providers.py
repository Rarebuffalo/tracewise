"""Provider selection boundary (no real model, no network). The fake is refused in every non-test environment;
`openai` and `gemini` are built from the operator's own key and an explicit model (bring your own key, 2026-11-21),
reach only their codec's endpoint, and nothing falls back to another provider."""

from __future__ import annotations

import inspect

import httpx
import pytest
from pydantic import SecretStr

from tracewise.config import Settings
from tracewise.investigate import providers
from tracewise.investigate.provider import Message, ProviderError, StepRequest


@pytest.mark.parametrize("env", ["local", "staging", "prod"])
def test_fake_provider_is_refused_outside_test(env: str) -> None:
    with pytest.raises(providers.ProviderConfigError, match="only allowed with TW_ENV=test"):
        providers.provider_factory(Settings(tw_env=env, llm_provider="fake"))


KEY = "placeholder-not-a-key-000000"
ENDPOINTS = {
    "openai": "https://api.openai.com/v1/responses",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/m-1:generateContent",
}


def _real(name: str, env: str = "prod", **over: object) -> Settings:
    keys = {"openai_api_key": SecretStr(KEY)} if name == "openai" else {"gemini_api_key": SecretStr(KEY)}
    base: dict[str, object] = {"tw_env": env, "llm_provider": name, "llm_model": "m-1", **keys}
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["openai", "gemini"])
@pytest.mark.parametrize("env", ["test", "local", "staging", "prod"])
def test_real_providers_are_built_from_the_operators_key_and_model_in_every_environment(name: str, env: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={"error": {"message": "nope"}})

    make = providers.provider_factory(_real(name, env), transport=httpx.MockTransport(handler))
    p = make()
    assert make() is p  # one provider per worker process
    assert p.name == name and p.model == "m-1"
    with pytest.raises(ProviderError) as e:  # 401 is permanent: one request, no retry, no fallback
        p.step(StepRequest((Message("system", "s"), Message("user", "u")), (), False, 100, 5.0))
    assert len(seen) == 1 and str(seen[0].url) == ENDPOINTS[name] and seen[0].method == "POST"
    assert KEY not in str(e.value)


@pytest.mark.parametrize("name", ["openai", "gemini"])
def test_a_real_provider_needs_an_explicit_well_formed_model(name: str) -> None:
    with pytest.raises(providers.ProviderConfigError, match="requires LLM_MODEL"):
        providers.provider_factory(_real(name, llm_model=None))
    with pytest.raises(providers.ProviderConfigError, match="LLM_MODEL is malformed") as e:
        providers.provider_factory(_real(name, llm_model="bad model/../x"))
    assert KEY not in str(e.value)


@pytest.mark.parametrize(("name", "setting"), [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")])
def test_a_real_provider_needs_its_own_key(name: str, setting: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=setting):
        Settings(_env_file=None, llm_provider=name, llm_model="m-1")  # type: ignore[call-arg, arg-type]
    other = {"gemini_api_key": SecretStr(KEY)} if name == "openai" else {"openai_api_key": SecretStr(KEY)}
    with pytest.raises(ValidationError, match=setting):  # the other provider's key is never used
        Settings(_env_file=None, llm_provider=name, llm_model="m-1", **other)  # type: ignore[call-arg, arg-type]
    with pytest.raises(providers.ProviderConfigError, match=f"{setting} is malformed") as e:
        providers.provider_factory(_real(name, **{f"{name}_api_key": SecretStr("has space in it")}))
    assert "has space" not in str(e.value)


def test_gemini_key_is_redacted_like_the_others() -> None:
    assert KEY in _real("gemini").secret_values()


def test_fake_in_test_env_fails_closed_and_there_is_no_fallback() -> None:
    p = providers.provider_factory(Settings(tw_env="test", llm_provider="fake"))()
    with pytest.raises(ProviderError):  # an empty script: every call fails → could_not_complete, never a guess
        p.step(StepRequest((), (), False, 100, 1.0))
    src = inspect.getsource(providers.provider_factory)
    assert "except" not in src  # no error path that could switch to another provider
    assert src.count("return ") == 2  # the test-only fake, or the one configured real provider


def test_the_network_capable_provider_is_built_in_exactly_two_places() -> None:
    """Revised deliberately on 2026-11-21 (bring your own key): `HTTPProvider` is constructed only by product
    selection (`investigate/providers.py`, from the operator's settings) and by the owner-run benchmark's model mode.
    The benchmark's key-file guards stay benchmark-only. Widening this must change this test again."""
    import re
    from pathlib import Path

    from tracewise.bench.providers import SCRIPTED

    src = Path(__file__).resolve().parents[2] / "src" / "tracewise"

    def mentioning(pattern: str, *, besides: str) -> list[str]:
        return sorted(
            str(p.relative_to(src)) for p in src.rglob("*.py") if p.name != besides and re.search(pattern, p.read_text())
        )

    assert mentioning(r"\bHTTPProvider\(", besides="http_adapter.py") == ["bench/model_provider.py", "investigate/providers.py"]
    assert mentioning(r"\bmodel_provider\b", besides="model_provider.py") == ["bench/__main__.py"]
    assert mentioning(r"\bmodel_access\b", besides="model_access.py") == ["bench/__main__.py", "bench/model_provider.py"]
    assert all("openai" not in name.lower() and "http" not in name.lower() for name in SCRIPTED)
    codecs = [
        p for p in src.rglob("*.py") if re.search(r"class \w*Wire\b|WireCodec\)", p.read_text()) and p.name != "http_adapter.py"
    ]
    assert sorted(p.name for p in codecs) == ["gemini_generate.py", "openai_responses.py"]
    assert mentioning(r"\bgemini_generate\b", besides="gemini_generate.py") == [
        "bench/model_provider.py",
        "investigate/providers.py",
    ]
    selection = (src / "investigate" / "providers.py").read_text()
    assert "model_provider" not in selection and "model_access" not in selection
