# Multi-provider model architecture (design, 2026-10-30)

**Status (2026-11-01): steps 2, 3 and the stop-kind half of step 4 implemented offline; step 1 waits for owner
decision O-5; the Anthropic and DeepSeek contracts are now recorded; no new codec exists.** What changed on
2026-11-01:

- **Step 2 done.** The investigator sends the same four tool declarations on every step; a tool-free step clears
  `allow_tools`, which the OpenAI codec sends as `tool_choice: "none"` and the Gemini codec as mode `NONE`. The OpenAI
  smoke harness mirrors this (its step 3 now answers G-7 for the shape the product actually sends).
- **Step 3 done (in memory).** `StepUsage` keeps `input_tokens`/`output_tokens` as totals and adds
  `cached_input_tokens` and `reasoning_output_tokens` as validated subsets, mapped from recorded fields only (OpenAI
  R-11, Gemini N-23); the investigation result carries them. Persisting them to the operations record needs a schema
  migration and is not done.
- **Step 4b, capability metadata done (2026-11-01, later session).** Each codec declares `CodecCapabilities`
  (none mode, replay scope, usage breakdown; output-cap semantics descriptive only). `HTTPProvider` refuses, at
  construction, a codec the loop cannot run: one without a none mode, or one needing replay on every assistant turn
  (the Anthropic and DeepSeek shape) until step 1 exists.
- **Step 4, stop kinds done; capability metadata not done (superseded by the line above).** `ProviderRefusal` and `ProviderTruncated` (subclasses of
  `ProviderError`, same `provider_failed` outcome) are raised only for documented reasons; the loop logs the kind.
- **Contract tests.** `tests/investigate/test_codec_contract.py` runs one provider-neutral suite over both codecs;
  a new codec joins its parametrisation with its own response builders.
- **Records.** [research/anthropic-api-reference-2026-11-01](../../research/anthropic-api-reference-2026-11-01/README.md)
  and [research/deepseek-api-reference-2026-11-01](../../research/deepseek-api-reference-2026-11-01/README.md) now
  hold the facts marked [UNRECORDED] below (confirmed, with two corrections: Anthropic's API overview now names
  `Authorization: Bearer` as the main header with `x-api-key` as a legacy fallback, and DeepSeek's current model ids
  are `deepseek-flash` and `deepseek-v4-pro`). Both confirm that step 1 is a precondition: Anthropic validates thinking
  blocks against an unchanged prefix on its 5.x models, and DeepSeek requires `reasoning_content` on every earlier
  assistant turn whenever `tools` is sent, which, after step 2, is every investigator request.

The original status line follows. **Status: design proposal; not implemented beyond what exists today.** No provider is enabled in the product. Product
selection (`src/tracewise/investigate/providers.py`) still accepts only the test fake and refuses `openai`; Gemini
exists only in the benchmark model mode. This document describes how to add providers without turning the
investigator into a set of provider-specific loops.

**Evidence.** Current code at HEAD `a738c61` plus this review's working tree; the recorded contracts
[research/openai-api-reference-2026-10-19](../../research/openai-api-reference-2026-10-19/README.md) and
[research/gemini-api-reference-2026-10-26](../../research/gemini-api-reference-2026-10-26/README.md); and a research
pass over official OpenAI, Anthropic, DeepSeek and Gemini documentation on 2026-10-30 whose findings are summarised in
§3. **Facts marked [UNRECORDED] come from that pass but have not been written up as a repository research record.**
Before any codec is written for that provider, they must be recorded the way the Gemini contract was (sources, short
quotes, numbered facts, gaps).

## 1. Decision

**A hybrid: one shared, provider-neutral investigation loop, with a native wire codec per provider.** The loop owns
budgets, tool validation and dispatch, redaction of evidence, repair, outcomes and validation. A codec owns every wire
detail: endpoint, authentication, request encoding, response decoding, opaque conversation state, usage mapping and
error classification. No provider is routed through another provider's compatibility endpoint.

