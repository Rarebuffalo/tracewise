# OpenAI smoke evaluation runbook (prepared in Phase 47; NOT executed)

**Status:** prepared and rehearsed offline only. No key has been used and no request has been made. Running it
needs every item in §1. The harness is [`scripts/openai_smoke.py`](../scripts/openai_smoke.py); its offline tests are
`tests/investigate/test_openai_smoke_harness.py`.

**What it is for:** checking that the recorded Responses contract
([research/openai-api-reference-2026-10-19/README.md](../research/openai-api-reference-2026-10-19/README.md)) matches the real
endpoint. **What it is not:** evidence of diagnosis quality, model accuracy, latency or cost at scale. That is T-605,
which is approved separately.

## 1. Owner authorisation checklist

### Required before the smoke call (all of them)

| # | Item | How it is supplied |
|---|---|---|
| A-1 | Written authorisation for **one** smoke evaluation, at most 3 HTTP requests | A reference string (date and approver) passed as `--authorization-ref` and recorded in the evidence |
| A-2 | The exact model identifier, with its source (UD-3) | Passed as `--model`. There is no default and no fallback; the harness never substitutes another model |
| A-3 | A **project-scoped** OpenAI API key | A file outside the repository, `chmod 600`, passed as `--key-file`. **Never** in chat, never printed, never committed, never in a `.env` file, never in an environment variable (the harness does not read the environment for keys) |
| A-4 | Confirmation of the OpenAI account's data-retention and training settings (C-8) | The owner, in writing. The harness also sends `store: false` |
| A-5 | Approval of the synthetic request content in §3 | The owner, in writing |
| A-6 | Approval of the exact command in §2 | The owner, in writing |
| A-7 | The expected cost and request limit in §4 | The owner fills in the per-token prices (G-6) and accepts the bound |

### Required after the smoke call, before a real evaluation

- The evidence shows that the endpoint accepts the requests and returns the recorded shapes (G-4), including tool-call ids (G-5), reasoning items (G-8) and the tool-free final step (G-7).
- If any check fails: a codec change, with regression tests, before anything else.
- A decision on the model, limits and pricing (C-9, G-6, UD-3).
- **Separate** approval to wire `LLM_PROVIDER=openai` in `investigate/providers.py`.
- **Separate** approval to run the T-605 evaluation (benchmark with the real model, E-01, cost and latency).

### Still required before a private pilot (independent of the smoke call)

- D-12 retention decisions.
- Confirmation of the provisional 0.2 alert threshold.
- **Signed URLs in `research/final-audit-public/evidence/marketplace.html`:** the query strings must be redacted before any push or publication. This file was not opened or edited in Phase 47; the remediation stays an owner decision (OWNER-DECISION-SHEET item 7).
- Benchmark decisions: B-04, A-05, A-04, B-12, D-5 and E-01.
- Database roles provisioned with separate credentials (D-11).
- G-PLAT-11, and the live GitHub stages S0–S5 ([LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md)).
- Hosting, TLS, scheduling, alert routing, and staging validation.
- The privacy notice and pilot terms, reviewed by counsel.

## 2. Command

Run from the repository, on the owner's machine, outside CI. Placeholders are in angle brackets.

```
uv run python scripts/openai_smoke.py --live --model <APPROVED_MODEL_ID> \
  --key-file <PATH_OUTSIDE_REPO, chmod 600> --authorization-ref "<DATE APPROVER REFERENCE>" > <EVIDENCE_PATH_OUTSIDE_REPO>.json
echo "exit=$?"
```

**Offline rehearsal** (no key, no network; already run in Phase 47):

```
uv run python scripts/openai_smoke.py --offline pass --model offline-model
```

**The harness refuses (exit 2, nothing sent):**
- under pytest or with `CI` set;
- without `--key-file` and `--authorization-ref`;
- a key file that is group- or world-readable, a symlink, larger than 512 bytes, or inside the repository;
- a malformed model id or authorisation reference;
- offline mode combined with either live option.

The harness is not imported by product code and is not referenced by `make`, pytest's collection or the benchmark (structural test `test_the_harness_is_unreachable_from_product_code_and_standard_commands`).

## 3. The requests and their content

The content is fixed in the script and synthetic: no repository source, logs, credentials, customer data or benchmark material. Instructions: "You are a test fixture for an API compatibility check…".

