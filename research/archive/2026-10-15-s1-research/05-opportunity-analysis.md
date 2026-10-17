# 05 — Opportunity Analysis

Research date: 2026-10-15. This document builds on `01`–`04`. Labels: [OBS] observed, [DOC] vendor-documented, [INF] inference.

## 1. What the evidence says about our original idea

Our original hypothesis was: *"Explain why a GitHub Actions run failed, classify it (code / test / dependency / infra), and give an evidence-backed fix with a trustworthy verification result."*

| Part of the original idea | Who already does it | Verdict |
|---|---|---|
| Explain a failed run in a PR comment | FailBrief ($0–59), The Plumber (free), GitHub Explain error (all Copilot tiers), CodeRabbit, Gitar | **Commodity.** The price floor is about $0.03–0.06 per analysis, or free. |
| Read code to find the line and suggest a fix | The Plumber, Copilot cloud agent, Cursor, Gitar | **Commodity.** GitHub ships one-click "Fix with Copilot" to Pro and above (2026-06-04) [DOC, verified]. |
| Classify code vs test vs flaky vs infra | Gitar ("real breakage separated from flaky and infra noise", $20/user) [DOC, verified], FixSense (E2E), FailBrief (error-type taxonomy) | **Contested.** No one owns it, though Gitar is closest. |
| Trustworthy verification | FixSense (E2E only), neverbreak (beta, "with proof"), Copilot agent (sandbox, not real CI), Gitar Pro (loop until CI passes) | **Contested and expensive to build.** Not feasible in 2–4 weeks for backend builds. |

**Conclusion: the evidence contradicts building the original idea as stated.** The "diagnose + fix" half is bundled into GitHub at zero marginal cost to Copilot users. Three direct indie competitors also exist, and none shows traction:

| Competitor | Traction signal |
|---|---|
| The Plumber | 4 installs |
| FixSense | 5 installs |
| FailBrief | 1 Product Hunt upvote |

Several HN launches in the category got almost no engagement. That pattern is consistent with two explanations:

- **(a)** Discovery and distribution are hard.
- **(b)** The pain is real, but a *standalone, generic* explainer is not compelling enough to adopt or pay for.

We cannot yet distinguish (a) from (b). That is the central uncertainty.

## 2. The problem, restated with evidence

| Pain | Evidence | Strength |
|---|---|---|
| CI is red often, and recovery is slow, worse for mid-size teams | CircleCI 2026: main-branch success rate 70.8%, the lowest in 5+ years; typical recovery 72 min (+13% YoY); about 3 h for 21–50-person companies | Quantitative (vendor telemetry) |
| A large share of failures are **not code regressions**: flaky, network, dependency | arXiv 2602.02307: 67.7% of reruns were flaky; top causes are tests, network and dependency resolution. ICST 2024: investigation is the main cost of flaky tests. | Quantitative |
| **Breakage without a code change**: runner image drift, upstream releases | `ubuntu-latest` 22.04 → 24.04 breakages (multiple repos); setuptools 78.0.1 broke builds widely (2025-03) | Repeated pattern |
| Generic AI explanations degrade on complex logs; users distrust "almost right" | ICPC 2025 (>80% correct only on simple logs); SO 2025 (66% "almost right" frustration); DORA 2025 (24% high trust) | Quantitative |
| Code-fix agents misfire on infra and flaky failures, and can mask bugs | HN anecdote (registry timeouts); GitHub Community #183215; dotnet/runtime retrospective | Anecdote + single-org data |
| Noise from AI bots on PRs | Community #169148 (~388 upvotes); CodeRabbit noise complaints | Repeated pattern |
| **Who broke it?** (attribution) | The Plumber demo reported on a README-only commit without saying the bug pre-dated it [OBS]. No product we found sells attribution as its core output. | **Direct observation, single case.** Customer pain is plausible but **unverified by interviews.** |

## 3. Hypotheses A–H

