# O-5: replaying provider-issued reasoning and continuation state outside P-2 redaction

**Date:** 2026-11-01
**Status:** Proposal for owner decision. **The Anthropic and DeepSeek codecs must not be implemented until this is approved.**
**Scope:** read-only analysis of the working tree and the recorded API research. No network call, no test run, no code change.

**Question.** May state that a provider issues (reasoning, signatures, encrypted continuation items, the model's own
turn) be sent back to that provider without the P-2 redaction applied to everything else sent to models?

**Short answer.** Accept with conditions. Two qualifications matter:

1. This partly ratifies what the code already does. OpenAI and Gemini replay their state unredacted today, in offline and
   benchmark code only (see §3).
2. DeepSeek also needs a separate gate for data location and training.

## 1. Baseline facts

- **What P-2 says.** P-2 = A: "redact all repository-derived content before provider calls" (docs/DECISIONS.md:34). It
  is enforced in one place, `provider_view` (src/tracewise/investigate/loop.py:97-114). That function redacts every
  message's `content` and every string in its `tool_calls` arguments. It passes `replay=m.replay` through unchanged
  (loop.py:111).
- **The data inventory overstates this.** docs/DATA-INVENTORY.md:38 and :58 say that "the model's own replayed turns"
  are redacted, and that "everything" is redacted at the boundary. The loop's docstring makes the same claim
  (loop.py:100-104). The comment on `Message.replay` says the field is "Never repository content"
  (src/tracewise/investigate/provider.py:26-28). None of these is accurate for the Gemini replay (see §3), so the
  documents need correcting whatever the owner decides.
- **Redaction can miss secrets (P-4).** Redaction works by matching patterns. Secrets that are split, encoded or in
  unknown formats pass through (DATA-INVENTORY.md:67).
- **The design already names O-5 as the gate.** docs/architecture/multi-provider-design.md:111-122 (§4 step 1) calls
  O-5 the gate before replay can be generalised. Its §6 (:176-177) calls replay "the only unredacted channel".
- **A prior approval is referenced but not recorded.** docs/MODEL-ADAPTER.md:258 labels the Gemini replay boundary
  "owner policy, 2026-10-26". I found no matching entry in DECISIONS.md or OWNER-DECISION-PACKET.md (a grep for
  "replay" in those files returns nothing). O-5 should record that approval explicitly.

## 2. Five classes of data

| Class | Provider requirement (record IDs) | What it may contain | Encrypted to us? | Where Tracewise holds it today | Redaction today |
|---|---|---|---|---|---|
| **1. Human-readable model reasoning** | DeepSeek `reasoning_content` must be "fully passed back" on every earlier assistant turn whenever `tools` is sent (D-26). Leaving it out gives HTTP 400 (D-27). It is ignored when there are no tools (D-28). Anthropic `thinking` text is summarised, or empty when `display: "omitted"` (A-20, A-25). Gemini `thought: true` text parts (N-6). The OpenAI reasoning `summary` (MODEL-ADAPTER.md:95) | Model-written text derived from the redacted inputs. It can quote or paraphrase repository content, and it can reassemble a split or encoded secret (P-4) | No, it is plaintext | Gemini: inside `SignedTurn._content` (gemini_generate.py:274). OpenAI: inside the replayed item dict (openai_responses.py:139-142). Anthropic and DeepSeek: no codec yet | None. It goes through the replay channel |
| **2. Opaque continuation state** | OpenAI `encrypted_content`: reasoning items are passed back with function-call outputs (R-10), and the codec uses `store: false` (openai_responses.py:79). Gemini `thoughtSignature`: resend "exactly as they were received" (N-15, N-16). A missing signature returns `MISSING_THOUGHT_SIGNATURE` (N-17). Anthropic `signature` and `redacted_thinking.data` are "opaque and encrypted" and must be passed back unchanged (A-25, A-35, A-36) | Opaque to us. The records call it an encrypted representation of the model's reasoning (R-13, A-25). We cannot inspect or audit it | Yes, by the provider for the provider | As class 1 | None. Redacting it would corrupt it (loop.py:111) |
| **3. Ordinary assistant messages** | Gemini: verbatim model `Content`, because signatures can sit on any part (N-15, NG-2). Anthropic: store the full `content` array, including `text`, and replay it on every turn (Anthropic record :152, A-38). OpenAI and DeepSeek: no requirement to replay text verbatim is recorded | Model answer text and drafts. It may quote repository content | No | `Message.content`, which is redacted in `provider_view`. Also inside the Gemini `SignedTurn` | Redacted in `Message.content`. **Not redacted** inside the Gemini replay |
| **4. Tool calls and tool results** | Calls have ids, and results are paired by id (R-5/R-6, N-7, A-32/A-33, D-29). Anthropic and Gemini replay the model's own call blocks verbatim inside the turn | Calls: arguments written by the model (paths, grep patterns). Results: repository content | No | `Message.tool_calls` and `Message("tool")`. Also the `functionCall` parts inside the Gemini `SignedTurn` | Results and the loop's view of arguments are redacted. **The Gemini replayed arguments are not redacted**: test_gemini_generate.py:576-588 shows a secret-shaped `grep` pattern sent verbatim |
| **5. Signed reasoning blocks** | Anthropic `thinking` blocks (text plus `signature`) cannot be edited, reordered or partly dropped, and edits get a 400 (A-36). On 5.1+ models they are bound to an unchanged system prompt, tool list and earlier messages (A-38, A-39). A Gemini signature attached to a `text` or `functionCall` part binds that part (N-15) | Classes 1, 3 and 4 inside a signature envelope | Partly: the text is readable but integrity-bound | Gemini `SignedTurn`. Anthropic: none yet | None. Any change breaks the signature or the prefix check |

