# DeepSeek API reference: recorded contract (retrieval, 2026-11-01)

**Retrieved:** 2026-11-01, by an automated fetch of official public pages only (`api-docs.deepseek.com`, and the
DeepSeek terms and privacy policy on `cdn.deepseek.com`). No API key was used, no request was made to
`api.deepseek.com`, no model call was made, and no credentials were read.

**How the pages were read:** each page was fetched and summarised by a fetch tool asked for short verbatim excerpts.
Quotes are kept under 15 words; everything else is paraphrase and marked "(paraphrase)" where it restates prose.
Field names, enum values and numbers are structural facts. Before any code relies on a fact, re-read the cited page.
No page showed a "last updated" date; the docs pages carry only a 2026 copyright footer.

**Important drift from earlier assumptions:** the current model ids are `deepseek-flash` and `deepseek-v4-pro`.
`deepseek-chat` and `deepseek-reasoner` were scheduled for discontinuation on 2026-07-24 (D-6).

## Sources

| ID | URL | Last updated (as shown) | Used for |
|---|---|---|---|
| S-1 | https://api-docs.deepseek.com/ | not shown | Base URLs, auth header, model names, legacy names, Anthropic endpoint |
| S-2 | https://api-docs.deepseek.com/quick_start/pricing | not shown | Models and versions, thinking modes, context, max output, features, prices |
| S-3 | https://api-docs.deepseek.com/api/create-chat-completion | not shown | Chat completions request and response schema, finish reasons, usage |
| S-4 | https://api-docs.deepseek.com/guides/thinking_mode | not shown | Enabling thinking, unsupported parameters, `reasoning_content` multi-turn rule |
| S-5 | https://api-docs.deepseek.com/guides/tool_calls | not shown | Tool-call round trip, tool message, strict mode (beta) and supported schema keywords |
| S-6 | https://api-docs.deepseek.com/quick_start/error_codes | not shown | HTTP status codes, causes, remedies |
| S-7 | https://api-docs.deepseek.com/quick_start/rate_limit | not shown | Concurrency limits, keep-alive behaviour, 10-minute close, 429 |
| S-8 | https://api-docs.deepseek.com/guides/anthropic_api | not shown | Anthropic-compatible endpoint (note only) |
| S-9 | https://api-docs.deepseek.com/updates | entries to 2026-10-17 | Model change log, legacy-name retirement |
| S-10 | https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html | released 2026-04-22, effective 2026-04-29 | Operator, governing law, rights in inputs/outputs |
| S-11 | https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html | 2026-02-10 | Storage location, retention, training use, scope |

## Contract facts (source-derived)

### D-A Endpoint, method, authentication

| ID | Fact | Source |
|---|---|---|
| D-1 | OpenAI-format base URL `https://api.deepseek.com`; chat endpoint `POST /chat/completions`. | S-1, S-3 |
| D-2 | Auth: `Authorization: Bearer ${DEEPSEEK_API_KEY}` (curl example). | S-1 |
| D-3 | Beta base URL `https://api.deepseek.com/beta` is required for strict tool mode and for Chat Prefix Completion (`prefix: true`). | S-3, S-5 |
| D-4 | The API version is not in the path; no version header is documented. | S-1, S-3 |

### D-B Models