| Step | Sends | Checks |
|---|---|---|
| 1 `text` | Instructions plus "Reply with exactly the two letters OK…"; no tools | Authentication, request serialisation, a `completed` response, `usage` (G-4) |
| 2 `tool_call` | Instructions plus "Call the list_dir tool… path `docs`"; the product's 4 read-only tool declarations (`strict: false`) | A `function_call` with a string `call_id` and arguments; reasoning items with `encrypted_content` if the model emits them (G-5, G-8) |
| 3 `tool_result_without_tools` | Step 2's conversation, the reasoning items and calls passed back **unchanged**, a synthetic `function_call_output` (`README.md`, `GUIDE.md`), "Now reply… OK"; **no `tools`** | The endpoint accepts earlier calls without `tools` (G-7), exact id pairing (G-5) and reasoning replay (R-10) |

Every request uses the product's codec and adapter unchanged, with `store: false`. Each response is validated by the codec: any non-`completed` status, refusal, unknown item, missing usage, malformed call or reasoning item without `encrypted_content` fails closed.

## 4. Limits and cost

| Limit | Value |
|---|---|
| HTTP requests | **at most 3** (enforced by the guarded transport); `max_retries = 0` |
| Request size | 32 KiB |
| Response size | 256 KiB |
| `max_output_tokens` | 2,048 per request |
| Time | 30 s per step; 90 s overall |
| Host | only `POST https://api.openai.com/v1/responses`; any other URL is refused in-process; no redirects; proxy environment ignored |

**Cost bound:** at most 3 requests × (under 1,500 input tokens + at most 2,048 output tokens), so under 4,500 input and 6,144 output tokens in total. The prices are not recorded (G-6). The owner multiplies these bounds by the approved model's prices (A-7).

## 5. Evidence: recorded and discarded

**Recorded** (one JSON document on stdout):
- mode, model id, authorisation reference, limits, start time;
- per step: accepted or not, text present and equal to `OK`, number of tool calls, whether they name a known tool, number of reasoning items kept for replay, and token usage;
- per exchange:
  - request byte size, top-level keys, `store`, tool count, `tool_choice`, `max_output_tokens`, input item types;
  - HTTP status and response byte size, top-level keys, `object`, `status`, `incomplete_details.reason`;
  - output item types: for reasoning items, whether `encrypted_content` is present and the summary part count; for function calls, the call id **length**, a known-tool flag, and whether arguments are a string;
  - usage token counts;
  - error `code`, `type` and key names, and rate-limit header **names**.

Enum-like values are recorded only if they match `[a-z0-9_.]{1,64}`; anything else becomes `<other>`.

**Never recorded:** the key or any header value, prompts, response text, tool arguments, call ids, reasoning items, `encrypted_content`, error messages, request bodies. Reasoning items stay in memory for step 3 only. If the serialised evidence would contain the key, the harness writes nothing and exits 2.

## 6. Outcome classes and success criteria

| Exit | Class | Meaning |
|---|---|---|
| 0 | `pass` | All 3 steps were accepted and decoded under the recorded contract, and steps 1 and 3 returned text |
| 2 | `refused` | Configuration or safety refusal; nothing (more) was sent |
| 3 | `transport` | Connection failure or timeout. Says nothing about the contract. |
| 4 | `auth` | 401/403 |
| 5 | `quota` | A documented quota or billing 429; never retried |
| 6 | `unavailable` | Rate-limit 429 or 5xx; not retried in the smoke run |
| 7 | `request_refused` | Other 4xx. At step 3 this would mean the answer to G-7 is "no". |
| 8 | `unsupported_response` | Malformed, incomplete, refusal, unknown shape or too large. The contract record or codec needs review. |
| 9 | `observation_missing` | The contract held, but the model did not call the tool, so G-5, G-7 and G-8 were not exercised |

**Success:**
- exit 0;
- `requests_sent` = 3;
- every exchange has `status: completed`;
- step 2 has a `function_call` with `arguments_is_string: true`;
- the evidence contains none of the excluded material.

**Anything else is a failure.** Record it and stop; do not retry without a new authorisation.

## 7. No other network activity or GitHub action

- The harness imports the codec and adapter only. It reads no database, GitHub App key or webhook secret, and no GitHub code path is reachable from it.
- The guarded transport refuses every URL other than the endpoint, and the HTTP client ignores proxy environment variables.
- Run it in a shell with no `DATABASE_URL`, GitHub App credentials or other tokens set. Optionally, observe the process's connections at the OS level (for example `ss -tp`): the only peer should be `api.openai.com:443`.
