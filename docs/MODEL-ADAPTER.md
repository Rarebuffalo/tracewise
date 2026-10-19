# Model adapter status (T-605 preparation)

**Status:** the adapter core is built and contract-tested offline. **No real model is integrated or evaluated.** `LLM_PROVIDER=openai` refuses to start until an OpenAI wire codec exists, and that codec needs the recorded contract in §2.

## 1. What exists (`src/tracewise/investigate/http_adapter.py`)

`HTTPProvider` implements the investigator's `Provider` interface over one HTTPS endpoint. The vendor's wire format is held in a pluggable `WireCodec`, which encodes a `StepRequest` and decodes a `StepResponse`.

| Guarantee | Verified by (`tests/investigate/test_http_adapter.py`, offline `MockTransport`) |
|---|---|
| The key is a `SecretStr`, sent only in the codec's auth header, registered for log scrubbing, and absent from messages and `repr` | `test_valid_text_and_tool_call_responses`, `test_the_key_is_registered_for_log_scrubbing`, every error test |
| A missing or malformed key, a bad model name, a non-HTTPS endpoint, or credentials in the URL are refused at construction | `test_missing_or_invalid_configuration_is_refused` (10 cases) |
| 429, 5xx, timeouts and transport errors are retried at most `max_retries` times (0–3), with capped jittered backoff that honours `retry-after` but never exceeds the investigation's remaining time | the retry, rate-limit, timeout and budget tests |
| 401/403 → `ProviderAuthError`; other 4xx (including redirects, which are never followed) → `ProviderRequestError`; neither is retried | `test_permanent_errors_are_not_retried` |
| These fail closed as `ProviderError`, never retried, never quoting the body: invalid or truncated JSON, a wrong shape, an empty answer, a body over the byte cap, text over `max_output_chars`, tool calls where none are allowed | the malformed, oversized and tool-call tests |
| Through the real investigator, validator and renderer: a valid diagnosis is accepted; an unsupported claim becomes inconclusive; a provider failure becomes `provider_failed` | the pipeline tests |
| Prompt injection in a repository file and a log, with a model that "obeys": `run_shell`, `write_file` and `fetch` are rejected before dispatch, only the model endpoint is contacted, and the dangerous fix never reaches the diagnosis | `test_prompt_injection_in_repository_and_log_cannot_grant_capabilities` |

These are **adapter contract tests**. They use a wire format defined in the test file (provider recorded as `fake`). They are **not** evidence about any real model's accuracy, behaviour or injection resistance (E-01).

**Usage and cost:** token counts come only from the provider's response (the codec decodes them). Cost is computed only from configured prices (`LLM_PRICE_*`); otherwise it is `NULL`/"unpriced". Nothing is estimated. There is no fallback provider, so customer data never goes anywhere else.

## 2. OpenAI contract checklist (C-1 to C-9): blocker for the codec

Nothing below is assumed. Each item must come from the **official API reference**, recorded as evidence with its URL and fetch date (as the GitHub docs were), or, where marked, from an approved live call.

| ID | Must be established from the official contract | Code that depends on it | Tests that will verify it | Offline with a fake transport? | Needs a real call |
|---|---|---|---|---|---|
| C-1 | Which API (Chat Completions or Responses); exact endpoint URL; API version or date header | `WireCodec.endpoint`; `HTTPProvider` endpoint validation | Codec unit test that the request goes to the recorded URL; the existing endpoint-confinement test | Yes | One smoke call to confirm reachability and version |
| C-2 | Request schema: roles; how tool results reference a tool-call id; how the conversation is replayed | `WireCodec.encode` | Golden test: a `StepRequest` encodes byte-for-byte to the recorded example request | Yes, against recorded examples | No |
| C-3 | Function-tool declaration schema (name, description, JSON-schema parameters); how to forbid tools on the final step | `encode` (tools, `allow_tools`) | Golden tests with and without tools; `test_tool_calls_where_none_are_allowed_are_refused` (exists) | Yes | Whether the model honours "no tools" (behavioural) |
| C-4 | Response schema: text versus tool calls; whether arguments are a JSON string or an object; finish/stop reasons; refusal and content-filter shapes; truncation indicators | `WireCodec.decode` | Decode tests from recorded responses: text, tool calls, refusal, truncated or `length` stop, filter. Every unknown shape → `WireError` (pattern exists in `test_malformed_*`) | Yes | Observe the real refusal and truncation frequency |
| C-5 | The structured-output or JSON-mode option for the final answer, and its failure mode | `encode` (final-step options); `decode` | Golden test; schema-violation → existing repair → inconclusive path | Yes | Whether outputs conform in practice (feeds T-605) |
| C-6 | Usage field names (input, output and any cached or reasoning tokens) and whether they are always present | `decode` → `StepUsage` | Decode test; missing usage → `WireError` or explicit zero (decide from the contract) | Yes | Confirm counts against billing for the cost record |
| C-7 | Error body shape; HTTP status semantics (429 versus quota exhaustion, 5xx); rate-limit headers (`retry-after` or vendor-specific) | `HTTPProvider` error classes; `_retry_after` | Classification tests exist (`test_permanent_*`, `test_server_errors_*`, `test_rate_limit_*`). Add vendor headers and quota-vs-rate-limit tests. | Yes | Real 429 behaviour under load (optional) |
| C-8 | Auth header format; organisation/project headers; data-retention and training settings, and any zero-retention option, needed by the privacy notice | `WireCodec.auth_headers`; privacy notice §4 | Header golden test; key never logged (exists) | Yes (format only) | Account-level settings are configuration, not code: the owner confirms them |
| C-9 | Model identifier (UD-3); per-token prices; context and output limits | `LLM_MODEL`; `AdapterConfig`; `LLM_PRICE_*`; `InvestigationLimits` | Configuration validation; the cost computation test (exists) | Yes | Prices and limits for the chosen model are confirmed at evaluation time (T-605) |

**What unblocks the codec (no API key needed):**
1. Your approval to obtain the official OpenAI API reference pages for the chosen API.
2. Record them under `research/` as dated evidence, including example requests and responses for text, tool calls, refusals, errors and usage.
3. Your choice of API (C-1); recommended: whichever the recorded reference documents most completely for tool calls and structured output.

Then `OpenAIWire` can be written and golden-tested offline.

**A key is needed only later**, for the separately authorised T-605 evaluation.

**Until then** `LLM_PROVIDER=openai` refuses at startup (`investigate/providers.py`; `test_process_entrypoints.py`, case `LLM_PROVIDER=openai`). There is no fallback to `fake` or to any other provider.

## 3. Steps to finish T-605 (each needs your approval)

1. Record C-1 to C-8 as evidence.
2. Write `OpenAIWire` (codec only; the core is done). Contract-test it against recorded request and response examples.
3. Wire `LLM_PROVIDER=openai` in `investigate/providers.py`.
4. Provide a key **locally** (O-2). Run the benchmark with `--provider` set to the real model. Measure accuracy, cost (C-9) and latency, with at most 3 prompt/model iterations (TASKS rule 4). Run E-01 for injection resistance.
5. Choose the model (UD-3). Write the privacy notice (T-1001).
