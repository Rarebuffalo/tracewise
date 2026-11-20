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
| C-3 | **Offline done** | R-7, R-8, R-9 | The 4 read-only tools only, `strict: false` (our specs have optional fields, R-8); on a tool-free step the same tools are sent with `tool_choice: "none"` (R-9; constant declarations, multi-provider design step 2; `tests/investigate/test_codec_contract.py`). The loop still refuses tool calls on that step. |
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

**Continuation-state envelope (O-5, 2026-11-02):** the loop seals each step's replay items in a
`replay.ReplayEnvelope`. The envelope is bound to provider, model, tenant, job, job attempt and a random
investigation id. It has a 64 KiB cap per envelope and a 192 KiB cap per conversation, and a SHA-256 fingerprint
detects any change. It is masked in `repr` and refuses pickling and copying. `provider_view` opens envelopes only
when building the next request, so a codec receives the same raw items as before. A refusal (`ReplayError`, a fixed
reason code) ends the investigation as `provider_failed`. A provider's `replay_scope` (`tool_turns` or `all_turns`)
decides which assistant turns carry state. With `all_turns`, the repair turn keeps its exact text and state. The
engine accepts `all_turns`; no such codec exists, and Anthropic and DeepSeek stay unselectable.

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
| G-7 earlier calls on the final step | Omitting `tools` is not documented; R-9 offers `tool_choice: "none"` | Since 2026-11-01 the same `tools` with `tool_choice: "none"` when `allow_tools` is false (previously omitted) | harness `pass`, `final_step_rejects_without_tools` | Needs observation | Step 3 accepted (exit 0) or 400 (exit 7). If 400, fix in the codec with tests before T-605. |
| `store: false` | R-3: `store` defaults to true | Always `false` | `test_encode_maps_*`; harness requests record `store` | Resolved (decision); account-level retention is C-8 | Nothing in code; the owner confirms account settings (A-4) |
| Quota versus rate limit | R-12, R-14 | See G-2 | See G-2 | Resolved offline from R-12 | Only if it occurs |
| Bounded rounds, time, retries | Ours (FS-DX-3) | `InvestigationLimits`; adapter `max_retries` ≤3 and deadline; the harness uses 0 retries and at most 3 requests | `test_loop*`, `test_http_adapter*`, harness budget test | Resolved offline | Nothing |
| G-4 reachability | n/a | n/a | n/a | Needs observation | Exit 0 |
| G-6 / C-9 model, limits, prices | not recorded | Configuration only | n/a | Owner decision and model information | Not established by the smoke run, except token usage for the cost record |

**No code change was needed for 47B.** Every gap the contract leaves open already fails closed. The remaining ones can only be closed by the smoke observation or an owner decision.

**Smoke harness:** `scripts/openai_smoke.py`, with its procedure, limits, evidence policy and authorisation checklist in [SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md). Phase 49 hardened it: unexpected JSON structures are `unsupported_response` (exit 8); the per-step and overall limits are wall-clock deadlines enforced at the socket layer (exit 10, runbook §4a); and decode now rejects a message whose `content` is not a list as a `WireError`. It is not part of the product: `providers.py` still refuses `LLM_PROVIDER=openai`.

## 3. Steps to finish T-605 (each needs your approval)

1. ~~Record C-1 to C-8 as evidence.~~ Done (Phase 45, §2b).
2. ~~Write the codec and contract-test it offline.~~ Done (`OpenAIResponsesWire`, §2b).
3. After the smoke call (G-4), wire `LLM_PROVIDER=openai` in `investigate/providers.py`.
4. Provide a key **locally** (O-2). Run the benchmark's model mode (below; prepared 2026-10-25, not run). Measure accuracy, cost (C-9) and latency, with at most 3 prompt/model iterations (TASKS rule 4). Run E-01 for injection resistance.
5. Choose the model (UD-3). Write the privacy notice (T-1001).

## 3a. Benchmark model mode (prepared 2026-10-25; NOT run)

`python -m tracewise.bench run --kind model --model ID --key-file PATH --authorization-ref REF --max-requests N
[--case ID ...] [--reps N] --out DIR` runs the frozen cases through the product's own `HTTPProvider` and
`OpenAIResponsesWire` (`src/tracewise/bench/model_provider.py`). It needs the T-605 approval and is owner-run only.
Product selection is unchanged: `LLM_PROVIDER=openai` still refuses.

