# 08 — Sources and Confidence

Access date for every source is **2026-10-15** unless stated otherwise. Each source is classed by what it can establish:

| Class | Meaning |
|---|---|
| **OBS** | Observed directly by us, or by our agents through public APIs |
| **VENDOR** | The vendor's own claim |
| **INDEP** | Independent third party |
| **RESEARCH** | Academic or survey |

## 0. Research method and REA usage (Phase 0)

| Item | Finding |
|---|---|
| REA version | `rea-agents` 6.5.0, MCP, 207 tools, client Claude Code (`binary_session`) |
| REA capabilities **available** and relevant | Browser scenario capture (Playwright: network, DOM, accessibility, screenshot), passive CDP page inspection, web bundle analysis, script export, JS application graph, HAR/pcap inspection, evidence ledger |
| REA capabilities **unavailable** | Ghidra/Hopper/IDA (not configured), macOS-only tools, JADX/apktool, Wakaru, WABT, TShark, sigrok, Binwalk/Unblob, pwntools. Native-binary tools are **irrelevant**: all targets are hosted SaaS with no shipped binary. |
| REA run 1 | `capture_browser_scenario` → theplumber.dev: **307 → 403, Cloudflare Turnstile challenge** (`cf-mitigated: challenge`). Evidence `ev_bd805a791f3f688e59f53f478755f0303d56733d38b9f945af56df244bf667ae`. Not bypassed. |
| REA run 2 | `capture_browser_scenario` → failbrief.com and app.failbrief.com/docs/how-it-works: success. Observed a Next.js marketing site, a separate SPA app with hashed Vite-style assets, Paddle.js, Umami and DataFast analytics, and a Turnstile widget. Docs text captured from the accessibility tree. Evidence `ev_0238914767b8b4a9e4797c6d069727fc383b41573235c67770d98a0d0b1ce95c`. |
| In-app browser | theplumber.dev stuck on the interactive "Verify you are human" checkbox. CAPTCHAs are not completed by us. |
| Accounts and access | No GitHub auth (`gh` unauthenticated). No vendor accounts were created. No apps installed. No forms submitted. |
| Supplementary methods | GitHub public REST API (app manifests, org, repos, runs, commit comments); WebFetch / WebSearch via 5 parallel research agents; curl text extraction |

## 1. The Plumber

| ID | URL | Date | Supports | Class |
|---|---|---|---|---|
| S1 | https://github.com/marketplace/the-plumber-app | n/d | Tagline, workflow claims (clone, agentic, <2 min), free plan (10/mo, public repos), languages, privacy claim, 4 installs | VENDOR (installs: GitHub-displayed) |
| S2 | https://api.github.com/apps/the-plumber-app | created 2026-04-14, updated 2026-04-15 | Exact permissions and events | OBS |
| S3 | Search-engine snippet of theplumber.dev | n/d | Page title "AI CI Failure Diagnosis" | VENDOR (indirect) |
| S4 | https://api.github.com/users/theplumber-dev | org created 2026-04-14 | Org metadata, 1 repo | OBS |
| S5 | https://github.com/theplumber-dev/coffee_shop; `/comments`, `/actions/runs`, `/commits` APIs; upstream `andrewcampi/coffee_shop` runs | 2026-04-14 | Real Plumbing Report text, timing (run done 14:43:06Z → comment 14:49:20Z), README-only trigger commit, earlier introducing commit | OBS |
| S6 | https://github.com/getplumber/plumber ; https://news.ycombinator.com/item?id=48763749 | 2026-07-02 | An *unrelated* "Plumber" (CI security scorer) | OBS |
| — | https://crt.sh/?q=%25.theplumber.dev | first cert 2026-04-12 | Domain active (renewals through 2026-10-06) | OBS (agent) |
| — | theplumber.dev `/`, `/pricing`, `/docs`, `/examples`, `/privacy`, `/terms`, `/support`; api.theplumber.dev/health; Wayback | — | **Inaccessible** (Cloudflare challenge); Wayback has no snapshots | OBS |

## 2. FailBrief

| URL | Date | Supports | Class |
|---|---|---|---|
| https://failbrief.com/ | sitemap lastmod 2026-09-09 | Positioning, pricing ($0/9/29/59; 25/150/500/2,000), sample comment format, "read-only" and "logs never stored" claims | VENDOR |
| https://app.failbrief.com/docs/how-it-works (REA-captured) and `assets/docsConfig-DD0E7hwL.js` (agent, read as text) | n/d | Pipeline, "doesn't run tests / open PRs", logs-only, flaky definition, MCP, plans | VENDOR (directly observed rendering) |
| https://failbrief.com/privacy-policy/ ; /terms/ | updated 2026-08-09 | OpenAI, AWS us-east-1, Neon, Paddle; retention; no SLA; refund contradiction | VENDOR |
| https://api.github.com/apps/failbrief | created 2026-01-06, updated 2026-04-06 | Permissions incl. `issues:write`, `emails:read`; no `contents` | OBS (re-verified by us) |
| https://api.github.com/orgs/failbrief | org created 2026-01-24 | Org metadata | OBS |
| https://dev.to/aliyaakoub/i-built-an-ai-that-explains-your-ci-failures-in-plain-english-right-inside-your-pr-nef | 2026-05-10 | Founder's launch post; target users; "doesn't fix code" | VENDOR |
| https://www.producthunt.com/products/failbrief ; hunted.space ; launchigniter.com ; foundrlist.com ; kittylaunch.com | 2026 (weeks 23–24; 2026-06-15) | Launch metrics (1 PH upvote, etc.) | INDEP (platform-displayed) |
| RDAP verisign (failbrief.com) | registered 2026-02-11 | Domain age | OBS |