Scores run 1 (low) to 5 (high). For "Ease to replicate", a **low** score means **hard** for competitors to copy, which is better for us.

### A. First-causal-failure identification among downstream errors
- **Competitor coverage:** GitHub CI Doctor (preview) explicitly starts from "earliest failed job and first meaningful error" [DOC, verified]. Agents generally do this implicitly.
- **Pain evidence:** HN thread (huge, mostly irrelevant logs); ICPC 2025.
- **Difficulty:** low (deterministic parsing).
- **Replicability:** trivial.
- **Validation test:** measure on B-11/B-12 whether competitors get it wrong. If they mostly get it right, A is not a wedge.
- **What a customer would pay for:** nothing standalone. It is a *feature*.
- **Risk:** already solved well enough.
- **Scores:** pain 3, whitespace 1, time 5, differentiation 1, reach 3, WTP 1, ops risk 5.

### B. Attributing a failure to code regression vs dependency drift vs infra/runner vs flaky
- **Competitor coverage:**
  - Gitar markets "real vs flaky vs infra" [DOC].
  - FixSense classifies app/test/flaky/environment for E2E.
  - FailBrief has an error-type taxonomy.
  - **None we found documents dependency-drift detection** ("your lockfile didn't change, but `foo` resolved to 2.0.0 vs 1.9.3 on the last green run, released 4 h ago").
- **Pain evidence:** runner drift and setuptools incidents; arXiv flaky-build causes; HN anecdote.
- **Difficulty:** medium. Parse installed versions from logs (`Successfully installed …`, `added N packages`, `uv pip` output), diff them against the last green run on the same branch, check the PyPI/npm release time, read the runner image version from the log header.
- **Integration dependencies:** GitHub runs and logs API; PyPI JSON API; npm registry API; GitHub Status API.
- **Replicability:** medium. It is not hard in principle, but it needs per-ecosystem log parsers and a run-history store. Agents without history can't do it.
- **Validation test:** mine 200 real failed runs from popular public Python/TS repos and count the share where the cause was external (dependency, runner, flaky). If ≥25%, and teams in interviews describe "is it us or upstream?" as a recurring cost, keep going.
- **What a customer would pay for:** "Never waste an hour debugging your own code when upstream broke you", plus an instant 'not your fault, pin X' fix.
- **Risk:** the share of external failures in small teams' repos may be low. Gitar may add it.
- **Scores:** pain 4, whitespace 4, time 4, differentiation 4, reach 3, WTP 3, ops risk 4.

### C. Evidence-backed diagnosis with explicit uncertainty and abstention
- **Competitor coverage:** FailBrief and The Plumber show confidence labels without a basis. Nobody advertises abstention.
- **Pain evidence:** distrust surveys (strong but general).
- **Difficulty:** medium (evidence check, calibration needs labeled data).
- **Replicability:** easy to *claim*, hard to *demonstrate*.
- **Validation test:** in interviews, show two mock reports (one confident, one with "unclear + 2 checks to run") and ask which they'd act on. Then measure the false-attribution rate.
- **What a customer would pay for:** not directly. It is a *trust property* that increases retention.
- **Risk:** customers say they want honesty but reward confident answers.
- **Decision:** **adopt as a design principle, not the pitch.**
- **Scores:** pain 3, whitespace 4, time 3, differentiation 3, reach 2, WTP 2, ops risk 4.

### D. Cross-run correlation: when the failure first appeared and which change caused it
- **Competitor coverage:**
  - CI Doctor correlates with the *triggering* commit (preview, DIY, GitHub-only).
  - FailBrief keeps history but does no correlation.
  - The Plumber demo misses it [OBS].
  - Harness offers it, but only for Harness CI.