Why:

1. **All four providers share the same conversation model**: the client resends the whole history; the model returns
   tool calls with provider-issued ids; the client returns id-paired results; a "no tools" mode exists (OpenAI
   `tool_choice: "none"`, Anthropic `{"type": "none"}`, DeepSeek `"none"`, Gemini `NONE`) [UNRECORDED except Gemini
   N-8]. The differences are encoding and opaque state, which is what a codec is for.
2. **The safety logic must exist once.** Budgets (FS-DX-3), tool allowlist and argument validation, P-2 redaction of
   evidence, repair and outcome mapping would otherwise be duplicated per provider and drift.
3. **Compatibility endpoints lose correctness.** Google's OpenAI-compatible Chat Completions layer is "still in beta"
   and does not document where thought signatures travel (Gemini record G-1, G-2); the native API does.

Rejected alternatives are in §9.

## 2. Components and boundaries

```
GitHub webhook ─► web (HMAC, ingest) ─► Postgres queue ─► worker
                                                      │
                                          collect_evidence (logs, pre-pass, code source)
                                                      │
                                       investigate()  ← shared loop (budgets, tools, redaction, repair)
                                                      │  Provider.step(StepRequest) → StepResponse
                                              HTTPProvider (vendor-neutral transport)
                                                      │  WireCodec: encode / decode / errors
                         ┌──────────────┬─────────────┼──────────────┬───────────────┐
                 OpenAIResponsesWire  GeminiGenerateContentWire  (AnthropicMessagesWire)  (DeepSeekChatWire)
                                                      │
                                guarded transport (exact endpoint, POST, request/body caps, deadline)
                                                      │
                                                provider API
                                                      │
                                validate → confidence → render → publish (Check Run, comments)
```

- **Shared loop** (`investigate/loop.py`): unchanged responsibilities. It never sees provider wire formats.
- **`Provider` protocol** (`investigate/provider.py`): `step(StepRequest) -> StepResponse`, plus `name` and `model`.
- **`HTTPProvider`** (`investigate/http_adapter.py`): one request per attempt, bounded retries, byte cap, key held in a
  `SecretStr`, errors carry only provider, status and class.
- **`WireCodec`** per provider: `endpoint`, `auth_headers`, `encode`, `decode`, optional `is_permanent`.
- **Guarded transport** (`investigate/model_access.py`, `deadline_http.py`): exact URL and method lock, request cap,
  request-body cap, per-request wall-clock deadline. Used by owner-run tools today; the product needs the same chain
  when a provider is enabled.
- **Selection** (`investigate/providers.py`): the only place the product chooses a provider. It stays closed until a
  provider passes its smoke test and benchmark and the owner approves.

## 3. What differs between providers (summary)

| Concern | OpenAI Responses | Gemini generateContent | Anthropic Messages | DeepSeek chat completions |
|---|---|---|---|---|
| Auth | `Authorization: Bearer` (R-2) | `x-goog-api-key` (N-2) | `x-api-key` + required `anthropic-version` [UNRECORDED] | `Authorization: Bearer` [UNRECORDED] |
| Tool args | JSON string (R-5) | JSON object (N-7) | JSON object `input` [UNRECORDED] | JSON string [UNRECORDED] |
| Results | `function_call_output` per call (R-6) | `functionResponse` parts in one content (N-7) | all `tool_result` blocks first in one user message [UNRECORDED] | one `tool` message per call [UNRECORDED] |
| Call id | always (R-5) | optional; codec refuses missing (NG-4) | always [UNRECORDED] | always [UNRECORDED] |
| Opaque state to replay | reasoning items with `encrypted_content` (R-10); newer models may need all output items, text turns included [UNRECORDED] | signatures on any part; verbatim model turn (N-15) | `thinking`/`redacted_thinking` blocks, byte-identical; some models check that system, tools and earlier messages are unchanged [UNRECORDED] | plaintext `reasoning_content`, required on every earlier assistant turn when tools are present [UNRECORDED] |
| "No tools" mode | `tool_choice: "none"` | `functionCallingConfig.mode: NONE` (N-8) | `tool_choice: {"type": "none"}` | `tool_choice: "none"` |
| Forced tool call | `required` | `ANY` | rejected on several current models [UNRECORDED] | rejected in thinking mode [UNRECORDED] |
| Truncation / refusal | `incomplete` / `refusal` part (R-11, R-13) | `MAX_TOKENS` / `SAFETY`, block reasons (N-13, N-14) | `max_tokens` / `refusal` stop reasons on HTTP 200 [UNRECORDED] | `length` / `content_filter` [UNRECORDED] |
| Usage | input incl. cached detail; reasoning inside output | prompt, tool-use prompt, candidates, thoughts (N-23) | input **excludes** cache read/write; thinking inside output [UNRECORDED] | prompt = cache hit + miss; reasoning detail [UNRECORDED] |
| Output cap includes reasoning | yes [UNRECORDED] | yes on Interactions; undocumented for generateContent (NG-1) | yes [UNRECORDED] | not stated |