## 3. FixSense

| URL | Date | Supports | Class |
|---|---|---|---|
| https://fix-sense.com/ (pricing section) | n/d | $0/$49/$149; quotas; competitor comparison | VENDOR (re-verified by us) |
| https://fix-sense.com/docs/features/auto-fix | n/d | Playwright/Cypress only; test files and config only; Deflake up to 3 runs; draft PR | VENDOR (re-verified by us) |
| https://fix-sense.com/docs/getting-started/installation ; /configuration ; /features/ai-analysis ; /features/quality-gates ; /features/dashboard ; /integrations/* ; /faq ; /troubleshooting | n/d | Install requirements, inputs, platforms, retention, flakiness scoring | VENDOR |
| https://fix-sense.com/docs/legal/privacy-policy ; /terms-of-service | effective 2026-03-03 | "Never access source code" claim (contradicts permissions); Bulgarian law | VENDOR |
| https://fix-sense.com/docs/guides/case-study-ci-triage | n/d | Anonymous 87% triage-time claim | VENDOR (unverified) |
| https://api.github.com/apps/fix-sense | created 2026-02-24, updated 2026-07-26 | Write permissions on contents, workflows, issues, checks, PRs | OBS (re-verified by us) |
| https://github.com/marketplace/fixsense-ai-ci-failure-analysis-auto-fix ; https://github.com/CopilotMe/fixsense-action ; hub.docker.com/r/sgace11/fixsense-pipe | repo created 2026-03-09 | 5 installs; 4 stars; ~751 pulls | OBS |

## 4. GitHub native and other competitors

| URL | Date | Supports | Class |
|---|---|---|---|
| https://github.blog/changelog/2025-01-15-copilot-users-can-ask-about-a-failed-actions-job-ga/ | 2025-01-15 | Explain error GA, one job at a time | VENDOR |
| https://github.blog/changelog/2026-05-18-one-click-fixes-for-failing-actions-with-copilot-cloud-agent/ | 2026-05-18 | Fix with Copilot (Business/Enterprise) | VENDOR (re-verified by us) |
| https://github.blog/changelog/2026-06-04-fix-with-copilot-for-failing-actions-now-in-pro-pro-and-max/ | 2026-06-04 | Extended to Pro/Pro+/Max | VENDOR (re-verified by us) |
| https://github.blog/changelog/2026-07-23-github-mobile-fix-failing-actions-checks-with-copilot-cloud-agent | 2026-07-23 | Mobile fix | VENDOR |
| https://github.blog/changelog/2026-03-24-ask-copilot-to-make-changes-to-any-pull-request/ | 2026-03-24 | @copilot fixes; no fork PRs | VENDOR |
| https://github.blog/changelog/2026-03-13-optionally-skip-approval-for-copilot-coding-agent-actions-workflows/ | 2026-03-13 | Workflow approval gate | VENDOR |
| https://github.com/githubnext/agentics/blob/main/docs/ci-doctor.md ; https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/ | 2026-02-13 | CI Doctor: automatic, first meaningful error, commit/PR correlation, issue dedupe | VENDOR (re-verified by us) |
| https://github.com/features/copilot/plans ; usage-based billing changelog 2026-04-27 | 2026 | Plans and AI Credits | VENDOR |
| https://github.blog/news-insights/company-news/updates-to-github-copilot-interaction-data-usage-policy/ | 2026 | Training on Free/Pro/Pro+ data unless opted out | VENDOR |
| https://www.sonarsource.com/plans-and-pricing/gitar/ | n/d | Gitar CI diagnosis (real vs flaky vs infra), $20–50/user | VENDOR (re-verified by us) |
| https://neverbreak.ai | n/d | Fix "with proof", free beta | VENDOR (re-verified by us) |
| https://docs.coderabbit.ai/pr-reviews/cicd-pipeline-analysis ; https://cursor.com/workflows/autonomous-agents/ci-autofix ; https://docs.gitlab.com/ci/pipelines/fix_pipeline/ ; https://trunk.io ; https://www.datadoghq.com/blog/bits-ai-test-optimization/ ; https://circleci.com/docs/guides/test/fix-flaky-tests ; https://developer.harness.io/docs/platform/harness-ai/devops-agent/ ; https://depot.dev/changelog/2026-05-08-depot-ci-diagnose ; https://docs.mergify.com/ci-insights/ | various | Overlapping products | VENDOR (agent-collected) |

