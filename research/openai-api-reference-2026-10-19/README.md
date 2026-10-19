# OpenAI API reference: recorded contract (owner-authorised retrieval, 2026-10-19)

**Retrieved:** 2026-10-19, by an automated fetch of official OpenAI documentation pages only. No API key was used and no API request was made. Only short quotes are reproduced; the rest are field names and structural facts.

`platform.openai.com/docs/api-reference/chat/create` returned **HTTP 403** to the fetch. The OpenAI developer site (`developers.openai.com`) served the pages below. Its API overview links the **Responses** API reference, not Chat Completions, so the Responses API was recorded and implemented (C-1).

## Sources

| ID | URL | Used for |
|---|---|---|
| S-1 | https://developers.openai.com/api/reference | API overview |
| S-2 | https://developers.openai.com/api/reference/resources/responses/methods/create | Responses create: request, response, example |
| S-3 | https://developers.openai.com/api/docs/guides/function-calling | Tool declaration, call and output pairing |
| S-4 | https://developers.openai.com/api/docs/guides/error-codes | Error causes; retry guidance |
| S-5 | https://developers.openai.com/api/docs/guides/rate-limits | Rate-limit headers; `Retry-After` |
| S-6 | https://developers.openai.com/api/docs/guides/reasoning | Reasoning items; stateless mode; incomplete responses |

API version: no version string is stated on these pages. The path is `/v1/responses`.

## Contract facts (source-derived)

| ID | Fact | Source |
|---|---|---|
| R-1 | `POST https://api.openai.com/v1/responses` (the path `post /responses` in the reference; the host from the official curl example) | S-2 |
| R-2 | Authentication: `Authorization: Bearer $OPENAI_API_KEY` (curl example) | S-2 |
| R-3 | Request fields: `model` (string); `instructions` ("A system (or developer) message inserted into the model's context"); `input` (string or array of items); `tools`; `tool_choice`; `max_output_tokens` ("An upper bound for the number of tokens…"); `parallel_tool_calls`; `store` (boolean; "Defaults to true when omitted"); `text.format` (`text`, `json_schema` with `name`/`schema`/`strict`, `json_object`); `temperature`; `truncation` (`auto` / `disabled`; default `disabled`, and input over the context window gives a 400); `previous_response_id` | S-2 |
| R-4 | Input message items: role `user`, `assistant`, `system` or `developer`; `content` is a string or a list of content parts; `type` is optionally `"message"` | S-2 |
| R-5 | `function_call` item: `call_id`, `name`, `arguments` ("A JSON string of the arguments"), `type: "function_call"`; output items may also carry an `id` | S-2, S-3 |
| R-6 | `function_call_output` item: `type`, `call_id`, `output` (a string, or an array of content parts); each call's output is matched by `call_id` | S-2, S-3 |
| R-7 | Function tool: `type: "function"`, `name`, `description` (optional), `parameters` (JSON Schema), `strict` | S-2, S-3 |
| R-8 | Strict mode needs `additionalProperties: false` and **every property listed as required** | S-3 |
| R-9 | `tool_choice`: `"none"`, `"auto"`, `"required"`, or object forms (forced function and others) | S-2, S-3 |
| R-10 | Reasoning items should be passed back with function-call outputs ("pass back all reasoning items, function call items, and function call output items"). In stateless mode (`store: false` or ZDR), reasoning items carry `encrypted_content` by default; `include: ["reasoning.encrypted_content"]` is legacy and accepted but no longer required. | S-6 |
| R-11 | Response: `object: "response"`; `status` ∈ {`completed`, `failed`, `in_progress`, `cancelled`, `queued`, `incomplete`}; `output` is an array of items. `message` items have content parts `output_text` (`text`) or `refusal` (`refusal`). `function_call` and `reasoning` items also appear. `usage`: `input_tokens`, `output_tokens`, `total_tokens`, `input_tokens_details.cached_tokens`, `output_tokens_details.reasoning_tokens`. The example also shows `error` and `incomplete_details` (both null). `output_text` is an SDK-only convenience, not an API field. | S-2 |
| R-12 | Error causes: 401 (authentication, wrong key, IP not allowed); 403 (unsupported region); 429 is either a **rate limit** or **quota/billing** (`credit_balance_exhausted`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`, `organization_usage_limit_exceeded`; `error.type` such as `insufficient_quota`). "Retrying billing, spend, or quota errors won't restore API access." 500 server error; 503 `server_is_overloaded`. The body fields referenced are `error.code`, `error.type`, `error.param`. | S-4 |
| R-13 | An incomplete response is reported with `incomplete_details.reason`. `max_output_tokens` is named explicitly. A content-filter case appears in an example; the full list of values is **not** published. | S-6 |
| R-14 | `Retry-After` (seconds) "when present" on temporary 429 and 503; otherwise exponential backoff with jitter and limited retries. Rate-limit headers: `x-ratelimit-{limit,remaining,reset}-{requests,tokens}`, with reset values shown only as examples (`1s`, `6m0s`). | S-4, S-5 |

## Integration decisions (ours, not from the documentation)

- `store: false`, for data minimisation; replay is stateless (R-10).
- `strict: false` on tools, because our tool specs have optional fields (R-8).
- A model refusal fails closed (`WireError`) and is never published as a diagnosis.
- Any `status` other than `completed` fails closed.
- Missing `usage` fails closed; usage is never invented.
- No `text.format`: the investigator validates JSON itself (`json_schema` is available as a later improvement).
- `max_output_tokens` is set to the investigator's character cap, as a generous upper bound. The adapter enforces the character cap on the decoded text in any case.

## Gaps (not resolved by the documentation)

| ID | Gap | Handling |
|---|---|---|
| G-1 | The full list of `incomplete_details.reason` values | Any non-`completed` status fails closed |
| G-2 | No JSON example of the error body (only field names) | Classification reads `error.code` and `error.type` tolerantly; an unknown body is treated as retryable 429/5xx, within bounded retries |
| G-3 | Whether reasoning items may be omitted for non-reasoning models | Always passed back when present; none appear for non-reasoning models |
| G-4 | Reachability, real response shapes, and actual refusal/truncation frequency | Need one authorised smoke call (T-605) |
| G-5 | Maximum `call_id` length | **Corrected in Phase 46:** the earlier 64-character cap was not in the contract and could merge two distinct ids. Ids are now sent back exactly as issued; a duplicate, missing or unpaired id fails closed. A provider-side length limit, if any, would show up in the smoke call. |
| G-6 | Model identifier, context and output limits, prices | T-605 / UD-3 / C-9 (owner) |
| G-7 | (Phase 46) Whether a request may contain earlier `function_call` items while `tools` is omitted (our final, tool-free step). R-9 documents `tool_choice: "none"` as the alternative. | Undocumented either way; to be observed in the smoke call |
| G-8 | (Phase 46) R-10 says reasoning items carry `encrypted_content` "by default" in stateless mode | A reasoning item without it fails closed; the smoke call confirms this is not over-strict |