| ID | Fact | Source |
|---|---|---|
| D-5 | `model` enum: `deepseek-flash` (served by DeepSeek-V4.1-Flash-1017) and `deepseek-v4-pro` (DeepSeek-V4-Pro-0813). Both support non-thinking and thinking mode, and thinking is the default. Context length 1M; maximum output 384K. Tool calls, JSON output, Responses API and Anthropic API are supported on both; vision only on `deepseek-flash`. | S-2, S-3 |
| D-6 | Legacy names `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are still accepted, but the models behind them were retired. They route to V4.1-Flash-1017 at Flash prices. Change log 2026-04-24 (paraphrase): `deepseek-chat` / `deepseek-reasoner` to be discontinued on 2026-07-24, mapped meanwhile to V4-Flash non-thinking / thinking. | S-1, S-9 |
| D-7 | The model behind `deepseek-flash` changes without a name change (2026-10-17 upgrade to V4.1-Flash-1017; "API call method and pricing" unchanged, paraphrase). | S-9 |
| D-8 | Concurrency limit per account (not per key): 2,500 for `deepseek-flash`, 500 for `deepseek-v4-pro`. | S-2, S-7 |
| D-9 | Prices are per 1M tokens, split into input cache hit, input cache miss and output. Peak rates (weekday UTC windows 01:00–04:00 and 06:00–10:00) are double the off-peak rates. | S-2 |

### D-C Request

| ID | Fact | Source |
|---|---|---|
| D-10 | Thinking switch: `thinking: {"type": "enabled" \| "disabled"}`, which overrides `reasoning_effort` (`none`, `low`, `high`, `max`; `none` disables; default `high`). With both omitted, thinking is **enabled**. `minimal` maps to `low`; `medium` and `xhigh` map to `high`. With the OpenAI SDK, `thinking` goes in `extra_body`. | S-3, S-4 |
| D-11 | Message roles: `system` (`content` string), `user` (string or content-part array), `assistant` (`content` nullable string, required; optional `name`; beta `prefix`; beta `reasoning_content`), `tool` (`content` string or part array; `tool_call_id` required). | S-3 |
| D-12 | On the schema page, assistant `reasoning_content` is described only for Chat Prefix Completion (paraphrase; requires `prefix: true`). The replay rule for tool use is on the thinking guide (D-24). | S-3, S-4 |
| D-13 | `tools`: only `type: "function"`; names unique; `function.name` letters, digits, `_`, `-`, max 128 chars; `description`; `parameters` is a JSON Schema object (omitted = no parameters); `function.strict` boolean, default false, beta. | S-3 |
| D-14 | Strict mode (beta): beta base URL (D-3), `strict: true` on every function; the server validates the schema and errors on invalid or unsupported types. Supported in thinking and non-thinking mode. Types: object, string, number, integer, boolean, array, enum, anyOf, plus `$ref`/`$def`. Objects: all properties in `required`, `additionalProperties: false`. Strings: `pattern`, `format` (email, hostname, ipv4, ipv6, uuid); not `minLength`/`maxLength`. Numbers: `const`, `default`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`. Arrays: not `minItems`/`maxItems`. | S-5 |
| D-15 | `tool_choice`: `"none"`, `"auto"`, `"required"`, or `{"type": "function", "function": {"name": …}}`. Default `none` without tools, `auto` with tools. | S-3 |
| D-16 | Thinking mode: "`required` and named tool choices are not supported in thinking mode"; "Disable thinking mode first to use them." Paraphrase: they return 400. `none` and `auto` are not restricted. | S-3 |
| D-17 | `parallel_tool_calls` does not appear on the schema page or the tool-calls guide; the guide example reads only `tool_calls[0]`. | S-3, S-5 |
| D-18 | `max_tokens`: "The maximum number of tokens that can be generated in the chat completion." Range 1–393216; defaults 8K non-thinking, 64K thinking, 128K with `reasoning_effort: max`; input plus output limited by context length. Whether reasoning tokens count toward it is **not stated** (default rises with thinking, which suggests but does not establish it). | S-3, S-4 |
| D-19 | Thinking mode ignores `temperature`, `presence_penalty`, `frequency_penalty` (no error, paraphrase). `top_p` handling is per model and mode; e.g. `deepseek-v4-pro` thinking fixes it at 0.95 with tool calling. `frequency_penalty`/`presence_penalty` are deprecated and ignored generally. | S-3, S-4 |
| D-20 | Other fields: `response_format` (`text` / `json_object`), `stop` (up to 16), `stream`, `stream_options.include_usage` (400 without `stream: true`), `logprobs`, `top_logprobs` (0–20), `user_id` (ASCII id ≤512 bytes; used for safety review and cache/scheduling isolation; no personal data). | S-3 |
| D-21 | Chat Completions accepts inserted `system` messages mid-conversation but not inserted tool calls (paraphrase). | S-5 |

