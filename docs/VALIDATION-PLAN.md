# Commercial Validation Plan: Gate G-0 (canonical)

Version 2.0, 2026-10-18. This carries over the ICP and interview script from `research/archive/2026-10-15-s1-research/07-validation-and-gtm.md`, with corrections:

- **no credentials**: the `gh run list` labelling is replaced by anonymous metadata;
- G-2 redefined (CM-27, D-1);
- unsupported latency copy removed.

**Recommendation unchanged:** validate demand before committing to the full build.

## 1. ICP v0 (hypothesis)

| Attribute | Definition |
|---|---|
| Company | Software teams of **5–30 engineers** |
| Stack | **GitHub Actions**; Python and/or TypeScript services; shared `main` |
| Volume | ≥15 workflow runs/day; red `main` at least weekly |
| Signals | Loosely pinned dependencies or frequent Dependabot/Renovate bumps |

**Buyer:** Head of Engineering, CTO, or a tech lead.

**Users:** whoever is blocked when CI is red.

**Current workarounds** (to confirm in interviews):

- scroll the logs;
- `git log` / bisect by hand;
- re-run until green;
- ask in Slack;
- paste the log into ChatGPT, Claude or Copilot ("Explain error" / "Fix with Copilot").

## 2. Interviews (G-1, G-3)

**Target:** 12–15 calls. **Opener** (no pitch):

> "We're researching how small teams handle red CI on GitHub Actions — not selling anything. 20 minutes; we'll share anonymized findings."

**Script (non-leading):**

1. Walk me through the **last time** CI on your main branch went red. What happened, step by step?
2. How did you figure out **what caused it**? How long did that take? Who was involved?
3. In the last month, roughly how many red runs were **not caused by the code in that push** (flaky tests, upstream package, runner, secret, an earlier commit)? How did you tell?
4. What did that cost you (blocked merges, delayed releases, interrupted people)?
5. What tools or habits do you use today when CI fails? *(Don't prompt.)*
6. Have you tried any AI tool for CI failures? What happened? What made you keep or drop it?
7. If something could answer one question about every red run automatically, what would it be?
8. Are there rules about sending CI logs or code to third-party services or AI providers? Who decides?
9. What do you currently pay for CI-related tooling? Who approved it?
10. *(At the end only)* Show two mock reports for a public failure: (A) a diagnosis with root cause, location and fix; (B) the same plus the attribution line ("this push changed only README.md; not implicated; likely pre-dates this push"). Which would change what you do next, and why?
11. Would you install this on one repo for 2 weeks? What would stop you?

**Recruiting channels:**

- GitHub public orgs with red `main` (observed through anonymous public pages);
- developer communities;
- warm network;
- LinkedIn.

No scraping of personal data beyond public contact routes.

## 3. Public-metadata study (G-2): no credentials

**Method:**

- Anonymous GitHub REST at ≤60 requests/hour.
- For 30–50 public Python/TS repos of ICP-like companies, list workflow runs on the default branch.
- For each red run, label from **metadata only**:
  - (a) the **same job and step** already failed on an earlier run in the lane before this push (*pre-existing at job/step level*);
  - (b) the **same SHA** has another attempt that passed (*flaky signal*);
  - (c) otherwise *undetermined from metadata*.

**Measurement definitions (D-1, provisional hypothesis H-G2):**

| Term | Definition |
|---|---|
| Lane | (repository, `workflow_id`, default branch) |
| Window | The 90 days before the study date, fixed when the study starts |
| **Denominator** | Workflow runs in the window on the default branch with `conclusion ∈ {failure, timed_out}` and `run_attempt = 1` (re-runs are not separate cases). At most the 50 most recent per repository, so no single repo dominates. **Excluded and reported separately:** runs whose jobs list is unavailable, and runs with no earlier completed run in their lane (no history to compare). |
| Numerator | Denominator runs labelled (a) or (b) |
| (a) Pre-existing | The **immediately preceding** completed run in the same lane also failed, with the **same job name and the same failed step name** |
| (b) Flaky signal | Another attempt of the same run (same `head_sha`, `run_attempt > 1`) concluded `success` |
| Reported | Pooled share with a Wilson 95% CI; the per-repository median share; the count per label; exclusions; and the full run list with provenance |

**Interpretation:**

- The share is a **lower bound** on "blaming the push would be wrong". Dependency, environment and config causes are **not countable** without logs.
- It is a hypothesis test for the commercial decision only, not a market finding, and not a gate on implementation.

**Rules:** no log downloads; no `gh` CLI; provenance recorded per run (endpoint, time, anonymous).

## 4. Gates (D-1 defaults applied)

| Gate | Evidence | Threshold |
|---|---|---|
| G-1 Pain | Interviews | ≥7/12 describe a costly "was it us or something else?" episode **unprompted** (Q1–Q3) |
| G-2 Base rate (provisional hypothesis H-G2) | §3 lower bound, with a Wilson 95% CI | **≥15% supports** the hypothesis; below 15% does **not** refute the product (lower bound). Input to the BUILD decision together with G-1 and G-3; never an automatic gate. |
| G-3 Commitment | Named repo + date | ≥5 leads commit to installing |
| G-PAY | Written pilot terms (price, start, exit criteria) | ≥2, before any external install |

**Outcomes:**

| Outcome | Condition |
|---|---|
| **BUILD** | G-1 + G-3 pass, and G-2 is not contradicting |
| **NARROW** | Pain concentrated in one sub-segment |
| **CHANGE** | Interviewees prefer plain diagnosis (mock A) and see no value in attribution: build parity only and re-examine differentiation |
| **ABANDON** | G-1 ≤3/12, or G-3 <2 |

## 5. Pricing and copy

- Price points to probe ($49 / $99 / $199 per month) are **hypotheses**. No quota or price is fixed until cost per analysis is measured (T-605).
- **No latency, accuracy or cost statements** in outreach or landing copy until measured.
