# 03 — Competitor Matrix

Research date: 2026-10-15. All pages were accessed on that date unless a date is given.

**Capability states**

| Mark | Meaning |
|---|---|
| ✅ | Confirmed available, with a source |
| ⛔ | Vendor explicitly says it is *not* supported |
| — | Not found in the evidence we reviewed. **This does not mean "unsupported".** |
| ? | Unknown |

Sources are listed in `08-sources-and-confidence.md`.

## 1. Who they are

| | **The Plumber** | **FailBrief** | **FixSense** | **GitHub native (Copilot)** |
|---|---|---|---|---|
| One-liner | GitHub App: agentic CI failure diagnosis posted as a "Plumbing Report" | GitHub App: AI explanation of failed Actions logs on the PR, plus a CI-health dashboard | AI analysis of **E2E test** failures plus a verified auto-fix PR (Playwright/Cypress) | "Explain error" (chat), "Fix with Copilot" (cloud agent), CI Doctor (preview sample) |
| Target customer | Unstated; free plan for public repos | Solo devs, 2–50-person teams, OSS maintainers (founder post) | Teams with large Playwright/Cypress suites and little QA budget | All Copilot users |
| Main job | "Why did CI break, what line, what fix" | "Why did CI break" (logs only) plus CI health trends | "Triage E2E failures (app bug vs test bug vs flaky) and fix the test" | Explain or fix a failed job on demand |
| Created / launched | App created 2026-04-14 [OBS] | App 2026-01-06; launched about May 2026 [OBS/DOC] | App 2026-02-24 [OBS]; legal pages effective 2026-03-03 | Explain error GA 2025-01-15; Fix with Copilot 2026-05-18 (Business/Ent), 2026-06-04 (Pro+) [DOC] |
| Team | Apparently a solo side project [INF] | Solo founder [INF] | Solo founder (QA automation background) [DOC/INF] | GitHub/Microsoft |

## 2. Capability matrix

| Capability | The Plumber | FailBrief | FixSense | GitHub native |
|---|---|---|---|---|
| Install experience | GitHub App, no config [DOC] | GitHub App, no YAML [DOC] | GitHub App **plus required config**: JUnit reporter and upload-artifact step; auto-fix needs a workflow PR and `ANTHROPIC_API_KEY` [DOC] | Built in; cloud agent needs admin enablement on Business/Enterprise [DOC] |
| CI platforms | GitHub Actions ✅ | GitHub Actions only ✅ (others ⛔) | GHA, GitLab, Azure, Bitbucket ✅; Jenkins analysis-only | GitHub Actions ✅ |
| Languages | 9 listed [DOC] | "All" [DOC] | Analysis: any JUnit-XML framework; **auto-fix: Playwright/Cypress only** ✅ | Any [INF] |
| Source-code access | ✅ `contents:read`, clone at SHA | ⛔ none (no `contents` permission) [OBS] | ✅ `contents:write` [OBS] (privacy policy contradicts this) | ✅ |
| Log processing | ✅ | ✅ (failed jobs only) | ✅ (reports, logs, screenshots, Playwright traces) | ✅ (one job at a time, for Explain error) |
| Root-cause investigation | ✅ agentic, reads code [DOC+OBS] | ✅ logs only | ✅ "multi-signal" | ✅ (agent); Explain error's code context is ? |
| Primary vs downstream error separation | ? | ? | ? | CI Doctor: "earliest failed job and first meaningful error" ✅ (preview sample) |
| Historical failure analysis | — | ✅ searchable history, MCP "seen before?" | ✅ 8-week trends, cached analyses | — (CI Doctor dedupes issues) |
| Flakiness analysis | — | ✅ same-commit pass/fail | ✅ 0–100 score, quarantine gate | — |
| Code-change correlation | — (demo did **not** attribute to the introducing commit) [OBS] | — | ? ("diff context" on re-analysis) | CI Doctor ✅ (triggering commit/PR) |
| Infra vs code classification | — | ✅ error-type taxonomy incl. timeout/dependency | ✅ app/test/flaky/environment | — |
| Fix generation | ✅ text plus code snippet plus "For AI Agents" block | Text suggestion only | ✅ patch (tests and config only) | ✅ pushes commit to branch |
| Automated verification | — | ⛔ ("doesn't run your tests") | ✅ runs tests in your CI, 1 run (or 3 with Deflake) | Agent runs tests in its sandbox; real CI on agent pushes needs approval by default |
| PR creation | — | ⛔ | ✅ draft PR | ✅ push to branch, or stacked PR (mobile) |
| Human approval | N/A | N/A | ✅ draft by default; auto-merge opt-in | ✅ review tag; workflow approval gate |
| Automatic trigger on every failure | ✅ | ✅ | ✅ | ⛔ manual click (except the CI Doctor DIY preview) |
| Dashboard / reporting | ⛔ "no dashboard" [DOC] | ✅ health score, MTTR, trends | ✅ | Actions UI only |
| Notifications | Comment only | PR comment, email, Slack, Discord | PR comment, Issues, Slack, webhook, quality-gate check | GitHub notifications |
| Agent / MCP integration | "For AI Agents" block in report | ✅ read-only MCP server | ✅ read-only Claude connector | Native |
| Self-host / BYO key | — | — | BYO key for auto-fix only; self-host "not available" | GitHub-hosted; Agentic Workflows run in your own Actions |
| LLM vendor disclosed | ? | OpenAI [DOC] | Anthropic (auto-fix BYO key); analysis provider ? | GitHub/Microsoft models |
| Data retention | "Code never stored, destroyed after report" [DOC] | Logs "deleted immediately"; results kept for the subscription plus 30 days [DOC] | 7 d / 60 d / 1 y by plan [DOC] | Free/Pro/Pro+ interaction data used for training unless opted out (from 2026-04-24) [DOC] |
| SOC 2 / DPA / SSO | ? (site blocked) | — | — | ✅ (GitHub Enterprise) |

