# Plan Review

Date: 2026-10-15. Reviewer stance: adversarial, assuming the plan is wrong until shown otherwise.

## 1. Verdict

**VALIDATE FURTHER, then proceed with a narrowed build.**

- Execute Phase 0 now (≈8.5 dev-days over about 2 calendar weeks).
- Start Phase 1 only if G-0 passes (Plan §16).
- The engineering plan is buildable. The **commercial hypothesis remains unproven**, and the **timeline is longer than the 2–4-week target**:
  - ≈4.5 weeks of effort to the internal MVP;
  - ≈6.5 weeks of effort to a hardened paid pilot;
  - plus a 14-day soak, partly overlapping.

## 2. Contradictions found in the original research (and their resolution)

| # | Contradiction | Where | Resolution |
|---|---|---|---|
| C1 | "Webhook: no retry, GitHub redelivers" vs reality: GitHub does **not** auto-redeliver [NEW-V] | R-02 §B.2 | Reconciliation job (Plan §4.4.9); the 503 path is designed around it |
| C2 | "Read-only" product while requesting `checks:write` and `pull_requests:write` | R-02 B.6, R-06 §4, ExecSum | Precise wording; `pull_requests:write` dropped; Check-Run-only (ADR-06) |
| C3 | Validation thresholds disagree: 25%/15% vs 20%/10% | R-05 §3B/§6 vs R-07 §3 | Unified G-2 (≥20%, CI lower bound ≥15%) |
| C4 | "≥3 say they'd pay" treated as willingness-to-pay evidence | R-07 §3 | Replaced by written pilot terms (G-PAY) |
| C5 | Numeric calibrated confidence (0.82) without labeled data | R-02 §B.5 | Bands only |
| C6 | Data model includes patch diffs, while positioning excludes fixes | R-02 B.4 vs R-05 §5 | Patches removed (DR-30) |
| C7 | Raw logs stored 7 days in R2 vs privacy-first claims | R-02, R-06 vs R-06 §8 | Raw logs never persisted (ADR-04) |
| C8 | "3 weeks + 1 buffer" includes dashboard, OAuth, Slack, billing, LLM and backfill | R-06 §13 | Scope cut, re-estimated bottom-up at 22.5 + 9 dd |
| C9 | Zero-install public-repo teaser assumes anonymous log access | R-07 §4 | Anonymous download returns 403 [NEW-V]; the teaser becomes an authenticated CLI |
| C10 | Inference that The Plumber's commit comments need `contents:write` | R-01 §2 | GitHub's permission table lists commit comments under Contents **read** [NEW-V]. The inference was wrong; it has no impact on our plan. |
| C11 | B-16 assumes the tool proposes a fix | R-04 | Redefined as outcome tracking |
| C12 | B-04 / B-11 non-deterministic as specified | R-04 | Amended (attempt-based flaky failure; `-W error`) |
| C13 | Backfill of 50 runs on install vs on-demand history | R-06 §4 | On-demand (logs are retained 90 days by default [NEW-V]) |
| C14 | Default LLM "Sonnet" in R-06 vs the instruction not to choose a model by recency | R-06, ExecSum | Choose by eval among Haiku 5.5 and Sonnet 5.5 |

## 3. Scope risks

| Risk | Likelihood | Impact | Mitigation built into the plan |
|---|---|---|---|
| **Parser breadth explodes.** Every repo prints differently. | High | Coverage drops; schedule slips | Golden set from real logs (T3.09); a `generic` fallback; coverage gate ≥50% rather than 90% |
| **L5 import linking is harder than estimated** (path mapping, `src/` layouts, TS path aliases) | Medium | B-02-type cases become `INTRODUCED_IN_RANGE` | Acceptable degradation, explicitly listed in truth.yaml alternatives |
| **Lane semantics wrong for real workflows** (reusable workflows, `workflow_call`, monorepo path filters, merge queues) | Medium-high | Wrong last-green → false blame | `non_linear` and `no_baseline` abstentions; real held-out eval; monorepo path-filtered workflows flagged `[UNK]` until seen |
| **First-bad scan budget (≤5 logs) too small** on busy repos | Medium | More `possible` / partial | Stored signatures first; configurable `MAX_INTERMEDIATE_LOGS` |
| **GitHub log format assumptions** (step markers, runner header) | Medium | Splitter bugs | U-2 resolved in T3.01 on ≥20 real logs before building parsers |
| **Check Runs are less noticed than comments** | Medium | Low perceived value | Partner feedback; a PR-comment opt-in can be added later (ADR-06 migration) |
| **Single developer, calendar-bound items** (interviews, soak) | High | Timeline | Interviews start day 1; the soak overlaps Phase 6 work |
| **GitHub ships attribution** (CI Doctor productized, Copilot improvements) | Medium | Differentiation erodes | G-5 measures the gap now; positioning complements Copilot; the cross-tenant signal remains a later moat |

