# Gemini API reference: recorded contract (owner-authorised retrieval, 2026-10-26)

**Retrieved:** 2026-10-26, by an automated fetch of official Google documentation pages only (`ai.google.dev`). No
API key was used, no API request or model call was made, and no credentials were read. Only short excerpts are
reproduced; the rest are field names and structural facts.

**How the pages were read:** each page was fetched and summarised by a fetch tool asked for verbatim excerpts. The
tool limits each quote to about 125 characters and paraphrases the rest; paraphrase is marked as such below. Excerpts
are therefore short and some are trimmed with "…". Before any code relies on a fact, re-read the cited page.

Several pages now document the **Interactions API** (`/v1beta/interactions`), which the API overview labels
"(Recommended)". The Chat Completions compatibility layer and the native `generateContent` API are documented
separately and less completely (see the gaps).

## Sources

| ID | URL | Last updated (as shown) | Used for |
|---|---|---|---|
| S-1 | https://ai.google.dev/gemini-api/docs/openai | 2026-10-22 | OpenAI compatibility (Chat Completions): endpoint, auth, limitations, thinking mapping |
| S-2 | https://ai.google.dev/gemini-api/docs/function-calling | not captured | Function calling (Interactions API): steps, modes, parallel and multi-turn calls |
| S-3 | https://ai.google.dev/gemini-api/docs/thinking | 2026-10-14 | Thinking levels, thought signatures, `max_output_tokens`, thinking billing |
| S-4 | https://ai.google.dev/gemini-api/docs/thought-signatures | — | Now only a redirect notice to S-3 ("This page has moved. Please see the Thinking guide.") |
| S-5 | https://ai.google.dev/gemini-api/docs/api-errors | not captured | Error codes and body (Interactions API) |
| S-6 | https://ai.google.dev/gemini-api/docs/rate-limits | not captured | Rate-limit dimensions, tiers, quota reset |
| S-7 | https://ai.google.dev/gemini-api/terms | 2026-04-28 (effective 2026-03-23) | Data use for unpaid and paid services; eligibility |
| S-8 | https://ai.google.dev/gemini-api/docs/pricing | 2026-10-22 | Pricing structure; free-tier availability per model |
| S-9 | https://ai.google.dev/gemini-api/docs/models | not captured | Model ids, status labels, naming and deprecation |
| S-10 | https://ai.google.dev/api/generate-content | not captured | Native `generateContent`: finish reasons, usage metadata, function call and response parts, thought signature |
| S-11 | https://ai.google.dev/gemini-api/docs/api-key | 2026-10-06 | API key header and handling |
| S-12 | https://ai.google.dev/api | 2026-09-04 | API overview: host, auth header, recommended endpoint |

## Contract facts (source-derived)

### C-1 Endpoint, version, method, authentication (Chat Completions compatibility)

| ID | Fact | Source |
|---|---|---|
| R-1 | Chat endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`; SDK base URL `https://generativelanguage.googleapis.com/v1beta/openai/`. The API version `v1beta` is in the path. | S-1 |
| R-2 | The HTTP method is not stated; the REST example is a `curl` with a `-d` JSON body (POST by inference). | S-1 |
| R-3 | Compatibility REST authentication: `Authorization: Bearer $GEMINI_API_KEY`. | S-1 |
| R-4 | Status: "Support for the OpenAI libraries is still in beta while we extend feature support." | S-1 |
| R-5 | The page documents chat completions, images, embeddings, batches and models endpoints. A Responses (`/responses`) endpoint is not documented. | S-1 |

### C-2 Request fields

