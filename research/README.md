# Research index

**Not a source of truth for implementation.** The canonical documents are in [../docs/](../docs/README.md).

This folder keeps dated records that the code cites: the recorded contracts of the model APIs (the codecs map every
field to a fact in these records), and the implementation-gap report with its decision notes.

| Path | What it is | Status |
|---|---|---|
| `openai-api-reference-2026-10-19/` | Recorded OpenAI Responses API contract (R-1…R-14, gaps G-1…G-8) | Dated record |
| `gemini-api-reference-2026-10-26/` | Recorded Gemini API contract: compatibility layer, native `generateContent` (Addenda A–C) | Dated record |
| `anthropic-api-reference-2026-11-01/` | Recorded Anthropic Messages API contract (A-1…A-54, gaps AG-1…AG-8); no codec exists | Dated record |
| `deepseek-api-reference-2026-11-01/` | Recorded DeepSeek chat completions contract (D-1…D-43, gaps DG-1…DG-9); no codec exists | Dated record |
| `product-strategy/` | Verified implementation-gap report and decision notes (2026-10-30 onward) | Proposals for the owner; not decisions |

Earlier market and competitor research, the original planning set and their evidence were removed from the repository
on 2026-11-21 and are kept privately by the maintainer. Older documents (notably `docs/CHANGELOG.md` and
`docs/DOC-CHANGE-PLAN.md`) still name some of those paths as plain text; they no longer exist here.
