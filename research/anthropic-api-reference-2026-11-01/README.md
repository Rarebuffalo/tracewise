# Anthropic Messages API reference: recorded contract (retrieval, 2026-11-01)

**Retrieved:** 2026-11-01, by fetching official Anthropic documentation pages only (`platform.claude.com/docs`; links
from `docs.anthropic.com` resolve there). No API key was used, no request was sent to `api.anthropic.com`, no model
call was made and no credentials were read. Page text was treated as data.

**How the pages were read:** each page was fetched as text. Excerpts are in quotation marks and kept under 15 words;
everything else is paraphrase, marked "(paraphrase)" where it could be mistaken for a quote. Field names, enum values,
header names and numbers are reproduced as written. None of the pages showed a "last updated" date. Before code relies
on a fact, re-read the cited page.

This record confirms or refutes the Anthropic rows marked [UNRECORDED] in
[docs/architecture/multi-provider-design.md](../../docs/architecture/multi-provider-design.md) §3 and §4. Evidence ids
are `A-`; gaps are `AG-`.

## Sources

| ID | URL | Last updated (as shown) | Used for |
|---|---|---|---|
| S-1 | https://platform.claude.com/docs/en/api/overview | not shown | Base URL, auth and required headers, request size limits, response headers |
| S-2 | https://platform.claude.com/docs/en/api/versioning | not shown | `anthropic-version` values and what each changed |
| S-3 | https://platform.claude.com/docs/en/api/messages/create (also served at `/api/messages`) | not shown | Request parameters, `tool_choice`, `thinking`, Message response object, `stop_reason` enum, `usage` |
| S-4 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools (`…/implement-tool-use` redirects here) | not shown | Tool definition fields, `tool_choice` values, forced-tool restrictions |
| S-5 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls | not shown | `tool_use` / `tool_result` shapes, ordering rules, `is_error` |
| S-6 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use | not shown | Parallel calls, result placement, `disable_parallel_tool_use` |
| S-7 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use | not shown | `strict: true` guarantees, schema caching |
| S-8 | https://platform.claude.com/docs/en/build-with-claude/structured-outputs (section "JSON Schema limitations") | not shown | Supported JSON Schema subset for strict tools |
| S-9 | https://platform.claude.com/docs/en/build-with-claude/thinking | not shown | Thinking configuration per model, blocks, preservation, tool use, caching, billing, limits |
| S-10 | https://platform.claude.com/docs/en/build-with-claude/extended-thinking | not shown | Manual (`budget_tokens`) mode, deprecation, interleaved-thinking beta header |
| S-11 | https://platform.claude.com/docs/en/build-with-claude/preserved-thinking | not shown | Prefix check on thinking-block signatures (Claude 5.1+ models) |
| S-12 | https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons | not shown | Stop-reason meanings, refusal on HTTP 200, empty responses |
| S-13 | https://platform.claude.com/docs/en/build-with-claude/prompt-caching | not shown | Usage field semantics, cache invalidation hierarchy |
| S-14 | https://platform.claude.com/docs/en/api/errors | not shown | HTTP status codes, error types, error body, size limits, validation errors |
| S-15 | https://platform.claude.com/docs/en/api/rate-limits | not shown | 429 behaviour, `retry-after`, rate-limit headers, spend caps |
| S-16 | https://platform.claude.com/docs/en/models/overview (`/about-claude/models/overview` redirects here) | not shown | Current model ids, context window, max output, retirement dates |
| S-17 | https://platform.claude.com/docs/en/manage-claude/api-and-data-retention | not shown | Retention, ZDR, training use, Covered Models |

Referenced but **not retrieved**: the pricing page (`https://platform.claude.com/docs/en/about-claude/pricing`), the
Commercial Terms (`anthropic.com/legal/commercial-terms`) and the privacy-centre retention articles
(`privacy.claude.com/…`), which are outside the permitted documentation hosts (AG-8).

## 1. Endpoint, method, headers