| ID | Fact | Source |
|---|---|---|
| R-6 | Parameters shown in the examples: `model`, `messages`, `reasoning_effort`, `stream`, `stream_options.include_usage`, `tools` (objects with `type: "function"` and a `function` with `name`, `description` and JSON Schema `parameters`), `tool_choice: "auto"`, `response_format` (via the SDK's parse helper), `service_tier`, `n` (shown as `n=1`), and `extra_body`. | S-1 |
| R-7 | `extra_body.google` carries Gemini-specific settings, for example `thinking_config` (`thinking_level`, `include_thoughts`) and `cached_content`. | S-1 |
| R-8 | `max_tokens` / `max_completion_tokens`: **not stated**. Only for the image endpoint does the page say that parameters not listed "will be silently ignored by the compatibility layer". Whether unknown chat parameters are ignored or rejected is not stated. | S-1 |
| R-9 | `reasoning_effort` maps to Gemini thinking levels or budgets by model family. "If you want to disable thinking, you can set `reasoning_effort` to `"none"` for 2.5 models." "Reasoning cannot be turned off for Gemini 2.5 Pro or 3 models." `reasoning_effort` and `thinking_level`/`thinking_budget` "can't be used at the same time". | S-1 |
| R-10 | Function-calling modes (Interactions API): `auto` (default), `any`, `none`, `validated`; a subset of tools can be allowed by name. "Only a subset of the OpenAPI schema is supported." Best practice: "Keep active set to 10-20 tools maximum." | S-2 |

### C-3 Tool calls, results, continuation and opaque state

| ID | Fact | Source |
|---|---|---|
| R-11 | Chat Completions compatibility: the shape of `choices[].message.tool_calls`, and how a tool result is sent back (role, `tool_call_id`), are **not stated**. The examples only print the response. | S-1 |
| R-12 | "Gemini 3 supports OpenAI compatibility for thought signatures in chat completion APIs." The page refers to the thought-signatures page for the example. That page now only redirects to the Thinking guide (S-4), which does not mention the compatibility layer. **Where a signature appears in a Chat Completions message, and how it is sent back, is not documented in the retrieved pages.** | S-1, S-3, S-4 |
| R-13 | Thought signatures: "encrypted representations of the model's internal reasoning", "required to maintain reasoning continuity across multi-turn interactions". In stateless mode: "You MUST always resend all thought blocks exactly as they were received from the model" and "You should NOT remove or modify thought blocks from the history". Signatures are "Always present, even when the model performs minimal reasoning" (Interactions API thought steps). | S-3 |
| R-14 | Interactions API: the model returns `function_call` steps (`type`, `name`, `arguments`, read as `id` in examples); results are sent as `function_result` with `name`, `call_id`, `result`. Parallel calls: "The model supports calling multiple functions in a single turn"; multi-turn: "This process can be repeated over multiple turns." | S-2 |
| R-15 | Native `generateContent` parts: FunctionCall `id` ("Optional. Unique identifier of the function call."), `name` (required), `args` (JSON object); FunctionResponse `id` ("The identifier of the function call this response is for."), `name` (required), `response` (required, JSON object). `Part.thoughtSignature`: "Optional. An opaque signature for the thought so it can be reused in subsequent requests." | S-10 |
| R-16 | Native finish reason `MISSING_THOUGHT_SIGNATURE`: "Request has at least one thought signature missing." A request that omits a required signature therefore fails. | S-10 |

### C-4 Response envelope, finish reasons, safety, truncation

| ID | Fact | Source |
|---|---|---|
| R-17 | Chat Completions compatibility: `finish_reason` values and the response envelope are **not stated**. | S-1 |
| R-18 | Native finish reasons include `STOP` ("Natural stop point of the model or provided stop sequence."), `MAX_TOKENS`, `SAFETY`, `RECITATION`, `MALFORMED_FUNCTION_CALL` ("The function call generated by the model is invalid.") and `MISSING_THOUGHT_SIGNATURE`. The full enum was not captured. | S-10 |
| R-19 | Native prompt blocking: `promptFeedback.blockReason` ("If set, the prompt was blocked and no candidates are returned."), with values such as `SAFETY`, `OTHER`, `BLOCKLIST`, `PROHIBITED_CONTENT`. | S-10 |
| R-20 | Interactions API: generation-blocked errors such as `safety`, `recitation`, `prohibited_content`, `spii`, `blocklist`, `content_blocked`. | S-5 |
| R-21 | `max_output_tokens` "sets the maximum number of tokens a response can generate, including thought tokens", and "applies to the combined total of thinking tokens and output tokens". Reaching it during reasoning can leave the output truncated or empty. | S-3 |

### C-5 Usage and billing

| ID | Fact | Source |
|---|---|---|
| R-22 | Chat Completions compatibility: usage is available (`stream_options.include_usage` in streaming), but **field names are not stated**. | S-1 |
| R-23 | Native `usageMetadata`: `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, `toolUsePromptTokenCount`, `thoughtsTokenCount` ("Number of tokens of thoughts for thinking models."), and a total covering "prompt + tool-use prompt + thoughts + response candidates". | S-10 |
| R-24 | Billing: "When thinking is turned on, response pricing is the sum of output tokens and thinking tokens." Interactions API usage field: `total_thought_tokens`. Pricing tables label output prices "Output price (including thinking tokens)" for many models; some input prices vary by prompt length (for example ≤200k tokens) and modality. | S-3, S-8 |

### C-6 Authentication and key handling

| ID | Fact | Source |
|---|---|---|
| R-25 | Native and Interactions REST: "All requests to the Gemini API must include a `x-goog-api-key` header with your API key." The compatibility layer uses `Authorization: Bearer` (R-3). | S-11, S-12, S-1 |
| R-26 | "Every Gemini API key is associated with a Google Cloud project." "Never check API keys into source control systems like Git." Restricting keys is recommended. | S-11 |

### C-7 Errors, quota and retries

| ID | Fact | Source |
|---|---|---|
| R-27 | Interactions API errors: an `error` object with `code` (snake_case) and `message`. Codes include 400 `invalid_request`, 401 `authentication`, 402 `payment_required` ("Don't retry"), 403 `permission_denied`, 404 `not_found`/`model_not_found`, 429 `rate_limit_exceeded` (per-minute or per-second limits; retry with backoff), 429 `quota_exceeded` (daily quota), 500 `api_error`, 503 `service_unavailable` (retry with backoff), 504 `deadline_exceeded`. | S-5 |
| R-28 | Spend-based limits return "a `429 RESOURCE_EXHAUSTED` error". | S-6 |
| R-29 | The error format of the Chat Completions compatibility endpoint and of `generateContent` is **not stated** on the errors page. | S-5 |

### C-8 Data use, training and retention

| ID | Fact | Source |
|---|---|---|
| R-30 | Unpaid Services: Google uses submitted content and generated responses "to provide, improve" its products; "human reviewers may read, annotate, and process your API input and output"; "Do not submit sensitive, confidential, or personal information to the Unpaid Services." | S-7 |
| R-31 | Paid Services: prompts and responses are not used to improve products. Google "logs prompts and responses for a limited period of time, solely for detecting and preventing violations"; the duration is not stated; data "may be stored transiently or cached in any country". | S-7 |
| R-32 | Gemini API access is a Paid Service "only when accessing the API through a Cloud Project" with an active billing account (paraphrase); unpaid quota is an Unpaid Service. The pricing overview labels Free "Content used to improve our products" and Paid "Content **not** used to improve our products". | S-7, S-8 |
| R-33 | Eligibility: 18 or older; available regions only; for API clients made available to users in the EEA, Switzerland or the UK, only Paid Services may be used; services are for professional or business purposes. | S-7 |

### C-9 Models, availability, prices, quotas

| ID | Fact | Source |
|---|---|---|
| R-34 | Model ids and status labels are listed on S-9, for example a "Stable" Gemini 3 family, `gemini-3-flash-preview` ("Preview"), and the Gemini 2.5 family ("These models are not deprecated and will continue to be served until further notice"). Preview models "will be deprecated with at least 2 weeks notice". Per-model token limits and capabilities are not shown on that page. | S-9 |
| R-35 | The pricing page marks per model whether the free tier is "Free of charge" or "Not available", for example "Not available" for `gemini-3.1-pro-preview`. This is the published table, not a statement about any account's actual access. | S-8 |
| R-36 | Rate limits: RPM, TPM (input) and RPD; "Rate limits are applied per project, not per API key."; tiers Free, Tier 1 (billing linked), Tier 2, Tier 3; RPD resets "at midnight Pacific time"; "Specified rate limits are not guaranteed and actual capacity may vary." Per-model numbers are shown in AI Studio, not on this page. | S-6 |

## Gaps (not resolved by the retrieved documentation)

| ID | Gap | Consequence |
|---|---|---|
| G-1 | Chat Completions compatibility: the response envelope, `message.tool_calls` shape, tool-result message shape, `finish_reason` values and usage field names (R-11, R-17, R-22). Google points to OpenAI's libraries but does not state that its responses follow OpenAI's Chat Completions specification, and no OpenAI Chat Completions reference is recorded in this repository (the 2026-10-19 record covers Responses only). | A compatibility codec would have to assume these shapes. |
| G-2 | Where a thought signature travels in a Chat Completions message and how it must be sent back (R-12). The referenced example page now redirects. | Multi-turn tool calling with a model that emits signatures cannot be implemented faithfully over the compatibility layer; omitting a required signature fails (R-16). |
| G-3 | Whether models with thinking disabled (`reasoning_effort: "none"`, 2.5 models only, R-9) emit signatures. | Not established; cannot be assumed. |
| G-4 | The output-token parameter for the compatibility layer, and whether unknown chat parameters are ignored or rejected (R-8). | Our 2,048-token cap cannot be relied on over the compatibility layer without this. |
| G-5 | Native `generateContent`: the full request schema (contents and roles, tools and function declarations, tool config, `generationConfig.maxOutputTokens`, `thinkingConfig`), the full finish-reason enum, and its error body format. These parts of S-10 were not captured. | Needs a further retrieval of the native reference before a native codec. |
| G-6 | Interactions API: the full request and response schema (the pages show steps and examples, not a field-level reference). | Needs a further retrieval before an Interactions codec. |
| G-7 | Paid-service log retention duration (R-31); the owner's actual tier and settings. | Owner confirmation, not documentation. |
| G-8 | Per-model limits, free-tier availability for a given account, and current prices at run time. | Owner selection and confirmation (C-9). |

## Tracewise compatibility assessment (analysis; not contract)

**Reusable unchanged:** the provider boundary (`Provider.step`, `Message`, `ToolCallRequest`, `StepResponse`), the
vendor-neutral `HTTPProvider` (`http_adapter.py`; endpoint, auth header and codec are parameters), the guarded
transports and rules in `model_access.py` (exact endpoint, POST only, request cap, body cap, key-file rules,
`SecretCanary`) and the deadline backend in `deadline_http.py`. Product selection (`providers.py`) is unaffected.

**Needs a separate codec and harness:** the request/response mapping (`openai_responses.py` is Responses-specific),
the benchmark builder (`bench/model_provider.py` imports the OpenAI codec and endpoint directly and would need an
explicit API choice), and a separate smoke harness (`scripts/openai_smoke.py` fixtures and evidence shapes are
Responses-specific). `Provider.name` and `WireCodec.name` are typed `Literal["openai", "fake"]` and would need
`"gemini"`.

**Opaque thinking state:** the interface already has a per-assistant-turn opaque channel, `Message.replay`, which
`provider_view` passes through unredacted and which the OpenAI codec uses for reasoning items. A Gemini codec could
store the model's own turn content (for example native parts carrying `thoughtSignature`, R-15) in that channel and
re-emit it verbatim, refusing anything it did not produce. That fits without changing the interface, **provided the
contract says where the signature is and how it is returned**.

**Cannot be implemented safely from this evidence:**
- The **Chat Completions compatibility** route: the response, tool-call, tool-result, finish-reason and usage shapes
  (G-1), and the signature location (G-2), are undocumented. Gemini 3 models cannot turn reasoning off (R-9), and a
  missing signature fails the request (R-16). The only possibly signature-free route, 2.5 models with
  `reasoning_effort: "none"`, is itself unconfirmed (G-3) and still lacks G-1.
- The **native `generateContent`** route is better documented for tool calls and opaque state (R-15, R-16, R-18,
  R-23) and is the most promising, but its request schema and error format were not captured (G-5).
- The **Interactions API** route is the one Google recommends and documents thought handling most clearly (R-13,
  R-14), but its field-level schema was not captured (G-6).

**Recommendation for the owner:** before any implementation, choose the API surface (native `generateContent` or
Interactions) and authorise one further retrieval of that surface's field-level reference (request, response, errors,
usage), recorded here as an addendum. Do not implement the compatibility route on the current evidence.

**Cost:** no hard dollar ceiling is possible from this evidence. `max_output_tokens` includes thinking tokens on the
Interactions API (R-21), and thinking is billed as output (R-24); input tokens have no documented pre-send limit. Any
cost figure needs the chosen model's current prices and remains an estimate.

---

# Addendum A: native `generateContent` API (owner-authorised retrieval, 2026-10-26)

**Retrieved:** 2026-10-26, same method and limits as above (official `ai.google.dev` pages only; quotes about 125
characters at most; paraphrase marked). No API request, model call or key access. This addendum adds to the record
above and does not change it. Evidence ids are `N-`; gaps are `NG-`.

## Additional sources

| ID | URL | Last updated (as shown) | Used for |
|---|---|---|---|
| S-10 | https://ai.google.dev/api/generate-content | not captured | Method, request and response bodies, Candidate, FinishReason, UsageMetadata, Content, Part, FunctionCall, FunctionResponse |
| S-13 | https://ai.google.dev/api/caching | not captured | ToolConfig, FunctionCallingConfig and its Mode enum (the shared definitions appear here) |
| S-14 | https://ai.google.dev/gemini-api/docs/migrate-to-interactions | not captured | Status of `generateContent`; concept mapping to Interactions |
| S-15 | https://ai.google.dev/gemini-api/docs/troubleshooting | 2026-10-23 | Retry guidance; safety-block guidance |
| S-16 | https://ai.google.dev/gemini-api/docs/text-generation | not captured | Confirms the guides document the Interactions API |

Also used: S-3 (thinking), S-5 (errors), S-6 (rate limits), S-7 (terms), S-8 (pricing), S-9 (models), S-11 and
S-12 (authentication), from the record above.

## 1. Endpoint, method, authentication

| ID | Fact | Source |
|---|---|---|
| N-1 | Method and URL: "post `https://generativelanguage.googleapis.com/v1beta/{model=models/*}:generateContent`"; the path parameter `model` has the form `models/{model}`. | S-10 |
| N-2 | Authentication: "All requests to the Gemini API must include a `x-goog-api-key` header with your API key." No other required header is stated; the examples send a JSON body. | S-12, S-11 |
| N-3 | Status: "While `generateContent` remains fully supported, we recommend the Interactions API for all new development." No end-of-support date is stated. | S-14 |

## 2. Request schema

| ID | Fact | Source |
|---|---|---|
| N-4 | Request body: `contents[]` (Content; "Required. The content of the current conversation with the model."), `tools[]` (Tool), `toolConfig` (ToolConfig), `safetySettings[]`, `systemInstruction` (Content; paraphrase: text only), `generationConfig` (GenerationConfig), `cachedContent` (string, `cachedContents/{…}`). | S-10 |
| N-5 | Content: `parts[]` ("Ordered `Parts` that constitute a single message."); `role` ("Optional. The producer of the content. Must be either 'user' or 'model'."). Elsewhere the Tool section mentions a `Content.role` "function" generation context, which conflicts with the two-value rule (see NG-3). | S-10 |
| N-6 | Part fields include `text` ("Inline text."), `thought` ("Optional. Indicates if the part is thought from the model."), `thoughtSignature` ("Optional. An opaque signature for the thought so it can be reused in subsequent requests."), `functionCall` and `functionResponse`. | S-10 |
| N-7 | FunctionCall: `id` ("Optional. Unique identifier of the function call."), `name` ("Required. The name of the function to call."), `args` (JSON object). FunctionResponse: `id` ("The identifier of the function call this response is for."), `name` (required), `response` (required, JSON object), plus `parts[]`, `willContinue`, `scheduling`. | S-10 |
| N-8 | ToolConfig: `functionCallingConfig`; FunctionCallingConfig `mode`: "If unspecified, the default value will be set to AUTO."; `allowedFunctionNames[]` "should only be set when the Mode is ANY or VALIDATED". Modes: `AUTO` (call or text), `ANY` ("always predicting a function call only"), `NONE` ("Model will not predict any function call. Model behavior is same as when not passing any function declarations."), `VALIDATED` (constrained decoding of calls; paraphrase). | S-13 |
| N-9 | `GenerationConfig` is linked (`/api/generate-content#GenerationConfig`) but **no definition section exists in the retrieved text**. `maxOutputTokens`, `candidateCount`, `stopSequences` and `temperature` appear only in code samples. `thinkingConfig`, `thinkingBudget` and `thinkingLevel` do not appear on the page at all. | S-10 |
| N-10 | Gemini 4 and 3.6+ models "ignore custom values for `temperature`, `top_p`, and `top_k`" (Interactions guide). | S-16 |

## 3. Response schema, finish reasons, safety, truncation

| ID | Fact | Source |
|---|---|---|
| N-11 | GenerateContentResponse: `candidates[]`, `promptFeedback` ("Returns the prompt's feedback related to the content filters."), `usageMetadata` ("Output only."), `modelVersion`, `responseId`. | S-10 |
| N-12 | Candidate: `content` ("Output only. Generated content returned from the model."), `finishReason` ("Optional. Output only."), `finishMessage` ("populated only when `finishReason` is set"), `safetyRatings[]`, `citationMetadata`, `tokenCount`, `groundingMetadata`, `avgLogprobs`, `index`. | S-10 |
| N-13 | FinishReason values: `FINISH_REASON_UNSPECIFIED`, `STOP` ("Natural stop point of the model or provided stop sequence."), `MAX_TOKENS`, `SAFETY`, `RECITATION`, `LANGUAGE`, `OTHER`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `MALFORMED_FUNCTION_CALL`, `IMAGE_SAFETY`, `IMAGE_PROHIBITED_CONTENT`, `IMAGE_OTHER`, `NO_IMAGE`, `IMAGE_RECITATION`, `UNEXPECTED_TOOL_CALL` (a tool call with no tools enabled), `TOO_MANY_TOOL_CALLS`, `MISSING_THOUGHT_SIGNATURE` (a signature missing from the request), `MALFORMED_RESPONSE`, `ESCALATION`, `PUP_LIMITED_DISABLED`, `CONTINUATION` (stopped at a per-request limit; resumable with a continuation token; `maxOutputTokens` "cumulative across continuation hops"). | S-10 |
| N-14 | Prompt blocking: `promptFeedback.blockReason` ("If set, the prompt was blocked and no candidates are returned."), values including `SAFETY`, `OTHER`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `IMAGE_SAFETY`. For `OTHER`, "the query or response may violate the terms of service". | S-10, S-15 |

## 4. Thought signatures in `generateContent`

| ID | Fact | Source |
|---|---|---|
| N-15 | "In the generateContent API, there are no dedicated thought blocks." Signatures "are metadata that can be attached to any part", "such as living inside functionCall parts or the final part of a response". | S-3 |
| N-16 | General rule (stated for stateless history): "You MUST always resend all thought blocks exactly as they were received from the model" and "You should NOT remove or modify thought blocks from the history". | S-3 |
| N-17 | A request missing a required signature ends with `MISSING_THOUGHT_SIGNATURE` (N-13). | S-10 |
| N-18 | **Not documented** in the retrieved pages: which parts must carry a signature, whether a signature on a text part may be dropped, which call carries it when several calls are made in parallel, and what exactly is validated. The page that used to cover this now redirects (S-4). | S-3, S-4 |

## 5. Submitting tool results and continuing

| ID | Fact | Source |
|---|---|---|
| N-19 | A FunctionResponse part carries the call's `id`, `name` and a JSON `response` (N-7). The conversation continues by sending the full `contents[]` history again (`generateContent` is stateless: there is no server-side session in its schema). | S-10 (inference for statelessness from the schema) |
| N-20 | **Not documented:** the `role` of the Content that carries function responses (`user` is the only non-model value allowed by N-5, but see the "function" mention), and whether a turn must contain one response per call, in order. | S-10 |

## 6. Output-token settings

| ID | Fact | Source |
|---|---|---|
| N-21 | `maxOutputTokens` is shown only in code samples (N-9). Its definition, default, and whether it includes thinking tokens are **not documented for `generateContent`** in the retrieved text. For the Interactions API, `max_output_tokens` includes thought tokens (R-21). | S-10, S-3 |
| N-22 | How to set or disable thinking in `generateContent` (`thinkingConfig`) is **not documented** in the retrieved text. The compatibility page maps `reasoning_effort` to thinking levels and budgets (R-9), but that is a different surface. | S-10, S-1 |

## 7. Usage metadata and billing

| ID | Fact | Source |
|---|---|---|
| N-23 | UsageMetadata fields: `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, `toolUsePromptTokenCount`, `thoughtsTokenCount` ("Number of tokens of thoughts for thinking models."), `totalTokenCount` (covering "prompt + tool-use prompt + thoughts + response candidates"), per-modality details, and `serviceTier`. | S-10 |
| N-24 | Billing (general): "When thinking is turned on, response pricing is the sum of output tokens and thinking tokens." The pricing tables say "Output price (including thinking tokens)" for many models. How usage fields map to a bill is not stated beyond this. | S-3, S-8 |

## 8. Errors, rate limits, retries

| ID | Fact | Source |
|---|---|---|
| N-25 | The API errors page documents the **Interactions API** error object (`error.code` snake_case, `error.message`; R-27). The error body format of `generateContent` is **not documented** in the retrieved pages; the troubleshooting page defers to the errors page. | S-5, S-15 |
| N-26 | Retry guidance: "Only retry on transient errors (like 429, 408, or 5xx)", not on 400, 402 or 403; exponential backoff with jitter and a maximum number of retries. | S-15 |
| N-27 | Rate limits are per project, with RPM, TPM (input) and RPD, and are "not guaranteed" (R-36). | S-6 |

## 9 and 10. Models, prices, data use

Unchanged from the record above (R-30 to R-36): model ids and prices are source-dated facts from S-8 and S-9; free-tier
use may improve Google's products with human review, paid use is not used for that and is logged for a limited,
unstated time; these are published policy, not the owner's account settings.

## Gaps (native API)

| ID | Gap | Consequence |
|---|---|---|
| NG-1 | `GenerationConfig` and `ThinkingConfig` field definitions: `maxOutputTokens` semantics and default (including whether thinking tokens count), `candidateCount` default, how to set or disable thinking (N-9, N-21, N-22). | The 2,048-token output cap and a single-candidate response cannot be relied on from documentation. |
| NG-2 | Thought-signature placement and validation rules for `generateContent`, especially for parallel calls (N-18). | Only verbatim replay of the model's own content is defensible (see the assessment). |
| NG-3 | The role of the content that carries function responses, and the "function" role mention (N-5, N-20). | Encoding of tool results would rest on an assumption. |
| NG-4 | `FunctionCall.id` is optional (N-7): pairing when the model omits it, especially for two parallel calls with the same name. | A codec must fail closed when ids are missing or ambiguous. |
| NG-5 | The `generateContent` error body format and quota-versus-rate-limit distinction (N-25). | Errors could only be classified by HTTP status. |
| NG-6 | Real response shapes and frequencies (signatures present, ids present, `MISSING_THOUGHT_SIGNATURE` behaviour). | Needs an authorised live observation, as for OpenAI (G-4). |

## Tracewise compatibility assessment (native API; analysis, not contract)

**Mapping onto the current abstraction** (`investigate/provider.py`, `http_adapter.py`):
- System messages → `systemInstruction`; user messages → `Content(role="user", parts=[{text}])` (N-4, N-5).
- An assistant turn with tool calls → the model's own `Content` replayed (below); `ToolCallRequest(id, name,
  arguments)` from each `functionCall` part, with `args` serialised as a JSON string for the loop's validator.
- Tool results → `functionResponse` parts with the call's `id` and `name` and a JSON object `response` wrapping the
  tool text (the shape of `response` is ours; NG-3 for the role).
- The tool-free final step → keep `tools` and set `toolConfig.functionCallingConfig.mode = NONE`, which is
  documented (N-8). This is better than omitting `tools`, which can yield `UNEXPECTED_TOOL_CALL` (N-13).
- Decode: exactly one candidate, else fail closed; `finishReason` `STOP` accepted; every other value (including
  `MAX_TOKENS`, `SAFETY`, `MALFORMED_FUNCTION_CALL`, `MISSING_THOUGHT_SIGNATURE`, `CONTINUATION`) fails closed;
  `promptFeedback.blockReason` fails closed; `usageMetadata` required (`promptTokenCount`,
  `candidatesTokenCount`; `thoughtsTokenCount` recorded when present); `thought: true` parts are never treated as
  answer text.
- Reusable unchanged: `HTTPProvider`, `EndpointBudgetTransport`, `RequestDeadlineTransport` and the deadline
  backend, key-file rules, `SecretCanary`. One difference: the endpoint embeds the model id
  (`…/models/{model}:generateContent`), so the codec's exact endpoint is fixed per run from the explicit model id,
  and the host lock still compares the whole URL.

**Opaque state, the key question.** Because signatures "can be attached to any part" (N-15) and placement rules are
undocumented (NG-2), the only faithful approach is to keep the model's entire returned `Content` verbatim and send it
back unchanged as that turn. `Message.replay` can carry it with no change to the `Provider` interface. Two
consequences need an owner decision:
1. **Redaction exception.** Today `Message.replay` is the one channel that skips P-2 redaction, and it is limited to
   opaque OpenAI reasoning items. A verbatim Gemini `Content` also holds model-written text and `functionCall` args.
   They can only reflect input that was already redacted, but redacting them on replay would alter content tied to a
   signature. Widening the unredacted channel to "the provider's own returned content, replayed unchanged" is a
   security-policy change, not a code detail.
2. **Consistency check.** The codec must refuse (fail closed) any replay it did not produce, and any replay whose
   `functionCall` parts do not exactly match the turn's `tool_calls` (ids, names and args), so the loop's validated
   view and the replayed bytes cannot diverge.

**Verdict:** the native API is a **viable basis for a future offline adapter, but not yet implementable** without
assumptions. Before implementation:
- one more retrieval for NG-1 (`GenerationConfig`/`ThinkingConfig` definitions) and, if available, NG-3 and NG-5;
- an owner decision on the replay-redaction exception above;
- an explicit rule, failing closed, for NG-4 (missing or duplicate call ids).

NG-2 and NG-6 can only be settled by an authorised live observation. Until then, verbatim replay plus fail-closed
handling of `MISSING_THOUGHT_SIGNATURE` is the safe design. The Chat Completions compatibility route stays blocked
(G-1, G-2). The Interactions API is Google's recommendation (N-3) and may document thought handling more completely
(R-13, R-14), but its field-level schema is still unrecorded (G-6).

**Cost:** unchanged. No hard dollar ceiling; `maxOutputTokens` semantics for `generateContent` are undocumented
(NG-1); thinking is billed as output (N-24).

---

# Addendum B: output limits and confirmations (owner-authorised retrieval, 2026-10-26)

Same method and limits as above (official `ai.google.dev` pages only; short quotes; no API call or key). This
addendum adds facts and narrows NG-1; it does not change any entry above.

| ID | URL | Last updated (as shown) | Used for |
|---|---|---|---|
| S-17 | https://ai.google.dev/api/models | 2026-09-23 | Model resource: token limits, thinking support |
| S-18 | https://ai.google.dev/gemini-api/docs/tokens | 2026-10-13 | Token counting and output budgets (Interactions API) |

| ID | Fact | Source |
|---|---|---|
| N-28 | Model resource: `inputTokenLimit` ("Maximum number of input tokens allowed for this model."), `outputTokenLimit` ("Maximum number of output tokens available for this model."), `thinking` ("Whether the model supports thinking."). These are per-model values, read through `models.get`. | S-17 |
| N-29 | Output budgets (stated on the Interactions-oriented token guide): Gemini 3 and 2.5 "Use separate input (`1,048,576` tokens) and output (`65,536` tokens) budgets"; Gemini 4 synchronous responses are capped at `65,536` output tokens by default. These are model-family limits, not the default value of `maxOutputTokens` when it is unset. | S-18 |
| N-30 | Re-read on 2026-10-26, unchanged: `FunctionCall.id` is optional (N-7); signatures in `generateContent` can sit "inside functionCall parts or the final part of a response" (N-15); `toolUsePromptTokenCount` is "Number of tokens present in tool-use prompt(s)", `thoughtsTokenCount` "Number of tokens of thoughts for thinking models", `candidatesTokenCount` "Total number of tokens across all the generated response candidates" (N-23). | S-10, S-3 |

**NG-1, narrowed:** per-model output limits are documented (N-28, N-29). Still **not documented** for
`generateContent`: a definition of `maxOutputTokens`, its default when unset, and whether it includes thinking
tokens on this API. Whether a signature on a final text part is required on replay is still **not documented** (NG-2).

---

# Addendum C: function declaration schema (owner-authorised retrieval, 2026-10-30)

Same method and limits as above (official `ai.google.dev` only; no API call or key). Adds facts; changes no entry above.

| ID | Fact | Source |
|---|---|---|
| N-31 | FunctionDeclaration `parameters`: "Optional. Describes the parameters to this function. Reflects the Open API 3.03 Parameter Object". `parametersJsonSchema`: "Optional. Describes the parameters to the function in JSON Schema format." and "This field is mutually exclusive with `parameters`." | S-10 |
| N-32 | The Schema object (the type of `parameters`) lists: type, format, title, description, nullable, enum, maxItems, minItems, properties, required, minProperties, maxProperties, minLength, maxLength, pattern, example, anyOf, propertyOrdering, default, items, minimum, maximum. `additionalProperties` is not among them. Type values are upper case (`STRING`, `OBJECT`, …). | S-10 |

**Consequence for Tracewise:** the investigator's tool specs are JSON Schema (`additionalProperties: false`,
lower-case types), so they belong in `parametersJsonSchema`, not `parameters`. The codec was corrected on 2026-10-30.
Whether every JSON Schema keyword the specs use (`maxLength`, `minimum`) is honoured by the server is not stated and
needs live observation.