**Retention at the provider:**

- **OpenAI:** `store: false` (R-3, R-10).
- **Anthropic:**
  - Content is not retained by default.
  - Fable and Mythos "Covered Models" are retained for 30 days.
  - Flagged content may be kept for up to 2 years.
  - Content is not used for training without permission.
  - Sources: A-52, A-53, A-54, AG-8.
- **Gemini:**
  - Paid tier: content is logged "for a limited period" for abuse detection and is not used for training. The period is
    unstated (R-31, G-7).
  - Unpaid tier: content is used to improve products and human reviewers may read it (R-30).
- **DeepSeek:**
  - Data is stored in the PRC.
  - User Input is used to "train and improve" the models. Opting out takes a request to the privacy contact.
  - Input is retained while the account exists.
  - Whether these terms apply specifically to API prompts is not stated.
  - Sources: D-39, D-41, D-42, DG-6.

## 3. What the code does today

**OpenAI** (offline codec; product selection refuses it, providers.py:29-31):

- `decode` keeps `reasoning` items that have an `id` and an `encrypted_content`, but only when the response contains
  calls (openai_responses.py:139-142, :158).
- `encode` emits them before that turn's calls and refuses any other item in the replay channel (:58-61, :182-192).
- The whole item dict is replayed, including any `summary`, which is class 1.
- Gaps in the current implementation:
  - **No binding.** Nothing ties a replayed item to its model, conversation or exchange. Any dict with the right shape is
    accepted.
  - **The replay is not masked.** It is plain dicts inside a frozen dataclass whose default `repr` would print them.
  - **Text turns drop the replay** (:158).

**Gemini** (used only in the benchmark model mode):

- `decode` wraps the model's entire `Content` in a `SignedTurn` (gemini_generate.py:56-70, :272-274). The `SignedTurn`
  is:
  - authenticated with an HMAC key kept per codec instance (:81, :95-99);
  - bound to the model, the conversation epoch and the digest of the request that produced it (:101-111);
  - consumed on decode (:214);
  - checked against the validated tool calls (:197-207);
  - masked in `repr` and `str`, and refuses pickling and copying (:64-70).
- The `SignedTurn` contains classes 1 through 5, unredacted.
- Gaps in the current implementation:
  - **Tool-call turns only.** Replay is accepted only on a turn with tool calls (:153-154).
  - **The repair turn has no replay** and is truncated to 2,000 characters (loop.py:271).

**Loop:** replay is attached only to tool-call turns (loop.py:238).

**So, for O-5:**

- OpenAI and Gemini already depend on this exception.
- Anthropic and DeepSeek would widen it in two ways:
  - Replay would be needed on every assistant turn, including text and repair turns (A-38, D-26).
  - DeepSeek would add a plaintext class 1 that no signature protects.

