"""Benchmark model mode (T-605 preparation): the product's own adapter and OpenAI codec, owner-run, guarded.

This is the only module outside `investigate/http_adapter.py` that constructs an `HTTPProvider`. It is reached only
from `python -m tracewise.bench run --kind model`; product provider selection (`investigate/providers.py`) still
refuses `LLM_PROVIDER=openai`, and no product module imports this one (structural test in
`tests/investigate/test_providers.py`).

Guards (each a refusal before anything is sent):
* never under a test runner or CI (`PYTEST_CURRENT_TEST` or `CI` set);
* an explicit model id (no default, no fallback) and a written authorisation reference;
* the key only from an owner-only regular file outside the repository (`model_access.read_key_file`);
* a hard request cap counted by a host-locked transport (POST to the recorded endpoint only); `max_retries=0`;
* a request-body cap (`MAX_REQUEST_BYTES`), checked on the serialised body before anything is sent;
* a real wall-clock deadline per request equal to the investigation's remaining time (`deadline_http`), enforced
  at the socket layer, so a trickling response cannot outlive the investigation's budget.

When the cap is reached the evaluation stops: the harness (`run_suite(budget=...)`) marks the run that was cut off
and every run not started as `interrupted`, which is never scored (docs/MODEL-ADAPTER.md §3a). The key itself stays
inside the adapter and a `SecretCanary`; nothing here returns it.

The model never sees `reference.yaml` or `truth.yaml`: the factory ignores the reference it is handed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

from tracewise.bench.model import CaseSpec, Reference
from tracewise.bench.providers import ProviderFactory
from tracewise.investigate import deadline_http, model_access
from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider
from tracewise.investigate.openai_responses import ENDPOINT, OpenAIResponsesWire
from tracewise.investigate.provider import Provider

MAX_REQUESTS_CEILING = 2000  # a sanity bound on the flag; the owner sets the actual cap for each run
# Request-body cap. Not the smoke harness's 32 KiB: its prompts are a few hundred bytes, while the evidence bundle
# alone may be 24,000 characters (prompt.MAX_BUNDLE_CHARS). The investigation's own caps bound the conversation:
# system policy ~1.6 kB + bundle 24,000 + up to 12 tool results of at most 8,000 characters (ToolLimits) + up to 12
# argument sets of at most 1,024 (InvestigationLimits) + a 2,000-character repair turn: about 135,000 characters, plus
# JSON escaping. 256 KiB leaves room for the model's own short turns and replayed reasoning items. A longer
# conversation is refused unsent, and that run is an error row (docs/MODEL-ADAPTER.md §3a).
MAX_REQUEST_BYTES = 256 * 1024
NOTICE = (
    "Model-based evaluation on synthetic benchmark cases. These results describe one run of one model under the "
    "stated limits; they are not proven model accuracy and must not be quoted as real-world accuracy."
)


@dataclass
class ModelRun:
    provider: HTTPProvider
    transport: model_access.EndpointBudgetTransport
    model: str
    authorization_ref: str
    leak_check: model_access.SecretCanary  # checks outputs for the key; never exposes it

    # `bench.harness.RunBudget`: the harness stops the evaluation once the cap is reached.
    def exhausted(self) -> bool:
        return self.transport.exhausted

    def refusals(self) -> int:
        return self.transport.budget_refused

    def oversized(self) -> int:
        return self.transport.oversize_refused

    def factory(self) -> ProviderFactory:
        def make(_spec: CaseSpec, _commit: str, _ref: Reference | None) -> Provider:
            # The reference is deliberately ignored: a model must never see the expected answer.
            if self.transport.exhausted:
                raise model_access.RequestBudgetExhausted("request budget exhausted")  # recorded as an error row
            return self.provider

        return make

    def summary(self) -> dict[str, object]:
        """Content-free run facts for results.json: never the key, the key path, or any response text."""
        t = self.transport
        return {
            "model": self.model,
            "authorization_ref": self.authorization_ref,
            "max_retries": 0,
            "requests": {
                "max": t.max_requests,
                "sent": t.sent,
                "refused": t.refused,
                "refused_over_cap": t.budget_refused,
                "refused_too_large": t.oversize_refused,
                "budget_exhausted": t.exhausted,
            },
            "max_request_bytes": t.max_request_bytes,
            "notice": NOTICE,
        }

    def close(self) -> None:
        self.provider.close()


def build_model_run(
    *,
    model: str | None,
    key_file: str | Path | None,
    authorization_ref: str | None,
    max_requests: int | None,
    env: Mapping[str, str],
    inner: httpx.BaseTransport | None = None,
    repo_root: Path = model_access.REPO_ROOT,
) -> ModelRun:
    """Every check runs before the key is read or a client exists. `inner` is a test seam for a mock transport; the
    automation refusal applies regardless, so tests pass an explicit empty `env`."""
    model_access.refuse_under_automation(env)
    ref = model_access.check_authorization_ref(authorization_ref)
    if not model:
        raise model_access.AccessRefused("an explicit model id is required")
    if max_requests is None or not 1 <= max_requests <= MAX_REQUESTS_CEILING:
        raise model_access.AccessRefused(f"--max-requests must be between 1 and {MAX_REQUESTS_CEILING}")
    if key_file is None:
        raise model_access.AccessRefused("a key file is required")
    try:
        config = AdapterConfig(model, max_retries=0)  # validates the model id shape
    except ValueError:
        raise model_access.AccessRefused("model id is malformed") from None
    key = model_access.read_key_file(key_file, repo_root=repo_root)
    deadline = deadline_http.Deadline()
    network = inner or deadline_http.DeadlineHTTPTransport(deadline)  # `inner`: a test seam for a mock transport
    timed = deadline_http.RequestDeadlineTransport(network, deadline)
    transport = model_access.EndpointBudgetTransport(timed, ENDPOINT, max_requests, max_request_bytes=MAX_REQUEST_BYTES)
    client = httpx.Client(transport=transport, follow_redirects=False, trust_env=False)
    provider = HTTPProvider(OpenAIResponsesWire(), key, config, client=client)
    return ModelRun(provider, transport, model, ref, model_access.SecretCanary(key))
