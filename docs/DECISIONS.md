# Decisions Log (canonical)

Replaces `research/archive/2026-10-15-s1-plan/OPEN-QUESTIONS.md`.

## Closed (2026-10-18, by the user)

| ID | Decision |
|---|---|
| Q1 | MVP scope = parity + attribution signal: AI diagnosis on by default after a deterministic pre-pass; bounded read-only investigation; evidence-grounded diagnosis; three publishing surfaces; API-based fork-aware PR association; least privilege; redaction; injection protection; limits; inconclusive fallback; synthetic benchmark + separate public-metadata track |
| Q2 | Neutral Check Run included, alongside commit and PR comments |
| Q3 | Python + TypeScript, with strict scope control (interpreted as D-2) |
| Q4 | OpenAI first, behind a provider interface. No keys during documentation or offline work. No claims until measured. |
| Q5 | Code in `~/tracewise`; no remote initially; inspect ignore rules and sensitive files before staging |
| Q6 | Conservative cleanup: archive, don't delete. Evidence and quarantined logs untouched. Doc 04 archived only after B-01…B-16 are consolidated and verified. |
| Benchmark sources (2026-10-17) | Synthetic + anonymous public metadata only. No personal or global credentials. No private repos. |

## Defaults applied (flagged; change them if you disagree)

| ID | Default |
|---|---|
| D-1 | G-2 is a metadata-only lower bound. ≥15% supports BUILD. Below 15% alone does not trigger ABANDON. |
| D-2 | Implementation is Python only (no TypeScript service). Customer repos supported: Python and TypeScript. |
| D-3 | `research/final-audit/evidence/` (contains quarantined data) is excluded from git via `.gitignore`. Files stay untouched on disk. |

## Open (need approval later; not needed for offline work)

| ID | Item | Needed by |
|---|---|---|
| O-1 | Approve a dedicated GitHub test org + dev App (you create; project-scoped) | T-801 (LIVE) |
| O-2 | Provide an OpenAI key in your local env for the measured evaluation | T-605 |
| O-3 | Optional head-to-head with The Plumber (AT-CMP-01) | Any comparative claim |
| O-4 | Hosting and pricing | Pilot (T-1002; after T-605 cost measurement) |