- **Refused before the key is read:** under a test runner or CI (`PYTEST_CURRENT_TEST` or `CI` set); without an
  authorisation reference; without an explicit model id; without `--max-requests`. The flag accepts 1 to 2000:
  2000 is an implementation safety maximum on the flag, **not an approved spend budget**. The owner sets the cap
  for each run as part of the T-605 approval.
- **Key:** only from an owner-only regular file outside the repository. A symlink, a group- or world-readable file,
  or one inside the repository is refused. The rules are shared with the smoke harness
  (`src/tracewise/investigate/model_access.py`).
- **Requests:** `max_retries=0`. A host-locked transport allows only POST to the recorded endpoint and stops at N
  requests for the whole run. A refused request is never sent.
- **Request-body cap: 256 KiB** (`model_provider.MAX_REQUEST_BYTES`), checked on the actual serialised body before
  it reaches the network, every turn of every investigation. Not the smoke harness's 32 KiB, which fits its
  synthetic few-hundred-byte prompts but not an evidence bundle of up to 24,000 characters. The investigation's own
  caps put a conversation at about 135,000 characters plus JSON escaping (bundle, up to 12 tool results of 8,000,
  12 argument sets of 1,024, a 2,000-character repair turn, the ~1.6 kB policy); the rest is room for the model's
  short turns and replayed reasoning items. An over-cap request is refused unsent with a fixed message, and that run
  becomes an `error` row (`RequestTooLarge`, never scored); the evaluation continues. A model that writes long
  texts alongside its tool calls can reach the cap.
- **Wall-clock deadline per request** (`investigate/deadline_http.py`, shared with the smoke harness). Each
  request's total deadline is its own timeout, which the adapter sets to the investigation's remaining time, so no
  request outlives the investigation's 120 s budget. Enforced at the socket layer: name resolution in a thread
  abandoned at the deadline; connect, TLS handshake, every read and write clamped to the time left; a watchdog
  that shuts the socket down once the clock passes the deadline, which stops a peer that trickles bytes. Bound: the
  deadline plus the 20 ms watchdog interval plus scheduling jitter. Not covered: the OS scheduler, and local work
  between requests (the investigation loop checks its own deadline before each step).
- **When the cap is reached the evaluation stops** (`run_suite(budget=...)`). The run whose request was refused is
  recorded as `interrupted` (its diagnosis, report and pre-pass are discarded, because its outcome reflects the
  cap, not the model). Every analysis run not yet started is `interrupted` too. Completed runs keep their results.
  `interrupted` runs are never scored: no points, no abstention credit, no metric denominators. The summary is
  `complete: false`, `results.json` carries `interrupted`, the report opens with an **INCOMPLETE** notice saying the
  metrics cover only completed runs, and the exit code is 1. Track A (pre-pass only) and P2 runs use no provider
  and still run.
- **Run identity:** `config_id` hashes the configuration (benchmark version, truth lock, provider and model, cases,
  repetitions, slow cases, label; not the request cap) and is stable across equivalent runs. A complete evaluation
  has `run_id == config_id`; one stopped by the cap has `run_id = <config_id>-interrupted`, so it never shares an
  identifier with a complete one. Both ids are in `results.json` and `scores.json`; the report title of an
  interrupted run ends in "(INCOMPLETE)", and re-scoring (`score RESULTS.json`) keeps both.
- **Abstentions versus failures:** a provider or execution failure (`provider_failed`, `provider_timeout`,
  `invalid_output`, `budget_exhausted`, `unproductive`) is still scored as an abstention under BENCHMARK §4
  (unchanged), but the report counts these separately from abstentions the model chose, and lists them by reason.
