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

**Repository evidence check (Phase 32; superseded by §2b):** none of C-1 to C-9 is established by repository evidence. The recorded documentation under `research/` is GitHub-only, and nothing about OpenAI is recorded. Every item still needs the official reference. Items C-1 to C-7 can then be tested offline with a fake transport against recorded examples. C-8 (account settings) and C-9 (prices and limits) need the owner's confirmation, and their real-world behaviour needs the authorised T-605 calls.

**What unblocks the codec (no API key needed):**
1. Your approval to obtain the official OpenAI API reference pages for the chosen API.
2. Record them under `research/` as dated evidence, including example requests and responses for text, tool calls, refusals, errors and usage.
3. Your choice of API (C-1); recommended: whichever the recorded reference documents most completely for tool calls and structured output.

Then `OpenAIWire` can be written and golden-tested offline.

**A key is needed only later**, for the separately authorised T-605 evaluation.

**Until then** `LLM_PROVIDER=openai` refuses at startup (`investigate/providers.py`; `test_process_entrypoints.py`, case `LLM_PROVIDER=openai`). There is no fallback to `fake` or to any other provider.

## 2a. Offline readiness report (Phase 39)

| Question | Answer |
|---|---|
| Can a real model be reached today? | **No.** `HTTPProvider` is never constructed in product code. No vendor codec exists. `LLM_PROVIDER=openai` refuses in every environment. The fake provider is refused outside `TW_ENV=test`. The benchmark CLI offers scripted providers only. Evidence: `tests/investigate/test_providers.py` (including the structural test `test_no_code_path_can_reach_a_real_model_today`), `test_process_entrypoints.py`, and the network-guarded full suite. |
| Reference material that needs your approval | The official OpenAI API reference pages, for the chosen API (C-1), covering: the request schema with messages and tools (C-2, C-3); the response schema with tool calls, refusals and finish reasons (C-4); structured output (C-5); usage fields (C-6); the error format and rate-limit headers (C-7); authentication and organisation/project headers (C-8); the model list, limits and prices (C-9). Recorded as dated evidence with example requests and responses. |
| Implementable offline after that approval | `OpenAIWire` (`endpoint`, `auth_headers`, `encode`, `decode`); `providers.py` wiring for `LLM_PROVIDER=openai`; golden encode/decode tests from the recorded examples; error and rate-limit classification tests for C-7; configuration validation for C-9 |
| Needs a key and an authorised evaluation later | One reachability smoke call (C-1); behavioural checks (tool-use compliance, refusal and truncation frequency, structured-output conformance); usage-versus-billing reconciliation (C-6, C-9); real 429 behaviour; the T-605 benchmark run, E-01 injection resistance, model choice (UD-3), latency and cost |
| Owner-only (no code) | Account data-retention and training settings (C-8), for the privacy notice |

## 2b. Phase 45D status: Responses codec implemented offline; selection still refused

The owner approved retrieving the official reference (Phase 45). It is recorded in
[research/openai-api-reference-2026-10-19/README.md](../research/openai-api-reference-2026-10-19/README.md):
sources S-1 to S-6 on `developers.openai.com`, retrieved 2026-10-19, with facts R-1 to R-14 and gaps G-1 to G-6. The
pages state no API version string. `platform.openai.com` returned 403, so only `developers.openai.com` was used.

**API chosen (C-1):** Responses (`POST /v1/responses`). The codec is `OpenAIResponsesWire` in
`src/tracewise/investigate/openai_responses.py`; its tests are in `tests/investigate/test_openai_responses.py`
(synthetic fixtures built to the recorded field names, `httpx.MockTransport`, no network, no real key).