## 4. Privacy analysis: can replay contain unredacted secrets?

1. **Where replay comes from.** Every replayed byte comes from the same provider's own response:
   - decoded content (gemini_generate.py:233-274, openai_responses.py:139-142);
   - for DeepSeek, `message.reasoning_content` (D-22).

   Tracewise adds nothing to it. The provider authored it from inputs that were redacted under P-2, plus its own
   training.
2. **Secrets that reach replay in readable form.**
   - Redaction catches pattern-shaped secrets. A recognisable secret in the replay can therefore only come from one of
     three places:
     - a P-4 miss that the model decoded or reassembled;
     - the model's memorised knowledge;
     - the model copying a value that redaction does not match.
   - In every case, the provider has already seen the underlying material, encoded or not, and has already emitted the
     readable form in its response.
   - Replay discloses **no new information to that provider**.
3. **Exposure replay still adds.** It is not about who learns what. It is about how the content is classified and kept:
   - **Provider side:** the content is transmitted again as request input. Request logs and retention rules may treat
     it differently from response output. DeepSeek's training clause covers "User Input" (D-41). Gemini's unpaid tier
     allows human review (R-30).
   - **Tracewise side:** a plaintext copy is held in memory. If it were logged, persisted or shown, it would bypass P-2
     on a channel aimed at people. That is the main risk to control, and the reason the rules below matter more than
     the provider question.
4. **Content we cannot audit.** Class 2 content cannot be inspected, so we cannot verify what it holds. That is
   acceptable only because it goes back to its issuer, and only in that direction.
5. **Should DeepSeek's reasoning be redacted?**
   - DeepSeek's class 1 has no signature. In principle P-2 could be applied before replay.
   - But "fully passed back" (D-26) and DG-5 leave the effect of altering it undocumented.
   - Redaction would also cut no disclosure to the provider, per point 2.
   - **Recommendation:** replay it verbatim, and rely on the provider-approval gate (§6) instead.

## 5. Security analysis

- **Cross-tenant replay is the real threat.** Tracewise investigates runs for many installations. If state from
  investigation A were replayed into investigation B, A's repository-derived reasoning would reach the provider inside
  B's request, and could also influence B's output, which B's owner then reads. Binding to the conversation and
  attempt prevents this. The Gemini epoch and HMAC already do it (gemini_generate.py:101-111, :192-193); OpenAI does
  not.
- **Integrity.**
  - The HMAC protects against bugs in our own loop and stale state. It does not protect against an attacker inside the
    worker process, which is out of scope.
  - The provider's signatures (A-36, N-16) protect the provider. They are not a guarantee to us.
- **Prompt injection through reasoning.**
  - Repository content may steer the model's reasoning, and replay hands that reasoning back to the model.
  - This opens no new path to tools: tools run only from the loop's validated `tool_calls` (loop.py:240-259), and the
    replay is checked against those calls (gemini_generate.py:197-207).
  - Reasoning text is never answer text (gemini_generate.py:257-258) and never reaches `parse_draft` or `validate`.
  - Codecs that keep class 1 must keep those properties.
- **Divergence.** The bytes replayed to the provider must never describe a different action from the one the loop
  executed. That is why the consistency check is mandatory (MODEL-ADAPTER.md:261-262).

## 6. The proposed policy, point by point