- **Output:** results and the report are labelled "model-based evaluation, not proven model accuracy", with the
  model id, the authorisation reference and the request counts. Nothing is written if any output would contain
  the key: the check uses a `SecretCanary` built when the key file is read (`investigate/model_access.py`), so the
  CLI never reads the adapter's private key field. It runs on the exact bytes of `results.json`, `scores.json` and
  `report.md` before any of them is written, and only those checked bytes are written and printed. An unexpected
  error ends with `error: the evaluation stopped unexpectedly (<type>)` and exit 3: no traceback, no message,
  nothing written. Run as `python -m tracewise.bench`, logging is JSON to stderr at WARNING through the shared
  secret filter, with which the adapter registers the key; `main()` itself never replaces a caller's log handlers.
  The model never receives `reference.yaml` or `truth.yaml`.
- **Smoke harness versus benchmark caps:** the smoke harness (SMOKE-RUNBOOK §4) sends a fixed synthetic
  conversation: at most 3 requests, a 32 KiB request body, a 256 KiB response, 2,048 output tokens, 30 s per step
  and 90 s in total. The benchmark sends real evidence: N requests (owner-set), a 256 KiB request body, a 1 MB
  response, 16,000 output tokens, and the investigation's 120 s per request. Both use the same wall-clock deadline
  backend (`investigate/deadline_http.py`) and key-file rules.
