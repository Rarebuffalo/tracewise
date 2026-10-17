# 07 — Validation and Go-to-Market

Research date: 2026-10-15. **All prices and conversion targets here are hypotheses** until buyers talk to us or pay.

## 1. Ideal customer profile (ICP v0)

| Attribute | Definition | Why (evidence) |
|---|---|---|
| Company | Software company or product team, **5–30 engineers**, global, B2B or B2C SaaS | CircleCI 2026: the 21–50-employee band has the longest recovery (≈3 h). No platform team. |
| Stack | **GitHub Actions**, a **Python and/or TypeScript** service, shared trunk (`main`) | Narrow parsers, so attribution is feasible (`05` F) |
| Volume | ≥15 workflow runs/day; red main at least weekly | Enough runs to make history-based attribution valuable |
| Dependency hygiene | Unpinned or loosely pinned dependencies, or frequent Dependabot or Renovate bumps | Raises the share of failures caused by external drift (hypothesis B) |
| Already uses | GitHub Team/Enterprise; maybe Copilot; maybe Slack | Sets "Fix with Copilot" as the baseline to beat or complement |

**Buyer:** Head of Engineering, CTO (≤30 engineers), or a tech lead with a card.

**End users:**
- the on-call or "build cop" developer;
- whoever is blocked when main is red.

**Trigger moments** (when they look for a solution):
- main red for hours;
- an upstream release breaks CI on a Monday;
- a new hire repeatedly asks "is this my fault?";
- a postmortem about a delayed release.

**Current workarounds** (to be confirmed in interviews):
- scroll the logs;
- `git log` / `git bisect` by hand;
- re-run until green;
- ask in Slack;
- pin dependencies after the fact;
- paste the log into ChatGPT, Claude or Copilot ("Explain error").

**Competitors they may already use:**
- GitHub Copilot (Explain error / Fix with Copilot);
- Trunk or Datadog for flaky tests;
- CodeRabbit or Gitar for review.

**Reason to add us:**
- "Copilot fixes code. We tell you *whether it's your code*, and if it isn't, what changed upstream."
- Automatic on every red run.
- One Check Run, no comment spam.
- Read-only.

## 2. Validation experiment (week 0, before writing production code)

**Goal:** 12–15 conversations with engineering leads or senior developers who match the ICP, plus a real-data check.

### 2.1 Recruiting (no product pitch in the first message)

| Channel | Approach |
|---|---|
| **GitHub search** | Public orgs with Python/TS repos whose Actions history shows red runs on `main` (visible in public Actions tabs). Contact maintainers who are employed at companies. |
| **Communities** | r/devops, r/ExperiencedDevs, DevOps-focused Slack and Discord groups, local meetups. Ask for a 20-min "research call about CI failures", not a demo. |
| **Warm network** | The team's own network and past clients (SecureLens contacts). |
| **LinkedIn** | Heads of Engineering at 10–50-person startups. |

Opener template:

> "We're researching how small teams handle red CI on GitHub Actions — not selling anything. 20 minutes, and we'll share the anonymized findings + a CI-failure report on one of your public repos if useful."

### 2.2 Interview script (non-leading)

