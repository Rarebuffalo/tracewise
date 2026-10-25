"""Phase 47: the isolated OpenAI smoke harness (scripts/openai_smoke.py), exercised OFFLINE only.

No key is read, no real request is made: live mode is checked only on its refusal paths (it also refuses under
pytest and CI), and key-file acceptance is checked on the reader function alone.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "openai_smoke.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("openai_smoke_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(mod)
    return mod


S = _load()

EXPECTED = {
    "pass": ("pass", 3),
    "no_tool_call": ("observation_missing", 2),
    "missing_encrypted_content": ("unsupported_response", 2),
    "incomplete": ("unsupported_response", 1),
    "refusal": ("unsupported_response", 1),
    "unknown_item": ("unsupported_response", 1),
    "malformed_json": ("unsupported_response", 1),
    "too_large": ("unsupported_response", 1),
    "auth": ("auth", 1),
    "quota": ("quota", 1),  # never retried
    "rate_limited": ("unavailable", 1),  # no retries in the smoke harness
    "server_error": ("unavailable", 1),
    "bad_request": ("request_refused", 1),
    "transport_error": ("transport", 1),
    "final_step_rejects_without_tools": ("request_refused", 3),  # what a "no" to G-7 would look like
}
FORBIDDEN = [S.OFFLINE_KEY, S.OFFLINE_OPAQUE, S.OFFLINE_CALL_ID, "README.md", "list_dir tool", "two letters", "rs_offline"]


def run(*argv: str, env: dict[str, str] | None = None) -> tuple[int, dict[str, Any], str]:
    buf = io.StringIO()
    code = S.main(list(argv), env=env if env is not None else dict(os.environ), out=buf)
    text = buf.getvalue()
    return code, json.loads(text), text


def test_every_offline_scenario_is_covered() -> None:
    assert set(EXPECTED) == set(S.SCENARIOS)


@pytest.mark.parametrize("scenario", sorted(EXPECTED))
def test_offline_scenarios_classify_and_record_no_content(scenario: str) -> None:
    code, ev, text = run("--offline", scenario, "--model", "offline-model")
    want, sent = EXPECTED[scenario]
    assert (ev["result"], code, ev["requests_sent"]) == (want, S.EXIT[want], sent)
    assert [f for f in FORBIDDEN if f in text] == []
    assert "authorization" not in text.lower().replace("authorization_ref", "")  # no auth header is ever recorded
    if want not in ("pass", "observation_missing"):
        assert ev["failure"]["class"] == want and (ev["failure"]["detail"] is None)  # no provider message


def test_pass_sends_exact_ids_and_reasoning_once_without_tools_on_the_final_step() -> None:
    args = S.parse(["--offline", "pass", "--model", "offline-model"])
    deadline = S.Deadline(lambda: 0.0)
    provider, guarded, _ = S.build(args, {}, deadline)
    run_ = S.Run(provider, guarded, deadline, 60.0)
    assert S.run_steps(run_) == "pass"
    bodies = [json.loads(b) for b in guarded.inner.bodies]
    assert [b["store"] for b in bodies] == [False, False, False]
    assert ["tools" in b for b in bodies] == [False, True, False]  # G-7 is exercised exactly as the product does
    final = bodies[2]["input"]
    assert [i for i in final if i.get("type") == "reasoning"] == [S.REASONING]  # replayed once, verbatim
    assert [i["call_id"] for i in final if i.get("type") in ("function_call", "function_call_output")] == [
        S.OFFLINE_CALL_ID,
        S.OFFLINE_CALL_ID,
    ]  # >64 characters, unchanged (G-5)
    assert all(S.TOOL_RESULT not in json.dumps(b) or i == 2 for i, b in enumerate(bodies))


def test_the_synthetic_conversation_carries_no_repository_content() -> None:
    sent = " ".join([S.INSTRUCTIONS, S.TEXT_PROMPT, S.TOOL_PROMPT, S.TOOL_RESULT, S.FINAL_PROMPT])
    assert len(sent) < 600 and "tracewise" not in sent.lower() and "/" not in S.TOOL_RESULT


# ------------------------------------------------------------------ refusals (nothing is sent)


@pytest.mark.parametrize(
    "argv, env",
    [
        (["--live", "--model", "m-1", "--key-file", "/nonexistent", "--authorization-ref", "owner approval 1"], None),
        (["--live", "--model", "m-1", "--key-file", "/nonexistent", "--authorization-ref", "owner approval 1"], {"CI": "1"}),
        (["--live", "--model", "m-1"], {}),
        (["--live", "--model", "m-1", "--key-file", "/nonexistent"], {}),
        (["--live", "--model", "m-1", "--key-file", "/nonexistent", "--authorization-ref", "x"], {}),
        (["--live", "--model", "bad model!", "--key-file", "/nonexistent", "--authorization-ref", "owner approval 1"], {}),
        (["--offline", "pass", "--model", "m-1", "--key-file", "/nonexistent"], {}),
        (["--offline", "pass", "--model", "m-1", "--authorization-ref", "owner approval 1"], {}),
    ],
    ids=["under-pytest", "under-ci", "no-key-no-ref", "no-ref", "bad-ref", "bad-model", "offline-with-key", "offline-with-ref"],
)
def test_refusals_send_nothing(argv: list[str], env: dict[str, str] | None) -> None:
    code, ev, _ = run(*argv, env=env)
    assert (ev["result"], code, ev["requests_sent"], ev["exchanges"]) == ("refused", 2, 0, [])


def test_live_with_a_missing_key_file_is_refused_outside_ci_and_pytest() -> None:
    code, ev, _ = run(
        "--live", "--model", "m-1", "--key-file", "/nonexistent/key", "--authorization-ref", "owner approval 1", env={}
    )
    assert code == 2 and ev["failure"]["detail"] == "key file is not readable" and ev["requests_sent"] == 0


def test_model_is_mandatory_with_no_default() -> None:
    with pytest.raises(SystemExit) as e:
        S.parse(["--offline", "pass"])
    assert e.value.code == 2


def test_key_file_rules(tmp_path: Path) -> None:
    good = tmp_path / "k"
    good.write_text("synthetic-file-key-0000\n")
    good.chmod(0o600)
    assert S.read_key_file(str(good)).get_secret_value() == "synthetic-file-key-0000"  # never printed by the harness
    loose = tmp_path / "loose"
    loose.write_text("synthetic-file-key-0000")
    loose.chmod(0o644)
    link = tmp_path / "link"
    link.symlink_to(good)
    big = tmp_path / "big"
    big.write_text("x" * 600)
    big.chmod(0o600)
    for bad, why in [(loose, "owner only"), (link, "symlink"), (big, "too large"), (tmp_path, "regular file")]:
        with pytest.raises(S.Refused, match=why):
            S.read_key_file(str(bad))
    inside = ROOT / "pyproject.toml"  # any file inside the repository is refused, whatever its mode
    with pytest.raises(S.Refused):
        S.read_key_file(str(inside))


def test_guarded_transport_allows_only_the_recorded_endpoint_and_budget() -> None:
    import httpx

    forwarded: list[httpx.Request] = []

    def inner(req: httpx.Request) -> httpx.Response:
        forwarded.append(req)
        return httpx.Response(200, json={})

    g = S.GuardedTransport(httpx.MockTransport(inner), S.Deadline())
    with pytest.raises(S.Refused):
        g.handle_request(httpx.Request("POST", "https://example.invalid/v1/responses", content=b"{}"))
    with pytest.raises(S.Refused):
        g.handle_request(httpx.Request("GET", S.ENDPOINT))
    with pytest.raises(S.Refused):
        g.handle_request(httpx.Request("POST", S.ENDPOINT, content=b"x" * (S.MAX_REQUEST_BYTES + 1)))
    assert forwarded == [] and g.sent == 0  # destination, method and size refusals never reach the inner transport
    at_cap = b'{"p":"' + b"x" * (S.MAX_REQUEST_BYTES - 8) + b'"}'
    assert len(at_cap) == S.MAX_REQUEST_BYTES
    g.handle_request(httpx.Request("POST", S.ENDPOINT, content=at_cap))  # exactly at the cap: forwarded
    for _ in range(S.MAX_REQUESTS - 1):
        g.handle_request(httpx.Request("POST", S.ENDPOINT, content=b"{}"))
    with pytest.raises(S.Refused, match="budget"):
        g.handle_request(httpx.Request("POST", S.ENDPOINT, content=b"{}"))
    assert len(forwarded) == g.sent == S.MAX_REQUESTS  # the over-budget request was not forwarded either


def test_every_outgoing_request_carries_the_2048_output_token_cap() -> None:
    """Through the real path: run_steps → product adapter → OpenAIResponsesWire.encode → guarded transport, captured
    as serialised bytes by the offline transport (no network). Every one of the three requests carries the cap, and
    the recorded evidence reports the same value per exchange."""
    args = S.parse(["--offline", "pass", "--model", "offline-model"])
    deadline = S.Deadline(lambda: 0.0)
    provider, guarded, _ = S.build(args, {}, deadline)
    try:
        assert S.run_steps(S.Run(provider, guarded, deadline, 60.0)) == "pass"
    finally:
        provider.close()
    bodies = [json.loads(b) for b in guarded.inner.bodies]
    assert len(bodies) == S.MAX_REQUESTS == 3
    assert [b["max_output_tokens"] for b in bodies] == [2048, 2048, 2048]
    assert [rec["request"]["max_output_tokens"] for rec in guarded.records] == [2048, 2048, 2048]


def test_usage_breakdowns_are_recorded_as_integers_only() -> None:
    """Reasoning and cached token counts (R-11) are recorded when present, so the authorised run can show whether
    reasoning tokens fall inside `output_tokens`; anything that is not an integer is ignored, never echoed."""
    usage = {
        "input_tokens": 40,
        "output_tokens": 30,
        "total_tokens": 70,
        "output_tokens_details": {"reasoning_tokens": 24},
        "input_tokens_details": {"cached_tokens": 0},
    }
    shape = S.response_shape(200, json.dumps({**S.OK, "usage": usage}).encode(), httpx_headers())
    assert shape["usage"] == {
        "input_tokens": 40,
        "output_tokens": 30,
        "total_tokens": 70,
        "reasoning_tokens": 24,
        "cached_tokens": 0,
    }
    odd = {**usage, "output_tokens_details": {"reasoning_tokens": "LEAK-text"}, "input_tokens_details": "x"}
    shape = S.response_shape(200, json.dumps({**S.OK, "usage": odd}).encode(), httpx_headers())
    assert "reasoning_tokens" not in shape["usage"] and "cached_tokens" not in shape["usage"]
    assert "LEAK-text" not in json.dumps(shape)


def httpx_headers() -> object:
    import httpx

    return httpx.Headers({})


# ------------------------------------------------------------------ isolation (cannot run by accident)


def test_the_harness_is_unreachable_from_product_code_and_standard_commands() -> None:
    for p in (ROOT / "src").rglob("*.py"):
        assert "openai_smoke" not in p.read_text(), p
    for f in ("Makefile", "pyproject.toml"):
        assert "openai_smoke" not in (ROOT / f).read_text()
    assert not list(ROOT.glob(".github/**/*.yml")) or all(
        "openai_smoke" not in p.read_text() for p in ROOT.glob(".github/**/*.yml")
    )
    assert not SCRIPT.name.startswith("test_")  # never collected by pytest
    src = SCRIPT.read_text()
    assert "OPENAI_API_KEY" not in src and src.count("os.environ") == 1  # flags only (PYTEST_CURRENT_TEST, CI)
    assert "max_retries=0" in src


def test_the_actual_command_offline_and_its_refusal() -> None:
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    ok = subprocess.run(  # noqa: S603 - fixed argv, offline fixture
        [sys.executable, str(SCRIPT), "--offline", "pass", "--model", "offline-model"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    assert ok.returncode == 0 and json.loads(ok.stdout)["result"] == "pass" and ok.stderr == ""
    live = subprocess.run(  # noqa: S603 - refused before any network: PYTEST_CURRENT_TEST is inherited
        [sys.executable, str(SCRIPT), "--live", "--model", "m-1", "--key-file", "/nonexistent", "--authorization-ref", "test x1"],
        capture_output=True,
        text=True,
        timeout=60,
        env={**env, "PYTEST_CURRENT_TEST": "harness-isolation"},
        check=False,
    )
    assert live.returncode == 2 and json.loads(live.stdout)["requests_sent"] == 0
    none = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    assert none.returncode == 2 and none.stdout == ""
