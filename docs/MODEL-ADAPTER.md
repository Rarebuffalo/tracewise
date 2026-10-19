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

## 2. What must be recorded before an OpenAI codec is written

The repository's recorded evidence (`research/final-evidence-review/evidence/docs/`) covers GitHub only. None of the following is recorded. Each needs the official API reference captured as evidence (like the GitHub docs, with fetch date and URL) or observed in the first approved call:

| ID | Unresolved detail |
|---|---|
| C-1 | Which API: Chat Completions or Responses. Endpoint URL and API version. |
| C-2 | The request schema for system/user/assistant/tool messages, including how tool results reference a tool-call id |
| C-3 | The function-tool declaration schema, and how to forbid tool calls on the final step |
| C-4 | The response schema for text versus tool calls (arguments as a JSON string or an object), finish/stop reasons, and refusals |
| C-5 | The structured-output or JSON-mode option used for the final answer |
| C-6 | Field names for usage (input and output tokens) |
| C-7 | The error-body shape, and the rate-limit headers (`retry-after` and others) |
| C-8 | Auth header format, organisation/project headers, and a data-retention setting if the privacy notice (T-1001) requires one |
| C-9 | The model identifier (UD-3) and per-token prices for the cost record |

## 3. Steps to finish T-605 (each needs your approval)

1. Record C-1 to C-8 as evidence.
2. Write `OpenAIWire` (codec only; the core is done). Contract-test it against recorded request and response examples.
3. Wire `LLM_PROVIDER=openai` in `investigate/providers.py`.
4. Provide a key **locally** (O-2). Run the benchmark with `--provider` set to the real model. Measure accuracy, cost (C-9) and latency, with at most 3 prompt/model iterations (TASKS rule 4). Run E-01 for injection resistance.
5. Choose the model (UD-3). Write the privacy notice (T-1001).
