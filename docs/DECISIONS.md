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
| D-1 | **Provisional validation hypothesis, not a finding and not an implementation gate** (clarified 2026-10-18). H-G2: "at least 15% of first-attempt red default-branch runs are, at job/step level, pre-existing or flaky." The denominator and measurement method are defined in [VALIDATION-PLAN.md](VALIDATION-PLAN.md) §3. The result informs the commercial decision together with G-1 and G-3. It never blocks or unblocks engineering tasks automatically, and it is never quoted as a market statistic. |
| D-2 | **Python is the backend implementation language for now** (FastAPI service, worker, investigation pipeline). TypeScript is added only where a concrete, written requirement justifies it; there is none today. No UI and no extra runtime or service without such a requirement and your approval. Customer repositories analysed: Python and TypeScript (extractors only). |
| D-3 | Quarantined evidence (`research/final-audit/evidence/`) stays **excluded from git** (`.gitignore`) and **untouched on disk**. It is never read as evidence, copied, moved or deleted. |
| D-4 | **Ambiguous PR association** (added 2026-10-18; flagged for your review). FS-PUB-7 defines no tie-break when several open PRs into the repo share the run's head SHA. Tracewise therefore does **not** pick one. On `ambiguous` (or a malformed PR-lookup response, `error`) it posts **no PR comment** and publishes on the push surfaces instead: a commit comment on the exact SHA plus the neutral Check Run, which can name the candidate PRs. This never comments on the wrong PR. Alternative if you prefer: comment on every candidate PR. |

## Open (need approval later; not needed for offline work)

| ID | Item | Needed by |
|---|---|---|
| O-1 | Approve a dedicated GitHub test org + dev App (you create; project-scoped) | T-801 (LIVE) |
| O-2 | Provide an OpenAI key in your local env for the measured evaluation | T-605 |
| O-3 | Optional head-to-head with The Plumber (AT-CMP-01) | Any comparative claim |
| O-4 | Hosting and pricing | Pilot (T-1002; after T-605 cost measurement) |