| Item | Status | Contract | Implementation and test |
|---|---|---|---|
| C-1 | **Offline done**; reachability open (G-4) | R-1 | `ENDPOINT`; each request goes only to it (`test_full_investigation_*`, `test_overload_503_*`) |
| C-2 | **Offline done** | R-3, R-4, R-6, R-10 | System messages → `instructions`; tool results → `function_call_output` paired by `call_id`; reasoning items replayed verbatim (`Message.replay`); `store: false` (`test_encode_maps_*`) |
| C-3 | **Offline done** | R-7, R-8, R-9 | The 4 read-only tools only, `strict: false` (our specs have optional fields, R-8); tools and `tool_choice` omitted on the final step (`test_encode_without_tools_*`). The loop still refuses tool calls on that step. |
| C-4 | **Offline done**; real frequency open (G-1, G-4) | R-5, R-11, R-13 | Any status other than `completed`, refusal, unknown item or content part, malformed call → `WireError` → `provider_failed`, never a diagnosis (`test_decode_fails_closed_*`) |
| C-5 | **Decided: not used** | R-3 | No `text.format`; the investigator's own JSON validation and repair path stays authoritative. `json_schema` is a possible later improvement. |
| C-6 | **Offline done**; billing reconciliation open | R-11 | `input_tokens`/`output_tokens` required integers; missing usage → `WireError` (never invented) |
| C-7 | **Offline done**; error-body example missing (G-2) | R-12, R-14 | Quota/billing 429 (`credit_balance_exhausted`, spend/usage limit codes, `insufficient_quota`) → `ProviderQuotaError`, not retried; rate-limit 429 and 503 retried within the existing bounds honouring `Retry-After`; 401 not retried, key never in the error (`test_quota_429_*`, `test_rate_limit_429_*`, `test_overload_503_*`) |
| C-8 | **Format done**; account settings owner-only | R-2 | `Authorization: Bearer`; no organisation/project headers sent. Data-retention and training settings of the account are for the owner to confirm (privacy notice §4). |
| C-9 | **Open** (G-6) | none | Model id, limits and prices are not taken from the pages; they stay configuration (`LLM_MODEL`, `LLM_PRICE_*`) for T-605/UD-3 |

**Integration decisions (ours, recorded in the evidence file):** `store: false`; `max_output_tokens` receives the
existing `max_output_chars` cap as an upper bound (characters ≥ tokens for this content, so it never loosens the cap);
provider-issued call ids are sent back exactly (Phase 46 corrected an earlier 64-character cap that could merge two
distinct ids); a duplicate, missing or unpaired id fails closed before anything is sent (G-5); a refusal is never a
diagnosis.

**Reasoning replay (Phase 46 audit):** `Message.replay` is the one channel that skips P-2 redaction. It carries only
`reasoning` items decoded from the provider's own response, with a non-empty `id` and `encrypted_content`. They
are attached to the assistant turn of the same response and emitted before that turn's function calls. They live
only in memory for one investigation: they are never persisted, and a job retry starts a new conversation. Encode
refuses any other item in this channel. Their plaintext `summary` is model-authored; it can only reflect input the
model received, which was already redacted. G-7 (final step without `tools`) and G-8 (`encrypted_content` always
present) are open questions for the smoke call.

**P-2 on the real codec:** the redacted `provider_view` is what the codec serialises; the end-to-end test plants a
secret-shaped value in a source file and checks the serialised bytes. Pattern-based redaction remains incomplete (P-4).

**Why `LLM_PROVIDER=openai` still refuses** (`investigate/providers.py`; `test_providers.py`):
1. Nothing has been observed from the real endpoint (G-4). The fixtures prove the codec follows the recorded
   contract, not that the service behaves as recorded.
2. Real-model evaluation (T-605), the key (O-2) and the model choice (UD-3, C-9) are not authorised.
3. G-1, G-3, G-5, G-7 and G-8 are handled by failing closed, which needs one real observation to confirm it is not over-strict.

**To enable (each needs your approval):** one authorised smoke call (G-4) with a project-scoped key held locally; then
change `providers.py` to construct `HTTPProvider(OpenAIResponsesWire(), …)` and update the structural test
`test_no_code_path_can_reach_a_real_model_today` deliberately; then the T-605 evaluation. There is no fallback to `fake`.

## 2c. Phase 47: gap classification and the smoke harness