| # | Proposed rule | Verdict | Reasoning and change |
|---|---|---|---|
| P1 | Replay only when the provider's documented protocol requires it | **Accept with change** | Each codec must name the record fact that requires replay: R-10, N-16, A-35/A-38, D-26. Include state that is "needed to keep required state valid". Anthropic's "Recommended" cross-turn replay is effectively required on 5.1+ models because of the prefix check (A-38). An unrecorded requirement means no replay: fail closed or ask for a new record |
| P2 | Preserve it exactly | **Accept** | Keep each value identical to what was decoded: no normalisation, truncation or re-encoding of strings. Gemini signatures are strings, so serialising them back to JSON keeps the values. Remove the 2,000-character truncation of the repair turn for anything that is replayed (loop.py:271). Truncate only what is logged |
| P3 | Bind to the same provider, model, conversation and attempt | **Accept with change** | Also bind to the **exchange**, meaning the request digest, and require one decode per encode, as Gemini already does (gemini_generate.py:91-111, :214). The attempt binding means one codec instance, and so one HMAC key, per investigation attempt; a retried job starts a new conversation (MODEL-ADAPTER.md:94). OpenAI must adopt the same binding |
| P4 | Never treat it as evidence for a diagnosis | **Accept** | Reasoning and signatures never reach `parse_draft`, `validate`, confidence, `files_examined` or the fix. Only tool results count as evidence |
| P5 | Never expose it in reports, UIs or ordinary logs | **Accept with change** | Widen this to any log level, exception messages, `WireError` text, benchmark outputs, the database, `last_error` and test snapshots. Mask `repr` for every codec. Today only Gemini masks it (gemini_generate.py:64-67) |
| P6 | Never replay it across providers or unrelated conversations | **Accept** | Already enforced for Gemini (:105-110), and the OpenAI codec refuses a `SignedTurn` (MODEL-ADAPTER.md:271-272). Make the refusal symmetric across all codecs |
| P7 | Strict limits on size, access and retention | **Accept with change, with numbers** | Size: a byte cap per replay envelope and per conversation. Over the cap fails closed as `provider_failed`. Suggested starting points, for the owner to set: 64 KiB per turn and 192 KiB in total, inside the existing 256 KiB request cap (bench/model_provider.py:51). Access: only the codec that minted the envelope can open it. Retention: the lifetime of one `investigate()` call |
| P8 | Avoid persistence | **Accept with change: "prohibit"** | "Avoid" is too weak. Never persist it to the database, files, queues or caches. The envelope refuses serialisation, pickling and copying (gemini_generate.py:69-70) |
| P9 | Never reconstruct or modify signed state | **Accept, and extend** | Apply this to all replay, including DeepSeek's unsigned plaintext: no redaction, editing, reordering, partial dropping or synthesis (A-36, A-38, N-16, D-26) |
| P10 | Fail closed on errors | **Accept** | Any verification, binding, cap or consistency failure raises `WireError`. The result is an inconclusive outcome (`provider_failed`), never a guessed diagnosis (loop.py:219-227) |
| P11 | *(added)* Check consistency between the validated calls and the replayed calls | **Add** | The replayed call blocks must exactly match the loop's validated `tool_calls` (ids, names, arguments and order), as gemini_generate.py:197-207 does |
| P12 | *(added)* Separate approval per provider | **Add** | DeepSeek needs a separate owner approval for PRC storage and training (D-39, D-41, DG-6), on top of O-5. Gemini needs paid-tier confirmation (R-30 to R-32). Anthropic needs confirmation of ZDR or Covered Model status (A-53, AG-8) |

## 7. Where each provider stands

| Provider | Exception needed? | Status today | Change required by O-5 |
|---|---|---|---|
| OpenAI | Yes (R-10) | Replays reasoning items, including any `summary`, unredacted, on tool turns, unbound (openai_responses.py:58-61, :139-142, :158) | Ratify it, then move to a generalised signed envelope with masked `repr`. Text-turn replay is [UNRECORDED] (design :99), so keep tool-turn-only until it is recorded |
| Gemini | Yes (N-15 to N-17) | Replays the whole model `Content` (classes 1 to 5) as a `SignedTurn`, bound and masked (gemini_generate.py:56-111, :197-207, :272-274) | Ratify it. Add text-turn and repair-turn replay only if NG-2 is resolved; today repair fails closed (MODEL-ADAPTER.md:274-276) |
| Anthropic | Yes (A-35 to A-39) | No codec | Replay the full `content` array verbatim on every assistant turn, including the repair turn. `provider_view` must produce a byte-identical system prompt, tool list and earlier messages at every step (A-38). Provider retention gate: A-53, AG-8 |
| DeepSeek | Yes (D-26, D-27), when tools are sent, which is every investigator request after design step 2 | No codec | Replay `reasoning_content` verbatim on every earlier assistant turn, including when `tool_choice: "none"` is sent (DG-7). **Separate gate for PRC storage and training (P12)** |

## 8. How to enforce it

1. **Generalised `ReplayEnvelope`.** Move `SignedTurn` into a shared module.
   - Fields: provider, model, epoch, request digest, opaque payload, and an HMAC over all of them.
   - It has a masked `repr`, refuses `__reduce_ex__`, and only its codec can open it.
   - `Message.replay` takes `tuple[ReplayEnvelope, ...]`, and the loop type-checks that it holds nothing else.