| ID | Fact | Source |
|---|---|---|
| A-1 | Base URL `https://api.anthropic.com`; Messages endpoint `POST /v1/messages`. | S-1, S-3 |
| A-2 | Authentication (paraphrase): `Authorization: Bearer <token>` is required "unless `x-api-key` is set"; `x-api-key` is described as "Legacy fallback for `Authorization`, still supported". **Refines §3:** `x-api-key` is accepted but is no longer the primary documented header. | S-1 |
| A-3 | `anthropic-version` is "Required" in the S-1 header table (example value `2026-10-21`); S-2 says requests "must send an `anthropic-version` request header". The S-3 reference lists it as "optional string" (conflict, AG-1). | S-1, S-2, S-3 |
| A-4 | Version values: `2026-10-21` (latest; "Anthropic recommends using the latest API version"), `2023-06-01`, `2023-01-01`. Many guide examples still send `2023-06-01`; the S-3 reference example sends `2026-10-21`. | S-2, S-3, S-4 |
| A-5 | `2026-10-21` changes for Messages (paraphrase): `temperature`, `top_p` and `top_k` are removed and any of them returns 400 on every model; a `document` block in an `assistant` message returns 400; a user `text` block with non-empty `citations` returns 400. | S-2 |
| A-6 | Within a version Anthropic may add optional inputs, add output values, change error conditions and "Add new variants to enum-like output values". A codec must therefore tolerate unknown fields but should fail closed on unknown `stop_reason` or block types it must interpret. | S-2 |
| A-7 | `content-type: application/json` is required. `anthropic-workspace-id` is required only for a key not scoped to a workspace. | S-1 |
| A-8 | Beta features use beta headers (`anthropic-beta`, listed on the beta-headers page). Relevant here: `interleaved-thinking-2025-05-14` (manual-mode interleaving on older models only; accepted and ignored elsewhere) and `thinking-binding-controls-2026-08-01` (controls the prefix check, A-39). No beta header is needed for basic tool use or adaptive thinking. | S-10, S-11, S-9 |
| A-9 | Response headers include `request-id` (also `request_id` in error bodies), `anthropic-organization-id`, `anthropic-workspace-id`, and rate-limit headers (A-46). | S-1, S-14 |

## 2. Request body