## 4. Required changes to the shared contract (the migration)

The current abstractions hold up, with four gaps that the research above makes concrete. Each step is small, keeps the
fake provider deterministic, and is gated by tests.

**Step 1. Replay on every assistant turn, owned by the codec.**
Today replay is attached only to tool-call turns (`loop.py`), the repair turn re-sends the model's text truncated to
2,000 characters without replay, and the OpenAI codec drops replay on text turns. Anthropic's prefix check and
DeepSeek's every-turn rule make that a 400 [UNRECORDED]; Gemini may need text-part signatures (NG-2).
- Every decoded assistant turn may carry a codec-owned, verbatim, authenticated replay object (generalise Gemini's
  `SignedTurn`: HMAC with a per-instance key, bound to the model, the request that produced it and the conversation).
- The loop attaches the decoded replay to whatever assistant message it records, including the repair turn, and
  never truncates what is sent back (truncate only what is logged).
- The encoder emits the model's own turn verbatim from the replay and checks it against the loop's validated view.
- **Policy gate (owner, O-5):** replay skips P-2 redaction by design, and for DeepSeek it is plaintext reasoning that
  can echo repository content. Replay must stay in memory, never be logged or persisted, and only be sent back to the
  provider and model that produced it. The exception must be recorded in DATA-INVENTORY before this step ships.

**Step 2. Constant tool declarations; "none" instead of removal.**
Today the final step sends `tools=()`. On providers that check the conversation prefix, changing the tools invalidates
earlier opaque state. Change the contract to: the tool list is constant for a conversation; `allow_tools=False` maps to
each provider's "none" mode. Never use forced-call modes.

**Step 3. Usage breakdown.**
Extend `StepUsage` with `cache_read_input`, `cache_write_input`, `reasoning_output` and a consistently defined
`input_total` and `output_total`. Each codec maps its provider's fields (for example Anthropic's `input_tokens`
excludes cache tokens; DeepSeek's `prompt_tokens` includes them). Budgets use the totals. Diagnosis usage keeps its
current fields; the breakdown goes to the operations record so that output tokens, thinking tokens, tool-use tokens,
estimated cost and actual provider charges are never conflated.

**Step 4. Normalised stop kinds and capability metadata.**
- `ProviderRefusal` and `ProviderTruncated` subclasses of `ProviderError` (outcome unchanged: inconclusive), so
  telemetry can tell a refusal from a truncation from an outage.
- Codec capability metadata: supports "none" mode; parallel-call off switch; output cap includes reasoning; replay
  scope (tool turns or all turns); prefix-checked history; token-based output budget separate from
  `max_output_chars` (today the character cap is sent as a token cap, which can starve reasoning models).

**Step 5. Codecs, one at a time.** For each new provider: record its contract in `research/`, write the codec against
the recorded facts, add contract tests, run one authorised smoke test, then the benchmark. Order proposed by risk and
evidence: finish OpenAI and Gemini first (records exist), then Anthropic, then DeepSeek (data-location terms need owner
review).