- **Cost and usage: what is enforced, and what is not.**
  - *Hard:* the number of requests for the whole run (N; refused requests are never sent), with no retries.
  - *Per request, before sending:* the body ≤256 KiB; `max_output_tokens` = 16,000, deliberately the
    16,000-character answer cap (`schema.MAX_FINAL_CHARS`) sent as a token count, enforced by the provider and
    including reasoning tokens; a total wall-clock deadline equal to the investigation's remaining time.
  - *Per request, while and after reading:* the response body ≤1 MB; the answer text ≤16,000 characters.
  - *Per investigation:* at most 12 tool calls and 16 iterations; a 200,000-token budget (input plus output) that
    is checked after each response, so a single response can overshoot it before the investigation stops.
  - *Input size:* the 256 KiB body cap is a hard limit in bytes; there is **no per-request input-token limit** (the
    token count of 256 KiB depends on the content and the model's tokenizer).
  - *Usage:* the provider's `input_tokens` and `output_tokens` are required in every response. A response without
    them, an `incomplete` response, a refusal or any unknown shape fails closed as `provider_failed`. Usage is
    recorded per run in the diagnosis and reported as mean tokens per analysis run. Since 2026-11-01 the codec also
    maps the recorded breakdown (R-11: `input_tokens_details.cached_tokens`, `output_tokens_details.reasoning_tokens`)
    into `StepUsage` as subsets of the totals; a detail larger than its total, negative or malformed fails closed. The
    error kind distinguishes `ProviderTruncated` (`incomplete` with reason `max_output_tokens`, R-13) and
    `ProviderRefusal` (a `refusal` part) from other failures; the outcome is unchanged.
  - *Cost:* **not computed and not limited.** No prices are configured (G-6, C-9), so the benchmark reports tokens
    only. **There is no hard token or spend ceiling for the whole run**: only the request cap. The worst case is
    roughly N requests × (one request's input + up to 16,000 output tokens), and one request's input depends on the
    conversation. A dollar bound needs the approved model's prices and an owner-chosen limit.
- **Tests:** `tests/bench/test_model_mode.py` (mock transport only), plus the structural guards in
  `tests/investigate/test_providers.py` and `tests/unit/test_github_client.py`.

## 3b. Gemini native `generateContent` codec (2026-10-26; offline only, NOT run)

`src/tracewise/investigate/gemini_generate.py` (`GeminiGenerateContentWire`), written against the recorded contract
in `research/gemini-api-reference-2026-10-26/README.md` (Addendum A). It is reached only through the benchmark's model
mode, `--api gemini-generate-content` (`--api` defaults to `openai-responses`, the unchanged OpenAI path). Product
selection does not know it: `LLM_PROVIDER` accepts only `openai` (refused) and `fake`. Tests:
`tests/investigate/test_gemini_generate.py` (synthetic fixtures, mock transports). Nothing has been observed from the
real endpoint.

- **Endpoint and key:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` with
  the key only in `x-goog-api-key`. The model id is explicit and restricted to lowercase dotted or dashed names, so it
  cannot alter the path; the host lock compares the whole URL, model included. All transport guards are the shared
  ones (§3a): request cap, 256 KiB body cap, per-request deadline, no redirects, no proxies, zero retries.
- **Request:** system messages → `systemInstruction`; user messages → `user` content; tools →
  `functionDeclarations` (the JSON Schema specs in `parametersJsonSchema`, never `parameters`, which takes the
  OpenAPI subset: research record Addendum C) with `toolConfig` mode `AUTO`; a tool-free step keeps the same declarations and
  sets mode `NONE` (constant declarations, multi-provider design step 2; a request without tools keeps only the
  known tools the history uses, never inventing one for a name the investigator rejected); `generationConfig` `maxOutputTokens` (the answer cap) and `candidateCount: 1`.
  `maxOutputTokens` semantics are undocumented for this API (NG-1), so it is a requested upper bound, not a
  guarantee. Per-model maxima are documented (`outputTokenLimit` from `models.get`; 65,536-token output budgets for
  the Gemini 3 and 2.5 families on the token guide), but not the default when the field is unset, nor whether it
  includes thinking tokens here (research record, Addendum B). No thinking configuration is sent (undocumented here).
- **Response (fail closed):** exactly one candidate; finish reason `STOP` only, every other documented value and
  any unknown or missing one refused; a prompt block refused; parts limited to `text`, `thought`, `thoughtSignature`
  and `functionCall` (anything else refused); the model turn must carry role `model`; thought parts are never answer
  text; usage requires `promptTokenCount` and `candidatesTokenCount`; input adds `toolUsePromptTokenCount`, output
  adds `thoughtsTokenCount`. Breakdown (subsets of the totals): `cachedContentTokenCount` → cached input,
  `thoughtsTokenCount` → reasoning output. `MAX_TOKENS` → `ProviderTruncated`; `SAFETY`, `RECITATION`, `BLOCKLIST`,
  `PROHIBITED_CONTENT`, `SPII` and a prompt block → `ProviderRefusal`; every other non-`STOP` reason stays a generic
  `ProviderError`. All three give the same `provider_failed` outcome.
- **Call ids:** a function call without an id is refused (never invented, NG-4); duplicate ids are refused; results
  are paired by id only: an unmatched, missing or duplicate result is refused.
- **Replay boundary (owner policy, 2026-10-26):** the model's own returned content is kept verbatim so thought
  signatures stay where the model put them (N-15, N-16). It travels in `Message.replay`, which skips P-2 redaction,
  only as a `SignedTurn` that the same codec instance produced for the same model, authenticated with an HMAC key
  that never leaves the instance, and only on a turn whose validated `tool_calls` match its function calls exactly
  (ids, names, arguments, order; arguments are compared exactly as signed, or as the investigator's deterministic
  redaction of exactly those arguments, so a secret-shaped `grep` pattern does not break the round trip). A failed
  encode changes no codec state (epoch, decode binding, declarations). It is also bound to its exchange: the MAC covers a digest of the exact request
  that produced it, and it is accepted only directly after that same history, so it cannot be repeated in the same
  conversation. It is bound to its conversation as well: every request without a signed turn starts a new
  conversation with a fresh random epoch, and a turn is accepted only in the epoch that minted it, so a stale turn is
  refused even when an identical history is reconstructed (the same benchmark case run again). Decoding consumes the
  request binding, so a second response for one request is never replayable. The codec handles one exchange at a
  time; it is not for concurrent use. A
  forged, modified, reused, other-instance, other-model or OpenAI item is refused, and the OpenAI codec refuses a
  `SignedTurn`. It is never displayed (`repr` masked) and refuses JSON serialisation, pickling and copying; it never
  reaches the diagnosis, results or report. Tools still run only through the investigator's validated `tool_calls`.
- **Known limits:** the role of function-response content is `user` (NG-3: the only non-model role the reference
  allows); a signature on a final text answer is not replayed if the investigator asks for a repair turn, so a
  provider that then demands it ends `provider_failed`; `generateContent` error bodies are undocumented (NG-5), so
  errors are classified by HTTP status only and no 429 is treated as permanent; whether the server honours every
  JSON Schema keyword the specs use (`maxLength`, `minimum`) is not stated.
- **Contract change:** `Diagnosis.usage.provider` gained the value `gemini` (contracts.py and the SPEC example), used
  only by this benchmark path.