2. **Fixed exemption list in `provider_view`.** The *only* fields that skip `redact` are listed in §9. The loop asserts
   that `replay` contains only envelopes.
3. **Loop changes for design step 1.**
   - Attach `resp.replay` to every recorded assistant turn, including the repair turn.
   - Never truncate replayed content.
   - Truncate the 2,000-character copy only for logging (loop.py:271).
4. **Caps.** `MAX_REPLAY_BYTES_PER_TURN` and `MAX_REPLAY_BYTES_PER_CONVERSATION` are checked in `decode` and `encode`.
   Exceeding either raises `WireError`.
5. **Observability.**
   - Logs may contain only counts and sizes: the number of envelopes, the bytes per turn, the replay class present (for
     example `reasoning_tokens` from usage), and the verification outcome as a fixed code.
   - Logs must never contain content, signatures, item ids or digests.
6. **Per-provider approval switch.** Product selection (`providers.py`) stays closed. Enabling DeepSeek requires a
   separate, recorded owner approval.

## 9. Text to add to DATA-INVENTORY (if O-5 is accepted)

**Replace the "Model provider" row (docs/DATA-INVENTORY.md:38), protection column:**

> Everything Tracewise sends is redacted at the provider boundary (`investigate/loop.py::provider_view`; P-2, approved
> option A), with one exception (O-5, approved <date>). **Provider-issued continuation state** (`Message.replay`) is sent
> back verbatim and unredacted, only to the provider, model and conversation that issued it. It covers OpenAI
> `reasoning` items (`encrypted_content`, `summary`); the Gemini model `Content` with its `thoughtSignature`s, including
> its text and `functionCall` parts; Anthropic `thinking` (text, `signature`), `redacted_thinking` (`data`) and the
> turn's `text`/`tool_use` blocks; and DeepSeek `reasoning_content`. This state is authored by the provider from
> redacted input. It can quote repository content, and it can contain a secret that redaction missed (P-4) in readable
> form, but never data the provider did not already return. It is held in memory only, for one investigation attempt,
> inside an authenticated envelope that cannot be serialised. It is capped at <N> KiB per turn. It is never logged,
> persisted, rendered, published or used as evidence, and it is never sent to another provider, model or conversation.
> Any failed check ends the run as `provider_failed`. Provider-side retention and training terms: OpenAI `store: false`
> (R-10); Anthropic A-52 to A-54; Gemini paid tier only (R-31, R-32); DeepSeek requires separate approval for PRC
> storage and training (D-39, D-41).

**Replace the stage-3 row (DATA-INVENTORY.md:58), "Redaction and limits" column:**

> Everything redacted at the provider boundary (P-2), **except** provider-issued continuation state (O-5; see §3).

**Correct three other documents to match:**

- The `Message.replay` comment, provider.py:26-27.
- The `provider_view` docstring, loop.py:100-104.
- MODEL-ADAPTER.md:91-96, which says the replay channel carries only reasoning items. It also carries Gemini turns.

## 10. Tests required before the Anthropic and DeepSeek codecs ship

Most of these belong in the shared contract suite, tests/investigate/test_codec_contract.py, parametrised over every
codec.

1. Replay is present on the next request after **every** assistant turn: tool calls, text, and the repair turn (design
   step 1).
2. Byte and value identity: the replayed payload equals the decoded payload, and the repair turn is not truncated.
3. Tampering is refused: one changed character in the thinking text, `signature`, `data`, `reasoning_content`,
   `encrypted_content` or `thoughtSignature`.
4. Binding is enforced. A replay is refused when it comes from:
   - another codec instance or model;
   - another provider (all pairs, symmetric);
   - another conversation or epoch, including a reconstructed identical history;
   - a second decode for the same encode;
   - another position in the same conversation.
5. Consistency: replayed `tool_use`/`functionCall`/`tool_calls` must match the validated calls exactly, and any
   mismatch is refused.