## 5. Request and response lifecycle (one step)

```mermaid
sequenceDiagram
  participant L as Shared loop
  participant P as HTTPProvider
  participant C as WireCodec
  participant T as Guarded transport
  participant A as Provider API
  L->>L: provider_view(history) (redact evidence; keep replay objects as they are)
  L->>P: step(StepRequest: messages, tools, allow_tools, budgets, time left)
  P->>C: encode(model, request)
  C->>C: verify each replay object (MAC, model, conversation, request prefix); match validated tool calls
  C-->>P: body (or WireError: nothing sent)
  P->>T: POST endpoint, auth header
  T->>T: exact URL + method, request cap, body cap, deadline
  T->>A: request
  A-->>T: response (byte-capped, deadline-bounded)
  T-->>P: status, body
  P->>C: decode(body) (consumes the request binding)
  C-->>P: StepResponse(text, tool_calls, usage, replay) or WireError
  P-->>L: StepResponse or ProviderError (no body, no key)
  L->>L: validate tool calls, dispatch read-only tools, check deadline per call
```

## 6. Security boundaries

- **Model capabilities**: four read-only tools; no execution, writes or network. Unchanged by any provider.
- **What a provider receives**: redacted evidence (P-2), the fixed policy, tool specs, and its own previous turns as
  replay. Replay is the only unredacted channel (owner exception O-5).
- **Credentials**: a key per provider, from a file outside the repository with owner-only permissions for owner-run
  tools; product key handling to be decided with provider activation (environment versus file, M-11). Keys never
  appear in URLs, bodies, logs, errors or outputs; `SecretCanary` checks written artifacts.
- **Network**: exact endpoint per codec, POST only, no redirects, no proxies, a deadline per request, request and
  response byte caps.
- **Selection**: one closed switch in `providers.py`; structural tests prove no product module constructs a real
  provider or imports a codec.

## 7. Errors, retries and cost

- Codecs classify permanent errors (`is_permanent`): quota and billing exhaustion are never retried (OpenAI quota codes,
  Anthropic spend-limit 429, DeepSeek 402 [UNRECORDED]). Rate limits and 5xx are retried within the request's deadline,
  honouring `retry-after`; owner-run tools use zero retries.
- Every failure becomes an inconclusive outcome (`provider_failed`, `provider_timeout`, `budget_exhausted`), never a
  guessed diagnosis.
- Cost is computed only from owner-configured prices per model (`LLM_PRICE_*`); unpriced stays unpriced. A request cap
  and token budgets bound usage; **no hard dollar ceiling exists** (input tokens are not limited before sending).

## 8. Testing strategy

- **Contract tests per codec** with synthetic fixtures built from the recorded field names: encode shapes, decode of
  every finish state, id pairing, replay authentication and tampering, usage mapping, error classification.
- **Loop tests with scripted providers** (unchanged) plus a shared parametrised suite that runs the same conversation
  scripts through every codec via mock transports.
- **Structural tests**: only the benchmark constructs real providers; product selection refuses them; network modules
  are allowlisted.
- **Owner-run smoke test per provider** (three requests, synthetic content), then the benchmark (T-605).
- The fake provider stays deterministic; benchmark truth and its lock never change.

## 9. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| One loop per provider | Duplicates budgets, validation and redaction four times; safety drift |
| Everything through an OpenAI-compatible endpoint | Compatibility layers are beta or undocumented for opaque state (Gemini G-1/G-2); loses native features |
| A normalised, provider-neutral reasoning representation | Opaque state must be returned byte-identical (Anthropic, Gemini) or verbatim plaintext (DeepSeek); normalising it breaks the contract |
| A third-party multi-provider SDK | New dependency and trust surface; hides the exact request, which the security model needs to see |
| Enabling several providers at once | Each needs its own recorded contract, smoke test and benchmark; one verified reference first |