### D-D Response

| ID | Fact | Source |
|---|---|---|
| D-22 | Envelope: `id`, `object: "chat.completion"`, `created`, `model`, `system_fingerprint`, `choices[]`, `usage`. `choices[]`: `index`, `finish_reason`, `logprobs`, `message`. `message`: `role: "assistant"`, `content` (nullable), `reasoning_content` (nullable, thinking mode only, produced before the answer), `tool_calls[]`. | S-3 |
| D-23 | `tool_calls[]`: `id`, `type: "function"`, `function.name`, `function.arguments` as a **JSON string**; "the model does not always generate valid JSON" and may add parameters outside the schema, so validate (paraphrase). | S-3 |
| D-24 | `finish_reason` enum: `stop` (natural stop or stop sequence), `length` (`max_tokens` or context limit), `content_filter` (content omitted by filters), `tool_calls`, `insufficient_system_resource` (interrupted by inference resource limits), `aborted` (generation interrupted). All paraphrase except the values. | S-3 |
| D-25 | Streaming: SSE `chat.completion.chunk`; `delta.reasoning_content`; tool-call fragments keyed by `index` (first carries `id`, `type`, `function`; later only argument text); ends with `data: [DONE]`. | S-3 |

### D-E Multi-turn rules (thinking mode, tool results)

| ID | Fact | Source |
|---|---|---|
| D-26 | Requests **with `tools`**: earlier turns' `reasoning_content` "must be fully passed back to the API in all subsequent requests." Paraphrase: this covers every earlier assistant turn, including turns without a tool call and turns from earlier user questions; the sample keeps turn-1 reasoning in turn 2. | S-4 |
| D-27 | Omitting it on a request that carries `tools` causes HTTP 400 (paraphrase). Including it is not stated to be an error. | S-4 |
| D-28 | Requests **without `tools`**: `reasoning_content` "does not need to be passed back"; if sent it is "ignored" and not concatenated into the context. | S-4 |
| D-29 | Tool results: append the assistant message (with its `tool_calls`), then one message per call with `role: "tool"`, the matching `tool_call_id` and the result as `content`. "The model itself does not execute specific functions." | S-5, S-3 |
| D-30 | Tool use in thinking mode is supported (from DeepSeek-V3.2 on, paraphrase); the model may reason and call tools over several sub-turns before answering. | S-4, S-5 |

### D-F Usage

| ID | Fact | Source |
|---|---|---|
| D-31 | `usage`: `prompt_tokens` (= `prompt_cache_hit_tokens` + `prompt_cache_miss_tokens`), `prompt_tokens_details.cached_tokens` (= `prompt_cache_hit_tokens`), `completion_tokens`, `total_tokens` (= prompt + completion), `completion_tokens_details.reasoning_tokens`. | S-3 |
| D-32 | Whether `completion_tokens` **includes** `reasoning_tokens` is not stated. Billing distinguishes only input hit/miss and output; reasoning is not priced separately (paraphrase of S-2 table). | S-3, S-2 |
| D-33 | Streaming with `include_usage`: `usage` null on earlier chunks, full on the last content chunk. | S-3 |

### D-G Errors and rate limiting

| ID | Fact | Source |
|---|---|---|
| D-34 | 400 Invalid Format ("Invalid request body format."); 401 Authentication Fails ("…due to the wrong API key."); 402 Insufficient Balance ("You have run out of balance."; top up); 422 Invalid Parameters ("Your request contains invalid parameters."); 429 Rate Limit Reached (too fast, or a concurrency or QPS limit exceeded; pace requests); 500 Server Error (retry after a brief wait, contact if persistent); 503 Server Overloaded (retry after a brief wait). | S-6 |
| D-35 | Exceeding the concurrency limit yields HTTP 429; a per-`user_id` limit (raised-quota accounts only) yields 429 for that `user_id` only. A request occupies a slot until the response completes (paraphrase). | S-7 |
| D-36 | While waiting, non-streaming responses receive continuous empty lines; streaming responses receive SSE `: keep-alive` comments. Raw-HTTP parsers must handle them (paraphrase). | S-7 |
| D-37 | If inference has not started after 10 minutes, "the server will close the connection." | S-7 |
| D-38 | No error response body schema (error object fields) is documented. No `Retry-After` header is documented. | S-3, S-6 |