### Permissions requested (from `api.github.com/apps/<slug>`) [OBS]

| App | actions | checks | contents | issues | pull_requests | workflows | other | events |
|---|---|---|---|---|---|---|---|---|
| the-plumber-app | read | read | **read** | — | write | — | metadata | workflow_run |
| failbrief | read | read | — | **write** | write | — | emails:read, metadata | workflow_run |
| fix-sense | read | **write** | **write** | write | write | **write** | metadata | workflow_run, pull_request |

These manifests contradict some of the vendors' own copy:

- **FailBrief.** The FAQ omits `issues:write` and `emails:read`. The homepage says "read-only", yet the app has write access.
- **FixSense.** The privacy policy says it never reads source code. The app has `contents:write`, and the FAQ says it reads application code.

## 3. Pricing and limits

| | The Plumber | FailBrief | FixSense | GitHub Copilot |
|---|---|---|---|---|
| Free | **$0**: 10 analyses/mo, public repos only (**the only plan**) | $0: 25 analyses/mo, low-priority queue | $0: 350 analyses/mo, 3 auto-fixes, 5 analyses per run, 7-day retention | Free: Explain error within the 50 chats/mo limit; **no cloud agent** |
| Paid | None listed | Starter **$9** (150) · Pro **$29** (500, Slack/Discord) · Business **$59** (2,000, team) per installation/month | Pro **$49** (3,500 analyses, 20 fixes) · Team **$149** (10,000, 100 fixes); 30-day Pro trial | Pro $10 · Pro+ $39 · Max $100 · Business $19/user · Enterprise $39/user. Usage-based AI Credits since 2026-06-01 |
| Unit | Analysis | **Failed workflow run** | **Failed test** | Credits/tokens; code review also consumes Actions minutes |
| Implied $/analysis (paid) | n/a | $0.06 (Starter) → $0.03 (Business) | $0.014 (Pro) | Opaque |

**Adjacent tools people demonstrably pay for** (from the pain research; lower confidence):

| Tool | Price | Confidence |
|---|---|---|
| Gitar (Sonar) | $20–25/user/mo Core, includes "CI failure diagnosis — real breakage separated from flaky and infra noise" | Verified on sonarsource.com |
| Trunk Flaky Tests | Free for ≤5 committers, then per committer | Pricing pages inconsistent |
| Datadog Test Optimization | Per committer | — |
| Depot | $20–200/mo, for CI speed | — |

## 4. Other directly overlapping products

These were confirmed from their own pages by the research agent. Gitar, CI Doctor and neverbreak were also re-verified by us.

| Product | Overlap | Price signal |
|---|---|---|
| **Gitar (acquired by Sonar, per a secondary source)** | CI failure diagnosis separating real, flaky and infra failures on GHA and GitLab; Pro adds an autonomous fix loop "until CI passes" | $20–25/user Core; $40–50 Pro ✅ verified |
| **GitHub Agentic Workflows: CI Doctor** | Automatic on `workflow_run`; starts at the "earliest failed job and first meaningful error"; correlates with commit, PR and config; creates or updates one issue per root cause | Preview; you pay for your own agent tokens ✅ verified |
| **neverbreak.ai** | Reruns the failing test with runtime tracing; fix PR "with proof"; GH and GitLab | Free beta ✅ verified |
| Trunk CI Autopilot | Root-causes CI failures, stacked fix PRs; flaky quarantine | Waitlist / demo |
| CodeRabbit CI/CD analysis | Reads failed check logs, posts inline fixes; many CI systems | Part of CodeRabbit plans |
| Cursor CI autofix | Webhook → reproduce → commit fix | Usage-based |
| GitLab Duo "Fix pipeline" | Logs (last 150 KiB), MR changes → suggestions or MR | GitLab tiers |
| Datadog Bits AI test optimization | Flaky detection plus a "verified" fix PR | Preview |
| CircleCI Chunk | Flaky-test fixer, multi-run validation | Credits plus your own key |
| Harness AI error analyzer | Change-impact correlation, history matching | Harness CI only |
| Depot Sherlock | AI CI diagnosis | Included, Depot CI only |
| Mergify / Buildkite / BuildPulse / CloudBees Smart Tests | Flaky detection and quarantine (not AI RCA) | Various |