| ID | Fact | Source |
|---|---|---|
| A-10 | `model`, `messages` and `max_tokens` carry no "optional" marker (required by inference); `max_tokens` is "The maximum number of tokens to generate before stopping." (minimum 0; `0` only pre-warms the cache). | S-3 |
| A-11 | `system`: "optional string or array of TextBlockParam" (each `{type: "text", text}` with `text` minLength 1). | S-3 |
| A-12 | `messages[].role`: `user` or `assistant` (the reference also lists `system` for per-message settings). "Consecutive `user` or `assistant` turns … will be combined into a single turn." Content may be a string or an array of blocks; request block types include `text`, `image`, `document`, `tool_use`, `tool_result`, `thinking`, `redacted_thinking`, `search_result` and server-tool blocks. | S-3 |
| A-13 | Prefill is rejected (paraphrase): Claude 4.6 and later models return 400 `invalid_request_error` when the last message is `assistant`; "The conversation must end with a user message." | S-14, S-9 |
| A-14 | Tool definition: `name` matching `^[a-zA-Z0-9_-]{1,128}$`, `description` (optional), `input_schema` ("A JSON Schema object", `type: "object"`), optional `strict`, `input_examples`, `cache_control`, `defer_loading`, `allowed_callers`. | S-4, S-3 |
| A-15 | `strict: true` "guarantees Claude's tool inputs match your JSON Schema" via grammar-constrained sampling; `name` "is always valid". Without strict mode (paraphrase) the model may return wrong types or omit required fields; no server-side validation of non-strict inputs is promised. | S-7 |
| A-16 | Strict-mode schema subset: supports basic types, `enum`, `const`, `anyOf`, `allOf` (no `$ref` inside), internal `$ref`/`$defs`, `default`, `required`, `additionalProperties: false`, listed string `format`s, simple `pattern` regexes, `minItems` 0 or 1. **Not supported:** `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, other array constraints, recursion, `additionalProperties` other than `false`. Raw requests with unsupported features get a 400 (paraphrase). Per request: at most 20 strict tools, 24 optional parameters, 16 union-typed parameters. | S-8 |
| A-17 | `tool_choice` values: `{"type": "auto"}` (default when `tools` are given), `{"type": "any"}`, `{"type": "tool", "name": …}`, `{"type": "none"}` ("The model will not be allowed to use tools."; default when no `tools`). | S-3, S-4 |
| A-18 | `disable_parallel_tool_use` (boolean, default false) sits **inside** `tool_choice` ("It is not a top-level request parameter"): with `auto` at most one tool call; with `any`/`tool` exactly one. | S-3, S-6 |
| A-19 | Forced tool use (`any`, `tool`) is rejected with 400 on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1 ("tool_choice: type \"tool\" and \"any\" are not supported for this model."); `auto` and `none` "are accepted". It is also rejected with manual extended thinking. Where accepted, a forced call skips thinking. **Confirms §3** (forced call rejected on several current models). | S-4, S-9, S-14 |
| A-20 | `thinking` variants: `{"type": "adaptive"}`, `{"type": "enabled", "budget_tokens"}` (≥1024, less than `max_tokens`), `{"type": "disabled"}`, `{"type": "between_tools"}` (Sonnet 5.5 only); optional `display`: `summarized`, `omitted` (and `updates`, beta). Effort is set with `output_config.effort`. | S-3, S-9 |
| A-21 | Per-model thinking (paraphrase of the S-9 table): on Claude 5-generation models thinking is on by default (adaptive) with `display` defaulting to `omitted`; Opus 5.5, Fable 5.1 and Mythos 5.1 reject `disabled` with 400; Sonnet 5.5 rejects `disabled` (use `between_tools`); Haiku 5.5 and Opus 5 accept `disabled` only at effort `high` or below. `type: "enabled"` returns 400 on 4.7 and later. **Thinking cannot be avoided on Opus 5.5.** | S-9, S-10, S-14 |
| A-22 | On Claude 5-generation models and Opus 4.7/4.8, non-default `temperature`/`top_p`/`top_k` return 400 on every request (and on every model under `2026-10-21`, A-5). | S-9, S-2 |

## 3. Response

| ID | Fact | Source |
|---|---|---|
| A-23 | Message object: `type: "message"`, `id`, `role: "assistant"`, `model`, `content[]`, `stop_reason`, `stop_sequence`, `stop_details`, `usage`, plus `container` and `diagnostics` (nullable). | S-3 |
| A-24 | Content blocks relevant to a client-tool codec: `text` (`text`, optional `citations`); `tool_use` (`id` with pattern `^[a-zA-Z0-9_-]+$`, `name`, `input` as a JSON **object** (`map[unknown]`), `caller`, optional `toolset_name`); `thinking` (`thinking`, `signature`); `redacted_thinking` (`data`). Server-tool blocks (`server_tool_use`, `*_tool_result`) appear only when server tools are declared. **Confirms §3:** tool args are a JSON object `input`; a call id is always present. | S-3, S-5 |
| A-25 | `signature`: opaque; pass thinking blocks back "exactly as received, with this field intact". `redacted_thinking.data` is "opaque and encrypted"; pass it back unchanged. With `display: "omitted"` the `thinking` text is empty but the signature still carries the encrypted thinking. | S-3, S-9 |
| A-26 | `stop_reason` enum (all seven confirmed): `end_turn`, `max_tokens` ("we exceeded the requested `max_tokens` or the model's maximum"), `stop_sequence`, `tool_use`, `pause_turn` ("we paused a long-running turn"; a server-tool loop limit), `refusal`, `model_context_window_exceeded`. Always non-null when not streaming. | S-3, S-12 |
| A-27 | Refusal: "Safety classifiers return this stop reason as a normal HTTP 200 response, not an error." `stop_details` (`type: "refusal"`, `category` one of `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`, `general_harms` or null, `explanation`) is set for refusals and null otherwise. **Confirms §3.** | S-12, S-3 |
| A-28 | `max_tokens` can cut a `tool_use` block short (paraphrase: retry with a higher limit). An `end_turn` with (nearly) empty content can follow tool results, commonly when text is added after `tool_result` blocks (paraphrase). | S-12 |
| A-29 | `usage`: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_creation` (`ephemeral_5m_input_tokens`, `ephemeral_1h_input_tokens`), `output_tokens_details.thinking_tokens`, `server_tool_use`, `service_tier`, `speed`, `inference_geo`. | S-3 |
| A-30 | `input_tokens` **excludes** cache reads and writes: "Total input tokens in a request is the summation of `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`." `input_tokens` counts tokens after the last cache breakpoint (paraphrase). **Confirms §3/§4 Step 3.** | S-3, S-13, S-15 |
| A-31 | Thinking is **inside** `output_tokens`: `output_tokens` "remains the inclusive, authoritative total used for billing"; `thinking_tokens` is "Always ≤ `output_tokens`" and reflects raw reasoning, not the summary. Current-turn thinking "always counts toward `max_tokens`" and is billed as output, including summarized or omitted thinking. **Confirms §3** (output cap includes reasoning). | S-3, S-9, S-10 |

