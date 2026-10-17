# Executive Summary — The Plumber teardown and CI-diagnosis opportunity

Date: 2026-10-15. Details are in `01`–`08`. Labels: [OBS] observed, [DOC] vendor-documented, [INF] inference.

## Decision: **VALIDATE FIRST**

Do **not** build the original idea (explain + fix + verify CI failures) as stated. Instead:

1. Run a one-week validation of a narrower wedge: **failure attribution**, meaning "was it your push, an earlier commit, an upstream package, the runner, or a flaky test?"
2. Build the 3-week MVP in `06` only if the decision thresholds in `07 §3` are met.

**Confidence:**

| Aspect | Confidence | Basis |
|---|---|---|
| Problem | Medium-high | CircleCI and academic data |
| Differentiation | Medium | Bounded competitive search |
| Willingness to pay | **Low** | No direct evidence anywhere |

## Most important findings

1. **GitHub has bundled the core of the original idea.**
   - "Explain error" has been GA for all Copilot tiers since 2025-01-15.
   - **One-click "Fix with Copilot" for failing Actions** shipped to Business/Enterprise on 2026-05-18, to Pro/Pro+/Max on 2026-06-04, and to mobile on 2026-07-23 [DOC, re-verified].
   - GitHub's CI Doctor sample (technical preview) already does automatic first-error diagnosis with commit correlation [DOC, verified].
2. **The three named competitors are tiny, recent, solo-built products with no visible traction** [OBS]. Explanation (b) below is the most likely one, but it is unproven.

   | Product | Launched | Traction signal | Plans |
   |---|---|---|---|
   | The Plumber | Apr 2026 | 4 installs | Free only |
   | FailBrief | Jan 2026 | 1 Product Hunt upvote | $9–59 |
   | FixSense | Feb 2026 | 5 installs | $49–149, E2E auto-fix only |

   The poor traction could mean either:
   - **(a)** little demand for standalone CI explainers; or
   - **(b)** nobody has tried distribution.
3. **The Plumber was mostly unobservable on its own site.** All of theplumber.dev sits behind a Cloudflare challenge (REA evidence `ev_bd805a79…`), and we did not bypass it. Its GitHub App manifest and its one public report were fully verified [OBS]:
   - **Pipeline:** `workflow_run` → logs + clone → LLM agent with file-read tools → a 7-section markdown report, posted as a commit or PR comment.
   - **Permissions:** `contents:read` plus `pull_requests:write`.
   - **Fix suggestion:** the report's fix was **correct**.
   - **Latency:** about **6 min**, against a "<2 min" claim.
   - **Missed attribution:** **it reported on a README-only commit without saying the bug pre-dated it, or which commit introduced it** [OBS, n=1].
4. **Pain is real and measurable.**
   - CircleCI 2026: main-branch success fell to **70.8%**; recovery takes **72 min**, and about **3 h** for 21–50-person companies.
   - Flaky, network and dependency causes are a large share of GitHub Actions build failures (arXiv 2026).
   - LLM explanations degrade on complex logs (ICPC 2025).
   - Developers distrust "almost right" AI (SO 2025: 66%).
5. **Willingness to pay for *diagnosis* is unproven.** Small teams demonstrably pay for CI **speed** (Depot, Blacksmith) and **flaky-test management** (Trunk, Datadog, Gitar at $20+/user). We found no evidence of paying specifically for diagnosis, and log explanation already sells at about $0.03–0.06 per analysis.

## Is The Plumber a suitable reference product?

**As a workflow template: yes.**
- Its pipeline and permission set are the minimal viable design.
- Its report shape is worth emulating, especially "Files Examined" and the "For AI Agents" handoff block.

**As evidence of a market: no.** It has 4 installs, no paid plan, and has not been updated since 2026-04-15. Its ease of construction shows the basic pattern is **not defensible**.

## What competitors already do well

| Competitor | Strengths |
|---|---|
| **GitHub** | Zero-install distribution; agent that edits code and runs tests in a sandbox |
| **FailBrief** | Cheap, logs-only (no code access); history, flaky detection, MCP connector, Slack/Discord |
| **FixSense** | E2E-specific depth (screenshots, traces); honest verification design (Deflake: up to 3 runs, draft PRs, test-only edits) |
| **Gitar (Sonar)** | Real vs flaky vs infra separation, bundled with code review |

## Three most credible differentiation opportunities

1. **First-bad-change attribution (D).** Find the last green run, the first red run, and the commit range between them. Name the introducing commit and say "this push didn't cause it." The Plumber's own demo shows the gap.
2. **External-cause detection (B).** Detect dependency drift by diffing resolved package versions against the last green run and checking registry release times, plus runner-image changes and flaky recurrence. Report "Not your change — `pkg 2.0` released 3h ago; pin to 1.9.3."
3. **Evidence-checked verdicts with abstention (C+H)** as a design property:
   - every claim links to a real log line or diff hunk;
   - "unclear" yields a 2–3 step diagnostic plan instead of a speculative patch;
   - this addresses the false-confidence and masked-bug complaints.

Long-term moat hypothesis: **cross-tenant upstream-breakage signals**, e.g. "`foo 2.0` broke 30 repos in the last hour." This needs scale.

## Recommended initial segment

**Teams of 5–30 engineers on GitHub Actions with Python and/or TypeScript services and a shared trunk** (about 15+ runs/day). The buyer is the Head of Engineering or CTO; end users are the developers blocked by a red main.

## Proposed MVP (only after validation)

- A **read-only GitHub App**: `actions:read`, `checks:write`, `contents:read`, `pull_requests:write`.
- **Pipeline:** deterministic Python/TS log parsers, then fingerprinting, then **attribution rules** (pre-existing, dependency drift, runner change, flaky, code regression, config), then **≤2 bounded LLM calls** with structured output and an evidence check.
- **Output:** **one Check Run** per failed run, plus one optional upserted PR comment and a Slack alert when main breaks.
- **Outcome tracking:** the next run on the branch marks the analysis resolved or still failing.
- **Stack:** FastAPI + arq/Redis + Postgres (RLS) + Next.js.
- **Cost and price:** about **$0.04–0.06 per failed run** (Sonnet 5.5 default, roughly 40% handled deterministically). Pilot price hypothesis: $99/month flat.
- **Exclusions:** autofix PRs, sandboxes, non-GitHub CI, languages beyond Python/TS.
- **Timeline:** 3 build weeks plus 1 buffer.

## Biggest risks

1. **Pain mismatch.** Teams may resolve "who broke it" quickly by eye, leaving only the hard-investigation problem, where GitHub's agent wins.
2. **Fast-follower risk.** GitHub (CI Doctor productized) or Gitar may ship attribution.
3. **GitHub App trust barrier** for `contents:read` (CodeRabbit RCE precedent).
4. **Low base rate of external causes** in the target segment.
5. **Distribution.** Every indie competitor stalled at fewer than 10 visible installs.

## Recommended next action (this week)

1. **Label 200 real red runs** from 30–50 public Python/TS repos to measure how often "blame the push" is wrong (1–2 days).
2. **Run 12–15 non-leading interviews** using the script in `07 §2.2`, including the mock A/B Check Run test.
3. **Authorize a test GitHub org**: `gh auth login` plus explicit consent to install The Plumber, FailBrief and Copilot Fix there. Then run benchmark cases B-02, B-05, B-09, B-12 and B-14 against them (`04`). This tells us whether the attribution gap is real beyond n=1.
4. **Decide BUILD, NARROW, CHANGE or ABANDON** against the thresholds in `07 §3`.