## 5. Traction evidence

| Product | Strongest evidence | Label | Assessment |
|---|---|---|---|
| The Plumber | 4 Marketplace installs; 1 public repo; 0 followers; no launch posts; no paid plan; app not updated since 2026-04-15 | [OBS]/[DOC] | **Pre-traction / dormant side project** |
| FailBrief | Product Hunt: 1 upvote, 0 reviews; small-directory badges (LaunchIgniter "#1 of the week", FoundrList 27 upvotes); org has 2 followers; paid plans exist via Paddle; no customer logos or counts | [OBS] | **Very early**; paying customers unknown |
| FixSense | Marketplace app: 5 installs; Action repo: 4 stars; Docker: about 751 pulls; vendor claims "1,000+ failures analyzed" and an anonymised case study (87% triage reduction, unverified) | [OBS]/[DOC] | **Very early**; vendor claims not independently verified |
| GitHub native | Distribution to every Copilot user; features GA; multiple changelog expansions in 2026 | [DOC] | **Established distribution**. Usage of these specific features is not disclosed. |
| Gitar | Sonar acquisition (secondary source); published per-seat pricing | [DOC] | Established, via Sonar |
| Others (HN Show HN launches: PipelineIQ, ci-fix-coach, Wingman, Claude Code Watchdog, …) | Mostly 1–7 points, 0 comments | [OBS via agent] | **The category is crowded with low-pull launches** |

We **did not** infer revenue from installs, stars or launch badges. **No revenue, ARR or funding disclosures were found for The Plumber, FailBrief or FixSense.**

## 6. Customer feedback (independent)

| Product | Feedback found | Strength |
|---|---|---|
| The Plumber | None | — |
| FailBrief | None (0 comments on dev.to and Product Hunt; LaunchIgniter "Reviews (2)" text not retrievable) | — |
| FixSense | None (feedback repo archived 2026-03-18 with no issues) | — |
| GitHub "Fix with Copilot" / agent | **One HN anecdote (2026-07-24):** most of the poster's failures are registry timeouts, i.e. infra a code-fix agent can't fix. **GitHub Community #183215:** agent mode masked bugs by editing tests. **Microsoft dotnet/runtime retrospective (2026-03-23):** CI results "often had to be relayed manually"; sandbox success ≠ CI success; the team built its own CI-failure-analysis skill | Anecdote; anecdote with corroborating replies; strong single-org data |
| AI PR bots generally | GitHub Community #169148, "Can't disable Copilot code reviews" (~388 upvotes); recurring CodeRabbit-noise complaints; CodeRabbit RCE via a malicious PR (Kudelski, 2025) | Repeated pattern; concrete incident |
| LLM explanations of GHA failures (research) | ICPC 2025 (arXiv 2501.16495): >80% judged correct on **simple** logs; struggles on verbose or complex ones | Small academic sample (n≈31) |
| AI trust generally | SO Survey 2025: 66% say "almost right" answers are the top frustration; DORA 2025: only 24% trust AI a lot or a great deal | Quantitative |

**Complaint themes vs evidence strength**

| Theme | Strength |
|---|---|
| Incorrect or generic root causes on complex logs | Research plus anecdote; **moderate** |
| False confidence / "almost right" | Survey-level; **strong in general**, not tool-specific |
| Excessive comments and notifications | **Strong recurring pattern** (Copilot review, CodeRabbit) |
| Expensive or unpredictable usage | Moderate (HN reaction to Copilot billing changes) |
| Permission and privacy concerns | Moderate; amplified by the CodeRabbit RCE |
| Unreliable verification ("sandbox green ≠ CI green", agents editing tests to pass) | Moderate: Microsoft retrospective plus community thread |
| Infra failures misdiagnosed as code | Anecdote, plus CircleCI/arXiv data showing infra and flaky failures are common |
| Slow diagnosis, poor language support, difficult setup | **No evidence found** for these specific tools |

## 7. Gaps and limitations (inference, tied to the evidence)

1. **Nobody we found (in public evidence) delivers "who or what broke main", meaning attribution to the *introducing* commit vs an upstream dependency release vs a runner or infra change, as the core product.**
   - Closest: CI Doctor (correlates with the *triggering* commit; DIY preview), Gitar (real vs flaky vs infra), Harness (change impact, Harness-only).
   - The Plumber's own demo shows the gap: it reported on a README-only commit without saying the bug pre-dated it.
2. **Explicit abstention and evidence-linked claims** are not a stated feature anywhere. FailBrief and The Plumber show confidence labels without a stated basis.
3. **Verification that is honest about what was observed.**
   - FixSense verifies only E2E test fixes.
   - neverbreak claims proof but is a beta.
   - GitHub's agent verifies in a sandbox, not real CI.
   - Backend build and integration verification is largely open, but expensive to build.
4. **Fork PRs** are excluded from Copilot @-mentions and (reportedly) from Fix with Copilot. OSS maintainers are an underserved but low-paying segment.
5. **Price floor is low.** Pure log explanation already sells at $0.03–0.06 per analysis, or comes free with Copilot. A log-only explainer is not a business.