6. Caps: a replay over the per-turn or per-conversation cap is refused unsent and ends as `provider_failed`.
7. Masking: the envelope's `repr` and `str` are masked; `json.dumps`, `pickle`, `copy` and `deepcopy` raise.
8. Non-exposure, using a canary planted in the reasoning, thinking and signature fields: it does not appear in
   - log records at any level (caplog),
   - exception messages,
   - `InvestigationResult`,
   - the diagnosis,
   - database rows,
   - rendered reports,
   - benchmark outputs.

   Extend `test_privacy_flow.py` and the canary pattern in test_gemini_generate.py:420.
9. P-2 still holds outside the exemption: a secret planted in a tool result or user message is redacted in the
   serialised bytes, while a secret-shaped string authored by the model appears only inside the exempt replay field.
   This extends `test_model_input_privacy.py`.
10. Anthropic: the system prompt, tool list and earlier messages are byte-identical between step *n* and step *n+1*,
    which shows that `provider_view` is deterministic (A-38). The tool-free step sends `{"type": "none"}` with the same
    tools (A-17, A-40).
11. DeepSeek: every earlier assistant turn carries `reasoning_content` whenever `tools` is sent, including the
    `"none"` step (D-26, DG-7). A missing `reasoning_content` fails closed before sending.
12. Reasoning is not answer text: thinking or `reasoning_content` never reaches `parse_draft`, and a response that has
    only reasoning is not an answer.
13. Selection: `providers.py` refuses `anthropic` and `deepseek`, and DeepSeek stays refused until its separate
    approval is recorded.

## 11. Recommendation

**Accept with conditions.**

- **What to approve:**
  - The rules P1 to P12 as amended in §6.
  - The exemption list and DATA-INVENTORY text in §9.
- **What this ratifies:** the OpenAI and Gemini replay that exists today, with OpenAI moved onto the envelope.
- **Conditions before the Anthropic and DeepSeek codecs ship:**
  - §8 is implemented.
  - The tests in §10 pass.
- **DeepSeek also needs** its separate owner decision on PRC storage and training (D-39, D-41, DG-6).
- **If the owner rejects the proposal:**
  - Anthropic 5.1+ models and DeepSeek with tools cannot be used at all (A-38, D-27).
  - Gemini thinking models fail with `MISSING_THOUGHT_SIGNATURE` (N-17).
  - The existing OpenAI and Gemini replay would have to be removed.

---

## 12. Final provider-state contract (2026-11-01, fourth batch; for owner decision)

This section condenses §2–§11 into the contract a codec must meet. Nothing here is implemented beyond what §3 already
describes. The Anthropic and DeepSeek codecs are **not** started.

### 12.1 What a provider response may contain, and how each kind is handled

| Kind | Examples | Evidence? | Shown to users? | Logged? | Persisted? | Replayed? |
|---|---|---|---|---|---|---|
| Assistant text | the JSON answer, repair answers | Only after `parse_draft` and validation; never itself evidence | Only validated fields, through `render` (redacted) | No (sizes only) | Validated diagnosis only | As text, redacted by `provider_view` |
| Tool calls and arguments | `read_file` path and range | No; only the tool **results** are evidence | No | Tool name, status, category (`tool.error`) | No | Yes, redacted, and must equal the validated calls (P11) |
| Continuation state | OpenAI reasoning items, Gemini thought signatures, Anthropic `thinking`/`redacted_thinking` blocks, DeepSeek `reasoning_content` | **Never** | **Never** | **Never** (not at any level, not in exception text) | **Never** (P8: prohibited) | Exactly as received, only where the provider requires it, only within the same provider, model, investigation and attempt |
| Hidden reasoning text | thought summaries, `reasoning_content` plaintext | Never | Never | Never | Never | Only as part of the continuation state above |
| Usage metadata | totals, cached input, reasoning output | No | Totals in the report footer (existing) | Counts only | Counts only (`analysis`, migration 0014); NULL when not reported | No |
| Provider error information | HTTP status, error type | No | No (a fixed "could not complete" text) | Type and status code only, never the body | No (`last_error` is content-free) | No |

### 12.2 The ten requirements from the request, mapped