Each open question is classified using only the recorded contract. "Fails closed" means the investigator reports
`provider_failed` (inconclusive), never a diagnosis.

| Gap or item | Requirement (recorded) | Implementation | Test | Class | What the smoke run must establish |
|---|---|---|---|---|---|
| G-1 incomplete reasons | R-13: `incomplete_details.reason`; only `max_output_tokens` named | Any status other than `completed` → `WireError` | `test_decode_fails_closed_*[incomplete]`; harness `incomplete` | Safe by failing closed; full list needs observation | Records `incomplete_reason` if one occurs |
| G-2 error body | R-12: `error.code`, `error.type`, `error.param` named, no example | Tolerant read; documented quota codes and types → `ProviderQuotaError` (never retried); anything else on 429/5xx retryable within bounds; 401/403 permanent | `test_quota_429_*`, `test_rate_limit_429_*`, `test_overload_503_*`; harness `quota`, `rate_limited`, `auth` | Safe by failing closed; shape needs observation | Records error key names, `code` and `type` (no message) only if an error occurs |
| G-3 / G-8 reasoning items | R-10: pass back reasoning items; with `store: false` they carry `encrypted_content` by default | Only reasoning items with `id` and `encrypted_content` are kept and replayed verbatim; otherwise fail closed | `test_reasoning_*`, `test_decode_refuses_reasoning_*`; harness `missing_encrypted_content` | Needs observation | Step 2: whether reasoning items appear, and whether `encrypted_content` is present |
| G-5 call ids | R-5/R-6: pairing by `call_id`; no length documented | Exact ids; duplicate, missing or unpaired → fail closed | `test_ids_*`, `test_encode_refuses_*`; harness `pass` (an id longer than 64 characters) | Resolved offline for our side; real lengths need observation | Step 2: call id length; step 3: the pairing is accepted |
| G-7 tools omitted on the final step | Not documented; R-9 offers `tool_choice: "none"` | `tools` omitted when `allow_tools` is false | harness `pass`, `final_step_rejects_without_tools` | Needs observation | Step 3 accepted (exit 0) or 400 (exit 7). If 400, fix in the codec with tests before T-605. |
| `store: false` | R-3: `store` defaults to true | Always `false` | `test_encode_maps_*`; harness requests record `store` | Resolved (decision); account-level retention is C-8 | Nothing in code; the owner confirms account settings (A-4) |
| Quota versus rate limit | R-12, R-14 | See G-2 | See G-2 | Resolved offline from R-12 | Only if it occurs |
| Bounded rounds, time, retries | Ours (FS-DX-3) | `InvestigationLimits`; adapter `max_retries` ≤3 and deadline; the harness uses 0 retries and at most 3 requests | `test_loop*`, `test_http_adapter*`, harness budget test | Resolved offline | Nothing |
| G-4 reachability | n/a | n/a | n/a | Needs observation | Exit 0 |
| G-6 / C-9 model, limits, prices | not recorded | Configuration only | n/a | Owner decision and model information | Not established by the smoke run, except token usage for the cost record |

**No code change was needed for 47B.** Every gap the contract leaves open already fails closed. The remaining ones can only be closed by the smoke observation or an owner decision.

**Smoke harness:** `scripts/openai_smoke.py`, with its procedure, limits, evidence policy and authorisation checklist in [SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md). It is not part of the product: `providers.py` still refuses `LLM_PROVIDER=openai`.

## 3. Steps to finish T-605 (each needs your approval)

1. ~~Record C-1 to C-8 as evidence.~~ Done (Phase 45, §2b).
2. ~~Write the codec and contract-test it offline.~~ Done (`OpenAIResponsesWire`, §2b).
3. After the smoke call (G-4), wire `LLM_PROVIDER=openai` in `investigate/providers.py`.
4. Provide a key **locally** (O-2). Run the benchmark with `--provider` set to the real model. Measure accuracy, cost (C-9) and latency, with at most 3 prompt/model iterations (TASKS rule 4). Run E-01 for injection resistance.
5. Choose the model (UD-3). Write the privacy notice (T-1001).