- **Pain evidence:** CircleCI recovery-time data; the "did my push break it?" question. **No direct customer quotes found.**
- **Difficulty:** medium.
  - For each failing signature, walk back over runs on the same branch (`GET /repos/{r}/actions/runs?branch=main`).
  - Find the last green run and the first run with the same fingerprint.
  - Compute the commit range, then rank commits by overlap with stack-trace files and lockfile changes.
- **Replicability:** medium. It needs persistent history, and a fingerprint quality that is our real IP.
- **Validation test:** a benchmark with B-02, B-05 and B-15 style cases, plus 50 real OSS main-branch breakages. Correct first-bad-commit ≥70% of the time.
- **What a customer would pay for:** "When main goes red, know in 60 s whether it was your push, an earlier one, or upstream, and who should fix it."
- **Risk:** GitHub could ship this. Its CI Doctor is directionally there.
- **Scores:** pain 4, whitespace 4, time 4, differentiation 4, reach 3, WTP 3, ops risk 4.

### E. Verification of backend build and integration fixes
- **Competitor coverage:** Copilot agent (sandbox), Gitar Pro (fix loop), neverbreak (proof), FixSense (E2E). The space is crowded with well-funded players.
- **Difficulty:** high: sandbox infrastructure, secrets, services, cost and security.
- **Replicability:** n/a; incumbents are ahead.
- **Validation test:** not worth one in the MVP window.
- **Risk:** high operational risk (running untrusted code).
- **Decision:** **exclude.**
- **Scores:** pain 4, whitespace 2, time 1, differentiation 2, reach 2, WTP 3, ops risk 1.

### F. Recurring failure classes in Python and TypeScript repos
- **Competitor coverage:** FailBrief history and flaky detection; FixSense flaky scores; Trunk and Datadog.
- **Difficulty:** low to medium.
- **Replicability:** easy.
- **What a customer would pay for:** narrowing to two ecosystems makes B and D *feasible* (fewer log formats and package managers). It is a scope decision, not a wedge.
- **Scores:** pain 3, whitespace 2, time 4, differentiation 2, reach 4, WTP 2, ops risk 4.

### G. Private or self-hosted execution
- **Competitor coverage:**
  - GitHub Agentic Workflows already run in your own Actions with your own key.
  - FixSense has BYO key for fixes.
  - Several OSS self-hosted review bots exist.
- **Pain evidence:** JetBrains 2025: privacy is the third AI concern (13%). Strong blockers appear only in narrow populations. **Demand from small teams is weak.**
- **Difficulty:** low as a GitHub Action with BYO key. Monetizing it is hard.
- **Validation test:** interview question 8 (§07). Count how many say "we cannot send logs or code to a SaaS".
- **What a customer would pay for:** an enterprise-tier feature later. **Not a small-team wedge.**
- **Scores:** pain 2, whitespace 3, time 4, differentiation 2, reach 2, WTP 2, ops risk 4.