## 5. Pain, feedback and market evidence

| URL | Date | Supports | Class |
|---|---|---|---|
| https://circleci.com/blog/five-takeaways-2026-software-delivery-report | 2026-02-18 | 70.8% main success; 72 min recovery; ≈3 h for 21–50-employee companies | RESEARCH (vendor telemetry) |
| https://arxiv.org/abs/2602.02307v1 | 2026-02-02 | Flaky builds in GHA: causes include tests, network, dependencies | RESEARCH |
| ICST 2024 "Cost of Flaky Tests in CI" (conf.researchr.org) | 2024 | ≥2.5% of dev time; investigation is the main cost | RESEARCH |
| https://arxiv.org/abs/2501.16495 (ICPC 2025) | 2025-01-27 | LLM explanations correct on simple logs; struggle on complex ones | RESEARCH (small n) |
| ACM TOSEM 10.1145/3749371 | 2025-07 | GHA failure taxonomy (percentages not retrieved) | RESEARCH |
| https://arxiv.org/abs/2604.18334 | 2026-04-20 | AI-agent PRs correlate with lower workflow success | RESEARCH |
| Stack Overflow Developer Survey 2025 (via press) ; DORA 2025 report | 2025 | AI distrust; "almost right" frustration | RESEARCH (secondary for SO) |
| https://news.ycombinator.com/item?id=46614558 | 2026-01-14 | GHA debugging pain (490 points) | INDEP (pattern) |
| https://github.com/orgs/community/discussions/169148 | 2025-08-07 | Unwanted Copilot review noise (~388 upvotes) | INDEP (pattern) |
| https://github.com/orgs/community/discussions/183215 | 2025-12-31 | Agent mode masking bugs by editing tests | INDEP (anecdote plus replies) |
| https://news.ycombinator.com/item?id=49039185 | 2026-07-24 | Registry timeouts dominate failures | INDEP (anecdote) |
| https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime/ | 2026-03-23 | Agent CI limitations; custom CI-failure skill | INDEP-ish (first-party Microsoft, data-backed) |
| https://kudelskisecurity.com/research/how-we-exploited-coderabbit-from-a-simple-pr-to-rce-and-write-access-on-1m-repositories | 2025-08 | GitHub App blast-radius risk | INDEP |
| https://lwn.net/Articles/1020576/ ; pypa/setuptools#4910 | 2025-03 | Upstream release broke CI widely | INDEP |
| JetBrains State of Developer Ecosystem 2025 | 2025-10 | Privacy is the 3rd AI concern (13%) | RESEARCH |

**Not used (unverified):**
- Atlassian "150k hrs/yr";
- Spotify "6–8 hrs/wk";
- Lychee CodeRabbit audit percentages;
- Trunk Team price ($18 vs $0 conflict);
- BuildPulse prices.

## 6. Claim-confidence register (key claims)

| Claim | Basis | Confidence |
|---|---|---|
| The Plumber requests `contents:read`, `pull_requests:write`, `actions/checks:read` and listens to `workflow_run` only | API | **High (OBS)** |
| The Plumber clones the repo and uses an LLM agent with file-reading tools | Listing plus report artifacts | **High (DOC + INF)** |
| The Plumber posted a correct diagnosis about 6 min after run completion, without introducing-commit attribution | API timestamps plus commit diffs | **High (OBS)**, n=1 |
| The Plumber has no commercial traction | 4 installs, free only, no launch | **Medium-high**. Private usage is unknowable. |
| GitHub ships one-click Fix with Copilot for failing Actions to Pro and above | Changelog | **High (VENDOR, verified)** |
| FailBrief reads logs only (no code) | Docs plus manifest lacks `contents` | **High** |
| FixSense auto-fix is limited to Playwright/Cypress test code | Docs | **High (VENDOR, verified)** |
| No competitor sells first-bad-change / external-cause attribution as its core output | Bounded search across about 20 products | **Medium**. Absence of evidence is not evidence of absence. |
| Small teams will pay for attribution | **No direct evidence** | **Low**. This is the key unknown. |
| External causes are ≥20% of failures for the ICP | Indirect (arXiv flaky-build data, incidents) | **Low-medium**. Needs the 200-run labeling. |

## 7. Missing evidence and open questions

1. The Plumber's website content: privacy policy, terms, sub-processors, docs, the `/examples` page, any paid plan. **Needs a human to pass the Cloudflare check**, or the vendor to answer directly.
2. Hands-on behavior of all three products on controlled failures. **Needs a GitHub test org and the user's consent to install apps** (`04 §5`).
3. Paying-customer counts and revenue for all three indie competitors (not public).
4. Reddit discussions (blocked by the fetch tool). Feedback from that channel is under-represented.
5. Actual usage and quality of GitHub "Fix with Copilot" on infra, flaky and dependency failures (no systematic public evaluation).
6. Whether Gitar's "flaky and infra noise" separation includes dependency-drift or first-bad-commit attribution (pricing page only; docs not reviewed).
7. The share of red runs not caused by the triggering push, for small Python/TS teams (planned labeling study).