## 4. Tool results

| ID | Fact | Source |
|---|---|---|
| A-32 | Results go in the next message with `role: "user"` as `tool_result` blocks: `tool_use_id` (the call's `id`), optional `content` (a string, or a list of `text`/`image`/`document`/`search_result` blocks), optional `is_error: true` for a failed execution. There is no `tool` role. | S-5 |
| A-33 | Ordering (paraphrase of the "Important formatting requirements"): results "must immediately follow" the assistant tool-use message with no message between; in that user message `tool_result` blocks "must come FIRST"; text must come after all results (text before them is a 400). Missing results produce an error such as "tool_use ids were found without tool_result blocks immediately after". All results for a parallel turn belong "together in a single user message"; S-6 frames splitting as degrading parallel use (consecutive user turns are merged anyway, A-12). Result order is not stated (AG-3). **Confirms §3**, with that nuance. | S-5, S-6 |
| A-34 | Tool output is untrusted; S-5 recommends keeping untrusted content inside `tool_result` blocks rather than `system` or user text (paraphrase). Matches Tracewise's evidence handling. | S-5 |

## 5. Thinking with tool use, replay and prefix rules

| ID | Fact | Source |
|---|---|---|
| A-35 | Within a tool-use turn, thinking blocks must be passed back "complete and unmodified" with the `tool_use` they accompanied. Summary on S-9: "Required: within a tool-use turn, pass thinking blocks back"; "Recommended: across turns, pass everything back"; "Allowed: outside tool use, omit prior turns' thinking". | S-9 |
| A-36 | In the latest assistant message the consecutive thinking blocks (including `redacted_thinking`) cannot be rearranged, edited or partially dropped; modified blocks get 400 `invalid_request_error` naming the position (for example `messages.1.content.0`). Exception: text placed in an omitted block's empty `thinking` field is ignored. | S-9, S-14 |
| A-37 | Older thinking: Opus 4.5+, Sonnet 4.6+, Haiku 5.5, Fable/Mythos keep all prior turns' thinking in context (billed as input); earlier models keep the last turn only and the API "strips them automatically". Either way, passing all blocks back is correct. | S-9 |
| A-38 | **Prefix check** (Claude 5.1+ models: Fable 5.1, Mythos 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5): a block stays valid only while "the top-level `system` prompt, the `tools`, and the messages before it are unchanged" (paraphrase). Thinking blocks may be removed only from the oldest end, the newest end, or all at once; removing one from the middle invalidates later ones. `tool_choice`, `max_tokens`, effort, `output_config`, `metadata` and `thinking.display` are **not** part of the check. **Confirms §3** ("system, tools and earlier messages unchanged"). | S-11, S-9 |
| A-39 | Enforcement (paraphrase): with `prefix_mismatch_behavior` unset, accounts created on or after 2026-08-31 get a 400 ("The block is bound to a different conversation") on Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5; older accounts get no error and the failing blocks are billed; Mythos 5.1 errors for both. `"drop_block"` (beta header `thinking-binding-controls-2026-08-01`) drops the failing and all later blocks instead. A block from a model the current model cannot read is dropped silently. | S-11, S-14 |
| A-40 | Changing tools or system mid-conversation therefore has two effects: cache invalidation (tools → system → messages hierarchy; a change invalidates its level and all later levels) and, on 5.1+ models, prefix-check failure of later thinking blocks. Changing `tool_choice` invalidates only message-level cache. **Confirms §4 Step 2** (constant tools, use `none`). | S-13, S-11, S-4 |
| A-41 | Interleaved thinking is automatic with adaptive thinking (no header); on Opus 5.5 and others "reasoning between tool calls always appears in thinking blocks". Thinking cannot be toggled mid-turn; if it is, the API silently disables thinking for that request rather than erroring (paraphrase). Changing thinking config or effort invalidates cache. | S-9, S-10 |

## 6. Errors, retries, limits

| ID | Fact | Source |
|---|---|---|
| A-42 | Error body: `{"type": "error", "error": {"type", "message"}, "request_id"}`; `type` values "may expand". | S-14 |
| A-43 | Status → type: 400 `invalid_request_error`; 401 `authentication_error`; 402 `billing_error`; 403 `permission_error`; 404 `not_found_error`; 409 `conflict_error`; 413 `request_too_large`; 429 `rate_limit_error`; 500 `api_error`; 504 `timeout_error`; 529 `overloaded_error`. | S-14 |
| A-44 | Spend: a **user-set** organization/workspace spend limit returns **400** `invalid_request_error` (message begins "You have reached your specified API usage limits"). The **tier** monthly spend cap returns 429 `rate_limit_error` with `error.details.error_code: "enforced_spend_limit_reached"` and no `retry-after`; retries fail until access resumes. | S-14, S-15 |
| A-45 | Rate limits are RPM, ITPM and OTPM per model class; a rate-limit 429 may carry `retry-after` ("The number of seconds to wait until you can retry"); "Not every 429 carries it". `cache_read_input_tokens` do not count toward ITPM on most models; OTPM counts actual output, not `max_tokens`. 429s can also come from acceleration limits. | S-15, S-14 |
| A-46 | Rate-limit headers: `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{limit,remaining,reset}` (reset in RFC 3339). | S-15 |
| A-47 | Request size: Messages API 128 MB (first-party); exceeding it gives 413, returned by Cloudflare before the API. | S-14, S-1 |
| A-48 | Retry guidance: 500 "Retry the request with exponential backoff"; the SDKs retry connection errors, 429 and 5xx twice by default, honouring `retry-after`. Non-streaming requests expected to exceed 10 minutes should use streaming or batches (paraphrase). | S-14 |

## 7. Models, limits, prices

| ID | Fact | Source |
|---|---|---|
| A-49 | Current models (as listed 2026-11-01): `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`; each 1M-token context window and 128K max output (synchronous Messages API); retirement "Not sooner than" 2027-09-01, 2027-09-22, 2027-09-28 and 2027-10-07 respectively. "Every Claude model ID is a pinned snapshot". | S-16 |
| A-50 | Legacy models still available: Fable 5, Opus 5, Opus 4.8, 4.7, 4.6, 4.5, Sonnet 5, Sonnet 4.6, Haiku 4.5. The reference marks `claude-sonnet-4-5` deprecated with end-of-life 2026-11-30. Per-model max output is also tabled on S-9 (64K for Opus 4.5 and Sonnet 4.5). The Models API (`GET /v1/models`) returns `max_input_tokens`, `max_tokens` and `capabilities` (including `thinking.types.disabled.supported`). | S-16, S-3, S-9 |
| A-51 | Prices are per million input/output tokens, shown on S-16 and the pricing page; cache reads and batch are discounted. Prices are not copied here; read them at run time (AG-7). | S-16 |

## 8. Data retention and training

| ID | Fact | Source |
|---|---|---|
| A-52 | "Retained data is never used for model training without your express permission." | S-17 |
| A-53 | Conversation content "is not retained by default" (paraphrase), except Covered Models (Fable 5.1, Mythos 5.1, Fable 5, Mythos 5), which "require 30-day data retention" and are unavailable under ZDR unless expressly authorised. | S-17 |
| A-54 | ZDR is arranged per organization through Anthropic sales. Regardless of arrangement, flagged content or legal requirements may lead to retention "for up to 2 years" (paraphrase). Strict tool use caches compiled schemas for up to 24 hours; prompts and responses are not retained by that feature. | S-17, S-7 |

## Gaps

| ID | Gap | Consequence |
|---|---|---|
| AG-1 | `anthropic-version`: required (S-1, S-2) vs "optional" (S-3); behaviour when omitted is not stated. Which version to pin (`2023-06-01` vs `2026-10-21`) is a choice; the observable differences listed are A-5 only. | Always send it; pin one value per codec and record it. |
| AG-2 | Whether a **non-strict** `input_schema` containing `maxLength`/`minimum` (as Tracewise's specs do, `prompt.py`) is accepted, ignored or enforced. Strict mode rejects them (A-16). | Keep `strict` off, or strip those keywords for Anthropic and rely on the loop's own validator; never trust `input` without local validation (A-15). |
| AG-3 | Required **order** of `tool_result` blocks for parallel calls, and whether a turn with fewer results than calls is always a 400 (only an example message is quoted, A-33). | Emit one result per call, in call order, in one user message; fail closed on mismatch. |
| AG-4 | Whether a `refusal` response may carry partial `content`, and whether `model_context_window_exceeded` can occur with `max_tokens` below the window. | Treat both, `pause_turn` and `max_tokens` as fail-closed outcomes. |
| AG-5 | The owner's account creation date (before or after 2026-08-31) decides whether prefix mismatches error or are silently billed (A-39). | Owner fact; design must keep history append-only either way. |
| AG-6 | Real response shapes (thinking blocks present with `display: "omitted"`, empty-text blocks, parallel calls, usage values). | Needs an authorised live observation, as for OpenAI and Gemini. |
| AG-7 | Current prices and the owner's tier limits. | Read at run time; no hard dollar ceiling (thinking is billed as output and cannot be disabled on Opus 5.5, A-21, A-31). |
| AG-8 | Commercial Terms and privacy-centre retention articles (outside permitted hosts); the default retention period for non-ZDR commercial use beyond A-53. | Cite S-17 only; owner to confirm terms. |

## Tracewise mapping (analysis; not contract)

- **§3 [UNRECORDED] rows, outcome:** auth — *refined* (Bearer primary, `x-api-key` legacy but supported, `anthropic-version` required; A-2, A-3); tool args as object `input` — *confirmed* (A-24); results first in one user message — *confirmed* (A-33); call id always — *confirmed* (A-24); replay of byte-identical `thinking`/`redacted_thinking` with unchanged system/tools/earlier messages — *confirmed* (A-35 to A-39); `{"type": "none"}` — *confirmed* (A-17); forced call rejected on several models — *confirmed* (A-19); `max_tokens`/`refusal` on HTTP 200 — *confirmed* (A-26, A-27); usage input excludes cache, thinking inside output — *confirmed* (A-30, A-31); output cap includes reasoning — *confirmed* (A-31).
- **Codec consequences:** keep `tools` constant and send `tool_choice: {"type": "none"}` for the final step (A-38, A-40); store each assistant turn's full `content` array (thinking, text and `tool_use` blocks) in `Message.replay` and re-emit it verbatim, including on text-only and repair turns, since mid-history removal breaks later blocks (A-38); never prefill and never add text before results (A-13, A-33); send no sampling parameters (A-5, A-22); budget `max_tokens` for thinking plus answer (A-31); map 400 spend-limit and 429 spend-cap as permanent, 429 with `retry-after`/500/529 as retryable (A-43 to A-45).