## 4. Weaknesses in this plan (self-critique)

1. **G-2 uses public OSS repos as a proxy for private 5–30-engineer teams.** OSS has more fork PRs, fewer secrets and different dependency hygiene. The bias direction is unknown. Mitigation: prefer repos owned by companies, and ask interviewees for one month of red-run history (anonymized counts) as a second sample.
2. **Single-labeler ground truth.** κ on a 20% re-label measures self-consistency only. If budget allows, a second labeler on 50 runs.
3. **The 12–15 interview sample is small.** Thresholds like "7/12" are heuristics, not statistics. They are kept because the alternative is no gate.
4. **G-5 depends on non-deterministic Copilot output** and could change next month. Each case is run twice and dated.
5. **Synthetic benchmark cases are built by us for our algorithm.** They prove mechanics, not usefulness. Hence the separate real held-out gate.
6. **Cost model token sizes are assumptions.** T4.03 and T4B record actuals, and the model is recomputed before pricing is offered.
7. **The plan does not cover how customers discover us** beyond R-07 outreach. Acceptable for 1–3 pilots, not for growth.

## 5. Meeting the 2–4-week target honestly

| Option | What it takes | What you give up |
|---|---|---|
| 4 weeks of effort → **internal MVP only** | Default plan, Phases 1–5 | No external customer yet |
| ≈5 weeks of effort → **fastest credible paid pilot** | Python-only; skip T6.11 (registry), T4B (LLM) and TS parsers; soak shortened to 7 days with one friendly partner who knows it's early; all security and deletion items kept | TypeScript teams; some confidence from a shorter soak |
| ❌ Shipping to a customer without RLS, deletion, reconciliation or security tests | — | **Not recommended**: holding others' CI logs without these is the riskiest shortcut |

## 6. What must be completed before implementation begins

1. **The user approves** this plan and answers OQ-02 (Phase 0 spend and activities).
2. **Phase 0 is executed:** T0.01–T0.07.
3. **The G-0 memo** records BUILD (or NARROW) with evidence:
   - G-1 ≥7/12 unprompted;
   - G-2 ≥20% (CI lower bound ≥15%);
   - G-3 ≥5 named-repo commitments;
   - G-5 native gap in ≥3/5.
4. OQ-01 (permissions) and OQ-04 (language scope) are decided from the Phase 0 data.
5. The dev GitHub App and the test org exist (R2, R5).

## 7. Final recommendation

**VALIDATE FURTHER.** Run Phase 0 starting with the first five tasks below.

The architecture is deliberately small, which keeps the cost of building low *if* validation passes:

- one Python service with a worker;
- Postgres only;
- a GitHub App with 4 permissions;
- Check Run output;
- a deterministic engine.

It also keeps the waste low if validation fails: the Phase 0 CLI and labeled dataset are useful either way.

**First five tasks after approval:**

1. **T0.06** Start interview outreach (calendar-critical).
2. **T0.01** Create the test org and fine-grained PAT.
3. **T0.02** Build the lab collector CLI.
4. **T0.04** Build the 5 G-5 benchmark cases with `truth.yaml` committed first.
5. **T0.03** Label 200 failed runs (with a 20% re-label for κ).

Then T0.05 (Copilot comparison) and T0.07 (gate memo).