1. Walk me through the **last time** CI on your main branch went red. What happened, step by step?
2. How did you figure out **what caused it**? How long did that take? Who was involved?
3. In the last month, roughly how many red runs were **not caused by the code in that push**? Examples: flaky tests, an upstream package, GitHub runner, a secret, or an earlier commit. How did you tell?
4. What did that cost you, in blocked merges, delayed releases or interrupted people?
5. What tools or habits do you use today when CI fails? *(Listen for Copilot, ChatGPT, re-run, Trunk, etc. Don't prompt.)*
6. Have you tried any AI tool for CI failures? What happened? What made you keep or drop it?
7. If something could answer one question about every red run automatically, what question would you want answered?
8. Are there rules about sending CI logs or code to third-party services? Who decides?
9. What do you currently pay for CI-related tooling? Who approved it?
10. *(End only, after the pain is established)* Show **two mock Check Runs** for a real failure from their repo, if public: (A) a "fix suggestion" style and (B) an "attribution" style ("Not your change: `pydantic 2.12.0` released 3h ago, pin to 2.11.9"). Ask: which would change what you do next, and why?
11. Would you install this on one repo for 2 weeks? What would stop you?

### 2.3 Real-data check (in parallel, 1–2 days)

- Pull failed runs from 30–50 public Python/TS repos of ICP-like companies, for example with `gh run list --status failure --branch main --limit 50`.
- Hand-label 200 failures: code regression in the triggering commit / pre-existing (earlier commit) / dependency drift / runner or infra / flaky / config.
- **Output:** the share of failures where "blame the triggering push" would be wrong.

## 3. Decision thresholds

Evaluate after 12+ interviews plus the 200-run labeling.

| Decision | Threshold |
|---|---|
| **Continue (BUILD the MVP in `06`)** | All of: ≥7/12 describe a recent costly "was it us or something else?" episode unprompted (Q1–Q3); **and** labeled data shows ≥20% of main failures are not caused by the triggering push; **and** ≥5 agree to install on a real repo; **and** ≥3 say they'd pay ≥$50/mo, or name a budget owner, if it works |
| **Narrow the segment** | The pain is strong only in one sub-group, e.g. teams with heavy dependency churn, monorepos, or ML/Python data teams. Re-run 5 interviews in that sub-group before building. |
| **Change the differentiation** | Interviewees mostly want "make it green for me" (patches) and choose mock A over B. Pivot to complementing Copilot, e.g. as a router: classify → if code, hand to Copilot or Cursor; if not, pin or re-run automatically. Or explore flaky-test management for this segment, but against Trunk's free tier. |
| **Abandon** | ≤3/12 report the pain; **or** external causes are <10% in the labeled data; **or** most say Copilot "Explain error / Fix" is good enough and nobody will install a third-party app. Alternatives already satisfy the segment. |

## 4. Free / trial experience

1. **Zero-install teaser (public repos):** "Paste a repo URL → we analyze its last 20 red runs on main and show the attribution breakdown." Uses public Actions logs only, no App install. This doubles as an outreach asset ("we found 6 of your 14 red runs last month were upstream breakages").
2. **Install trial:** 14 days, full features, read-only app, no card.
3. **Free tier after the trial (optional):** 1 private repo, 30 analyses/month. This beats FailBrief's 25 and The Plumber's public-only 10.

## 5. Pricing hypotheses (to test, not to assert)

| Plan | Hypothesis | Rationale |
|---|---|---|
| Pilot | $0 for 2–4 weeks, then **$99/month** flat per org (≤10 repos, 1,000 analyses) | Above FailBrief ($29–59, logs-only) and below Gitar for 10 seats ($200–250). Flat pricing avoids the "unpredictable AI cost" complaint. |
| Team | **$249/month** (unlimited repos, 5,000 analyses, Slack, history API) | For 20–30 engineer teams |
| Experiment | Show 3 price points ($49 / $99 / $199) across interview cohorts in the "would you pay" question; then require a **paid pilot invoice** (even $99) as the real signal | |

**Billing:** Paddle or Lemon Squeezy as merchant of record (global VAT) for self-serve; manual invoice for the first pilots.

## 6. Design-partner recruitment

- **Target:** 5 design partners from the interview pool.
- **Offer:**
  - free for 6 weeks;
  - weekly 15-min sync;
  - their failure labels improve the product;
  - founder-level support.
- **Ask:**
  - install on ≥1 active repo;
  - 👍/👎 on each verdict;
  - one end-of-pilot call;
  - a **conversion decision at week 6 at the pilot price**.
- **Success metric per partner:**
  - ≥30 analyses;
  - ≥70% 👍 on attribution;
  - at least one "saved us time" story we can quote with permission.

## 7. Direct outreach plan (weeks 0–4)

| Week | Activity | Target |
|---|---|---|
| 0 | 60 personalized messages (GitHub-sourced plus network); 12–15 interviews; label 200 runs | Decision gate |
| 1–2 | Build; send 5 "your last month of red runs" reports (from public data) to interviewees' public repos | 5 design partners committed |
| 3 | Partners installed; daily review of every verdict | ≥70% 👍 |
| 4 | Pilot conversion asks; landing page live with anonymized real examples; one write-up post: "We labeled 200 red CI runs: X% weren't the pusher's fault" (content marketing with original data) | **≥2 paid pilots** |

## 8. Landing-page value proposition (draft)

> **Red CI? Know whose fault it is in 60 seconds.**
> Tracewise reads every failed GitHub Actions run and tells you whether *your push* broke it — or an earlier commit, an upstream package release, the runner image, or a flaky test. With the exact log line and diff that prove it, and the one next step.
> Read-only. One check per run. No comment spam. Python & TypeScript.
> *[See your last 20 red runs — free, no install]*

Proof points to collect (none exist yet; do not fabricate):
- the share of runs that were "not your fault";
- median time to verdict;
- partner quotes.
