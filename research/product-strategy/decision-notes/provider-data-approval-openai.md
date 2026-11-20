# Approval needed before the first real OpenAI call (staging gate G)

- **Date:** 2026-11-02
- **Status:** For owner decision. Nothing here enables a provider. `LLM_PROVIDER=openai` is refused at startup
  (`src/tracewise/investigate/providers.py`).
- **Basis:** the code as it stands, plus `research/openai-api-reference-2026-10-19/` (R-1 to R-14) and
  `docs/MODEL-ADAPTER.md`. Account-level settings are not recorded anywhere in this repository.

## 1. What Tracewise would send to OpenAI (per investigation step)

| Data | Included | Filtering before it leaves |
|---|---|---|
| System prompt (fixed text) | yes | — |
| Evidence bundle: failed jobs and steps, primary error lines and short excerpts of the GitHub Actions log, the trigger diff | **yes: log-derived** | Pattern-based redaction of every message (`loop.provider_view`, P-2): tokens, keys, URLs with credentials and other secret shapes. Pattern-based: encoded, split or unfamiliar secrets can pass (P-4) |
| Tool results: source windows (≤250 lines, ≤8000 chars per call), grep lines, directory listings, the diff | **yes: repository code** | Same redaction; read-only tools, path and symlink rules, read budgets |
| The model's own earlier turns and tool-call arguments | yes | redacted |
| OpenAI reasoning items (`encrypted_content`) | sent back only to OpenAI, unchanged (R-10) | not redacted (opaque, provider-issued); bound, capped and masked (O-5, `investigate/replay.py`) |
| Repository secrets, webhook bodies, tokens | no | never read or sent |

The request sets `store: false` (R-3: the default is true). No organisation or project header is sent.

## 2. Not established, needing the owner before the first call

1. **Account data retention and training settings** (MODEL-ADAPTER C-8): whether API inputs are retained for abuse
   monitoring, for how long, and whether zero data retention applies to the account or project. These are account
   configuration, not code. Record the confirmed settings (date, who confirmed) in the privacy notice §4.
2. **Data residency and the contract**: the legal entity, region and data-processing terms. The privacy notice §10
   lists these as open items.
3. **The model id and its price** (C-9): needed for `LLM_PRICE_*` (cost is otherwise recorded as unpriced) and for
   the per-analysis cost bound.
4. **The O-5 policy** (decision note §11): approval to send reasoning items back unredacted.
5. **Which repository's data may be sent:** the disposable `tw-live` fixture repository only, for staging.

## 3. Keys and records

- **The key:** lives only in the worker's environment file in the secrets directory (mode 600; `OPENAI_API_KEY`). It
  is registered with the log scrubber (`secret_filter.register`). It is never logged, never in a URL, never in chat.
- **What Tracewise records:** per analysis, the provider name, model, token totals, cached and reasoning subsets (or
  NULL), latency, the outcome, and the cost when priced. Operational logs carry event names, ids, counts, sizes and
  outcomes, never prompt or response content.

## 4. The code change that the approval unlocks (not made)

`provider_factory` would build `HTTPProvider(OpenAIResponsesWire(model), AdapterConfig(...), key)` for
`LLM_PROVIDER=openai`, instead of refusing. That is one function plus its test (`test_process_entrypoints.py`
expects the refusal today). It should be made only together with the approval above.

## 5. Gate D decision packet (2026-11-02)

**Public facts.** Official page "Data controls in the OpenAI platform" (developers.openai.com/api/docs/guides/your-data,
read 2026-11-02; no date shown on the page):
- API data is not used to train OpenAI models unless the organisation opts in.
- Abuse-monitoring logs are kept up to 30 days, unless the law requires longer.
- Zero Data Retention and Modified Abuse Monitoring need OpenAI's prior approval and are set per organisation, with
  project overrides.
- Responses application state is kept 30 days by default and when `store=true`. Tracewise sends `store: false`; under
  Zero Data Retention it is always treated as false.
- Data residency is configured per project. Non-US regions also need abuse-monitoring approval and an amendment.

These describe the platform. They do **not** say what this account has.

| # | Decision or fact | Status | Owner action |
|---|---|---|---|
| D1 | Organisation's training opt-in state | **Owner confirmation** (account-specific) | Confirm "not shared" in the organisation's data controls; record the date |
| D2 | Retention mode (default 30-day abuse monitoring, Modified Abuse Monitoring or Zero Data Retention) | **Owner confirmation** | Confirm which applies; the privacy notice §4 must state it |
| D3 | Project region and the contract that governs it | **Owner confirmation** | Name the project, region and agreement |
| D4 | Model | **Owner decision** | One id; the codec refuses malformed ids; no fallback |
| D5 | Price | **Owner decision**, read from the official pricing page at decision time | Set `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK`. Cached input stays unpriced (cost "unavailable") unless a cached price is added later |
| D6 | Provider-state policy (O-5) | **Owner decision** | Accept §6 P1–P12 or not. Without it, reasoning models cannot be used |
| D7 | Staging volume | **Owner decision** | Number of analyses (gate D cards: about 7), on `tw-live` only |
| D8 | Token and cost budget | **Owner decision** | Worst case per analysis: ≤16 steps and ≤200,000 tokens per attempt, × ≤3 attempts. Optionally a lower staging `max_total_tokens` |
| D9 | Filtering | Implemented: pattern redaction of everything sent except provider-issued replay (§1); not exhaustive (P-4) | Accept the residual risk for the fixture repository |
| D10 | Enabling change | Not made | Approve the change below |

**The enabling change, restricted to staging (not implemented):**
1. Add `OPENAI_MODEL` to `Settings`.
2. In `provider_factory`, build `HTTPProvider(OpenAIResponsesWire(model), AdapterConfig(model=model), key)` **only when**
   `TW_ENV=staging`, `OPENAI_MODEL` is set and `OPENAI_API_KEY` is present. In every other environment the refusal
   stays as today. A production enablement is a separate change after gate E.
3. Tests: the refusal outside staging; construction in staging with a fake transport (no network); the key never in
   the output. About 30 lines plus tests.
4. The key goes into the worker env file on the staging host only (mode 600). Never in chat or the repository.
5. Staging today runs `TW_ENV=test`, which the fake provider requires (gates A–C). Gate D switches only the worker's
   environment file to `TW_ENV=staging` plus the OpenAI settings, and back to `test` afterwards (rollback).