| Requirement | Rule | Enforced today |
|---|---|---|
| Opaque protocol data only where necessary | P1 | OpenAI (tool turns), Gemini |
| Not repository evidence | P4 | Yes: replay never reaches `parse_draft` or the validator |
| Never in reports | P5 | Yes |
| Never in ordinary logs | P5 | Gemini masks `repr`; **OpenAI items are plain dicts: a careless log of a `Message` would print them** (gap) |
| Bound to provider, model, investigation, attempt | P3, P6 | Gemini (HMAC per conversation epoch); **OpenAI unbound** (gap) |
| No cross-provider or cross-investigation replay | P6 | Gemini refuses foreign turns; OpenAI refuses a `SignedTurn` |
| No reconstruction or modification | P2, P9 | Yes for both; repair-turn replay is not used (fails closed) |
| Restricted access and retention | P7, P8 | In memory for one `investigate()` call only; nothing under `db/` or `jobs/` touches replay |
| Oversized or malformed state fails safely | P7, P10 | Response size cap (1 MB) and `WireError`; **no per-envelope byte cap yet** (gap) |
| Avoid persistence | P8 | Yes (prohibited, and true today) |

### 12.3 Provider compatibility matrix

| | OpenAI (Responses) | Gemini (generateContent) | Anthropic (Messages) | DeepSeek (chat) |
|---|---|---|---|---|
| Codec exists | Yes (smoke/bench only, disabled in product) | Yes (bench only) | No | No |
| Continuation state | Encrypted reasoning items (R-10) | Thought signatures on parts (N-15–N-17) | Signed `thinking` blocks (A-35–A-39) | Plaintext `reasoning_content` (D-26, D-27) |
| Must replay on | Tool-call turns (text turns unrecorded) | Every model turn with a signature | Every assistant turn (prefix check, A-38) | Every assistant turn when tools are sent |
| Engine support (`ENGINE_REPLAY_SCOPES`) | Yes | Yes | **Refused** until loop design step 1 | **Refused** until loop design step 1 |
| Binding/masking | Gap: unbound, unmasked | HMAC-bound, masked | Needs the shared envelope (§8) | Needs the shared envelope (§8) |
| State is readable plaintext? | No (encrypted) | Mostly opaque signatures plus text | Signed; may include summarised thinking | **Yes**: raises the log/persistence risk |
| Usage breakdown fields | cached, reasoning (documented) | cached, thoughts, tool-use prompt | cache read/creation (not mapped yet) | cache hit/miss, reasoning (not mapped yet) |
| Separate data-handling gate | Org data controls (existing) | Paid tier confirmation (R-30–R-32) | ZDR or Covered Model status (A-53, AG-8) | **PRC storage and training use (D-39, D-41, DG-6)** |

### 12.4 DeepSeek: a separate approval gate

The research record supports only these statements:
- The operator is a PRC company, and its terms are governed by PRC law (D-39).
- The privacy policy says personal data is collected, processed and stored in the PRC, and that user input is used for
  training, with an opt-out by request (D-41).
- The API terms state neither the data location nor whether API content is used for training (D-40).

Still unknown and needing authoritative confirmation (DG-6):
- whether API content (not the consumer app) is retained or used for training;
- whether any non-PRC processing or zero-retention option exists;
- whether a data-processing agreement is available.

Tracewise sends redacted log excerpts and repository code to the provider, so this is a data-transfer decision for the
owner, independent of O-5. **Recommendation:** do not enable DeepSeek, even after a codec exists, until the owner
records that decision. Keep `providers.py` closed to it.

### 12.5 Recommendation

Accept §6 (P1–P12) as the contract. Before any Anthropic or DeepSeek codec, close the three OpenAI/engine gaps in §12.2:
- the shared envelope with binding and masked `repr`;
- per-envelope and per-conversation byte caps;
- replay on every assistant turn (loop design step 1), with tests (§10).

### 12.6 Update (2026-11-02): §12.2 gaps closed in the shared engine

- **Binding:** every provider's state, OpenAI's included, is sealed per step in `investigate/replay.py`. It is bound to
  provider, model, tenant, job, job attempt and a random investigation id.
- **Masking:** `Message.replay` and `StepResponse.replay` are excluded from `repr`, and envelopes are masked.
- **Caps:** 64 KiB per envelope and 192 KiB per conversation. Oversized state is refused, never truncated.
- **Every-turn replay:** supported through `replay_scope` (`all_turns`).

Tests: `tests/investigate/test_replay.py`. The OWNER decision on the policy itself, and the per-provider data gates
(§12.3, §12.4), are unchanged. No Anthropic or DeepSeek codec exists.