### D-H Terms, data location, retention, training

| ID | Fact | Source |
|---|---|---|
| D-39 | Operator: Hangzhou DeepSeek Artificial Intelligence Co., Ltd. (PRC). Terms "governed by the laws of the People's Republic of China in the mainland"; disputes go to a court at DeepSeek's registered office after negotiation (paraphrase). | S-10 |
| D-40 | The Terms assign output rights to the user ("We assign any rights, title, and interests—if any—in the Outputs."). They do not state whether DeepSeek trains on API content, nor data location or retention (paraphrase); suspected-illegal-activity records are retained (§7.2). Export-control clause bars sanctioned countries and parties. | S-10 |
| D-41 | Privacy policy: "we directly collect, process and store your Personal Data in People's Republic of China." User Input is used to "train and improve our technology"; an opt-out right exists, via request to the privacy contact (paraphrase); no API-side toggle is described. Retention: as long as needed for the Services; input data while the account exists (paraphrase). | S-11 |
| D-42 | Scope (paraphrase): the policy covers the open platform's paid services, but excludes personal data of end users of developers' downstream apps, for which the developer is controller. How the training clause applies to API prompts specifically is not stated separately. | S-11 |

### D-I Anthropic-compatible endpoint (note only)

| ID | Fact | Source |
|---|---|---|
| D-43 | Exists at `https://api.deepseek.com/anthropic`; accepts `x-api-key` or `Authorization: Bearer`; `anthropic-version` ignored; `claude-opus*` maps to `deepseek-v4-pro`, other `claude*` to `deepseek-flash`. Thinking-mode tool continuation requires the full assistant `content` array including thinking blocks; signatures are not mentioned; `redacted_thinking` unsupported; `tool_choice` `any` behaves as `auto`. | S-8 |

## Gaps (not resolved by official documentation)

| ID | Gap | Consequence |
|---|---|---|
| DG-1 | Whether `max_tokens` includes reasoning tokens (D-18). | Our output cap cannot be assumed to bound total generation in thinking mode. |
| DG-2 | Whether `completion_tokens` includes `reasoning_tokens` (D-32). | Usage mapping must not double-count; record both raw fields. |
| DG-3 | Error body shape and `Retry-After` (D-38). | Classify by HTTP status only; do not parse bodies. |
| DG-4 | Parallel tool calls: no `parallel_tool_calls` parameter and no statement whether several calls can be returned (D-17); the schema allows an array. | Codec must handle 0..n calls and cannot disable parallelism. |
| DG-5 | Whether including `reasoning_content` on earlier turns is ever rejected; the schema page documents the field only for prefix completion (D-12, D-27). | Rely on S-4 guide; confirm in a guarded live smoke before shipping. |
| DG-6 | DeepSeek's own training use and retention of **API** content specifically (D-40, D-42); the privacy policy's training clause and PRC storage are the only statements. | Owner policy decision (data location, O-5) before any use. |
| DG-7 | Whether `tool_choice: "none"` with tools present keeps the tools-present `reasoning_content` replay rule (logically yes, since `tools` is present; not stated). | Replay on every turn whenever `tools` is sent. |
| DG-8 | API version stability guarantees; the model behind `deepseek-flash` changes silently (D-7). | Record `model` and `system_fingerprint` per run. |
| DG-9 | No page shows a last-updated date (except the change log, terms and privacy policy). | Re-fetch before implementation. |