### H. Turn an ambiguous failure into a short, prioritized diagnostic plan instead of a patch
- **Competitor coverage:** none advertised. Agents default to patching (risk of masking bugs, per Community #183215).
- **Pain evidence:** indirect (ICPC complex-log failures; "almost right").
- **Difficulty:** low once B, C and D exist. It is the abstention path's output.
- **Replicability:** easy.
- **What a customer would pay for:** not standalone.
- **Decision:** **bundle into B+D as the "unclear" output.**
- **Scores:** pain 3, whitespace 4, time 4, differentiation 3, reach 2, WTP 1, ops risk 5.

## 4. Ranking

Equal weights, with "ops risk" scored higher = safer. Higher totals are better.

| Rank | Hypothesis | Pain | Whitespace | Time-to-build | Differentiation | Reach | WTP | Ops safety | **Total /35** |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **D: first-bad-change attribution** | 4 | 4 | 4 | 4 | 3 | 3 | 4 | **26** |
| 1 | **B: code vs dependency vs infra vs flaky** | 4 | 4 | 4 | 4 | 3 | 3 | 4 | **26** |
| 3 | H: diagnostic plan for ambiguous failures | 3 | 4 | 4 | 3 | 2 | 1 | 5 | 22 |
| 4 | C: evidence and abstention | 3 | 4 | 3 | 3 | 2 | 2 | 4 | 21 |
| 4 | F: Python/TS recurring classes | 3 | 2 | 4 | 2 | 4 | 2 | 4 | 21 |
| 6 | A: first causal error | 3 | 1 | 5 | 1 | 3 | 1 | 5 | 19 |
| 6 | G: self-host | 2 | 3 | 4 | 2 | 2 | 2 | 4 | 19 |
| 8 | E: backend fix verification | 4 | 2 | 1 | 2 | 2 | 3 | 1 | 15 |

B and D are the same product seen from two sides: **"what changed between green and red, and was it us?"** A, C, F and H are its supporting properties.

## 5. Recommended narrow product promise

> **"When CI goes red, know in under a minute whether your push broke it — or an earlier commit, an upstream package release, the runner, or a flaky test — with the evidence, and the one-line next step."**

Working name: *Tracewise*. Positioning: **attribution, not autofix.** It complements "Fix with Copilot" rather than competing with it. Once attribution says "code regression in your commit", the customer can still click Fix with Copilot. We hand off cleanly, as The Plumber's "For AI Agents" block does.

**What it explicitly does not do in v1:**

- write code;
- open PRs;
- run sandboxes;
- support non-GitHub CI;
- support languages other than Python and TypeScript.

### Target segment (initial)

- **Who:** product engineering teams of **5–30 engineers** with a shared trunk on **GitHub Actions** and **Python and/or TypeScript** services.
- **Which ones:** teams that merge often enough that main being red blocks others. Proxy: ≥15 workflow runs/day on main or PRs.
- **Why them:**
  - CircleCI shows the worst recovery times in exactly this size band.
  - They have no platform team to build attribution tooling, unlike the dotnet/runtime case.
  - They are below Gitar/Sonar's sweet spot.
  - They are reachable via GitHub search (public repo activity), communities and direct outreach.
- **Not first:**
  - OSS maintainers (low willingness to pay, fork PR permissions);
  - enterprises (security review cycles exceed our runway);
  - E2E-heavy QA teams (FixSense's niche).

### Long-term defensibility (hypothesis, not an MVP claim)

**Cross-tenant upstream-breakage signal.** If many installations see the same failure fingerprint right after `foo==2.0.0` is published, we can warn every other customer with `foo` unpinned before their CI even runs.

- Fix-first agents do not have this data network effect.
- GitHub could build it, but it does not position the product that way today.
- It requires scale, so treat it as a moat to grow into.

## 6. Reasons to proceed / not to proceed

**Proceed (validate) because:**
- Measured pain is real and growing: 70.8% main success, slow recovery.
- External and non-code causes are a large share of failures.
- No competitor sells attribution as its core output (bounded search).
- It is cheap to build: deterministic, plus one bounded LLM call. Cost per analysis is about $0.003–$0.07 (see `06`).
- It fits the team's FastAPI/Postgres/LLM skills and the SecureLens multi-stage pipeline experience.

**Do not proceed if:**
- Interviews show teams resolve "who broke it?" in under 5 minutes by eye. In that case the pain lives in investigation of genuinely hard failures, which is the agent and fix space where GitHub wins.
- The real-run mining (validation test B) shows external causes are less than about 15% of failures for this segment.
- None of 10–15 leads agrees to install on a real repo within 2 weeks.

**Alternative explanations for the competitors' poor traction that would also hurt us:**
1. Developers don't adopt third-party GitHub Apps for small pains. Install friction plus security review.
2. CI pain is real, but budget goes to speed (Depot, Blacksmith) and flaky-test management (Trunk), not diagnosis.
3. All three are solo side projects with no distribution effort. In that case their failure says little about demand. This is the most likely explanation in our assessment, but it is unproven.
