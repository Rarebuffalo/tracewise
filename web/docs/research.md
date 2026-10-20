# Research: market, competitors and pre-launch signup patterns

Researched 21 Oct 2026. Live pages were read with a text fetcher. Archived pages (2019–2023 pre-launch eras) were
downloaded from web.archive.org. **Limit:** every page was read as text, so visual art direction is judged from
structure and copy, not from seeing it. Sources that couldn't be read are listed at the end. Quotes are kept short.

## 1. What Tracewise actually is (from the repository, the source of truth for every claim)

- A GitHub App that diagnoses **failed GitHub Actions runs**.
- It reads the failed jobs' logs, the triggering commit's changes and the files it needs, using a short-lived token
  limited to one repository.
- A **deterministic pre-pass** extracts primary error lines before any model is involved. It recognises pytest, Python
  tracebacks, ruff, mypy, tsc, jest, vitest, eslint and pip/npm/uv output.
- A **bounded, read-only investigation**: `read_file`, `grep`, `list_dir`, `get_diff`; at most 12 calls in 120 s.
- A **validator** checks every cited path, line and URL against what was examined. Anything unsupported becomes
  **"inconclusive"**, with next steps.
- It publishes a **Check Run plus a PR or commit comment**. Re-runs update in place.
- Permissions: Actions, Contents, Metadata *read*; Checks, Pull requests *write*.
- **Status:** pre-release.
  - Not run on live GitHub.
  - No AI model connected (OpenAI planned, not enabled).
  - No hosting.
  - No accuracy, latency or cost claims.
  - Privacy notice is a draft.
  - No license chosen.

Sources: `README.md`, `docs/PRIVACY-NOTICE-DRAFT.md`, `docs/DEPLOYMENT-BLUEPRINT.md`, `src/tracewise/report/render.py`.

## 2. CI-failure diagnosis products

| Product | Positioning (short quote) | How it shows the workflow | CTA / friction | Status shown | What we learn |
|---|---|---|---|---|---|
| [Trunk](https://trunk.io) ([blog](https://trunk.io/blog/engineers-shouldn-t-babysit-pipelines-ai-agents-should)) | "Finally, fast CI." | Dashboard screenshots; the blog shows a PR-comment screenshot | "Book a demo" (Calendly); no self-serve | **Inconsistent**: a blog says "Join the waitlist" for its agent; the homepage doesn't mention it | Contradictory status confuses. Be precise and consistent. |
| [Unblocked](https://getunblocked.com) ([PR failure agent](https://getunblocked.com/blog/pr-failure-agent/)) | Context for coding agents; the PR Failure Agent posts a root cause and fix | Screenshot of the triage comment | 21-day free trial | GA | Only posts once it has identified a cause, per its blog. The closest anyone comes to "abstention", and it's buried. |
| [GitLab Duo RCA](https://docs.gitlab.com/user/gitlab_duo_chat/examples/) | "quickly identify and fix CI/CD job failures" | A "Troubleshoot" button in the job log | Paid add-on | GA | Reads only the last 100,000 characters of the log; gives "an example fix"; no accuracy statement. |
| [Datadog CI Visibility](https://www.datadoghq.com/product/ci-cd-monitoring/) | Monitor and improve pipelines | Dashboards, video | Free trial / demo | GA | Platform play; no AI root-cause claim. |
| [BuildPulse](https://buildpulse.io) | "Your CI is slow, flaky, and expensive." | Three lanes plus a demo "push" through its own repo | "Start for free", no card | Core GA; AI review in **early access**, pricing announced at GA | Labels early-access features plainly. |
| [Gitar (Sonar)](https://www.sonarsource.com/products/gitar/) | "Don't just review. Ship." | Bot panel; failed-job list with fixes | "Install free" | GA | **Commits fixes** until green; quotes a vendor "fix rate". |
| [Mergify CI Insights](https://mergify.com/product/ci-insights) | "Your CI is a black box. Open it up." | Dashboard, PR comment, Slack alert | "Get started" | Per-integration "Available now / Coming soon" | Names the exact pain ("guess which job flaked", answers "buried in logs"); honest availability labels. |
| [Harness CI](https://www.harness.io/products/continuous-integration) | Root cause "in seconds" | Pipeline diagram | "Start for free" | GA | Speed claims contradict each other (4x/5x/8x). The cautionary example. |
| [GitHub "Fix with Copilot"](https://github.blog/changelog/2026-05-18-one-click-fixes-for-failing-actions-with-copilot-cloud-agent/) | One-click fix on the failed run's log page | A button | Copilot plans; admin enablement | GA | **Pushes a fix to the branch.** This is the free default developers already have, so the page must say clearly why evidence-first is different, without naming or attacking it. |
| CodeRabbit (search summaries only) | Reads CI failure logs during review, suggests fixes | — | — | GA | — |

**Pattern.** Almost every product ends in a *fix*: some commit it (Gitar, Copilot), some open PRs (Trunk), some
suggest one (Unblocked, GitLab, CodeRabbit). **None publishes confidence, abstention ("inconclusive") or accuracy.**

## 3. Observability: how products explain "from error to cause"

- **[Sentry](https://sentry.io/welcome/) / [Seer](https://sentry.io/product/seer/)**: "Issue → Context → Fix"; Seer
  "explains why your code failed". No accuracy numbers.
- **[Honeycomb](https://www.honeycomb.io)**: shows **one concrete investigation** (a spike) and offers a sandbox
  without signup.
- **[Axiom](https://axiom.co)**: tells cause as a chain; an "Open Playground" with no account.
- **[Better Stack](https://betterstack.com)**: "A human is always in charge".

**Lesson.** The clearest pages show **one real investigation as a trail**, not a feature list.

## 4. Pre-launch pages for developer tools (archived eras)

| Product | What they did before availability | Signup ask |
|---|---|---|
| Linear (2019) | "limited beta release" badge; detailed features; early-customer row; changelog | **One work-email field**, terminal-style placeholder |
| Resend (2022) | "Coming soon" plus one line of value | **Email only** |
| Zed (2022) | **Beliefs before features** (a short manifesto); founders' track record; tech blog | Email + OS + top features + languages (heavier) |
| Warp (2021) | Features marked "Upcoming" linked to public issues; "cloud features are opt-in" | Typeform |
| Supabase (2020) | Per-feature "coming soon"; a **/beta page with public progress and a production-readiness plan** | GitHub sign-in |
| Railway / Tailscale (2019–20) | One plain sentence on how it works; an exit promise ("Disembark Anytime") | "Get Started" |

## 5. Distinctive art direction (structure and copy only; designs not seen)

- **Linear**: "Fig 0.1" captions; the page reads like a technical document.
- **Raycast**: a keyboard as the central metaphor.
- **Family**: playful, captioned demo screens.
- **Teenage Engineering**: restraint as brand.

**Takeaway:** the art direction helps when the **metaphor carries information**. For Tracewise, the paper trail
literally is the product (evidence → citation → conclusion).

## 6. Waitlist mechanics (sources in `strategy.md` §6)

- **Fields.** NN/g: remove anything collectable later; mark optional fields. HubSpot (40k pages): textareas and
  dropdowns depress conversion more than single-line fields. Baymard: field count matters more than step count.
- **Counters.** FTC 2022 dark-patterns report: "false activity messages". FTC 16 CFR 465 (effective 21 Oct 2024)
  covers fake social-media indicators.
  - Small numbers backfire ("join 7 others").
  - Live updates leak timing.
  - Count only **verified** signups, round down, cache, poll.
- **Abuse.** Honeypot, signed timestamp, hashed-key rate limits, identical responses (no enumeration, OWASP).
  - Flag disposable domains rather than blocking them.
  - Self-hosted ALTCHA or Cloudflare Turnstile ready behind a flag.
- **Verification.** Double opt-in (Google sender guidelines; GDPR Art. 7 proof of consent).
  - Single-use hashed tokens, 24–72 h.
  - The confirm step is a button (POST), not a GET link, because scanners prefetch links.
- **Email providers (free tiers today).** Resend 3,000/month (100/day); Postmark 100/month; Mailgun 100/day;
  SES pay-as-you-go. **Nothing is created without owner approval.**
- **Consent.** UK PECR: prospects need specific opt-in for marketing; every message needs an opt-out. CAN-SPAM: a
  postal address in commercial email. Cookieless self-hosted analytics (Umami/GoatCounter) or none.

## 7. Positioning white space (interpretation)

1. **Abstention.** "Says *inconclusive* instead of guessing." Nobody else shows it. Put an inconclusive report on the
   page.
2. **Claim-by-claim citations.** Each claim points to its log line, file at commit, or diff.
3. **Read-only.** "Never writes code, never pushes", backed by the exact permission list.
4. **Single purpose.** One GitHub App, no dashboard, no platform.
5. **Honest pre-GA framing.** A public build-status receipt turns "no customers yet" into credibility.
6. **Against the free fix button.** The honest difference is evidence and abstention, not speed. Don't name or
   disparage anyone.

## 8. Sources not read, or only partly

- web.archive.org through the text fetcher was blocked; downloaded directly instead.
- Read only from search-result summaries:
  - CodeRabbit docs (the changelog URL returned 404);
  - Unblocked's GitHub Actions integration page;
  - GitHub's Copilot technical-preview posts.
- EU UCPD 2021 guidance text: not located.
- EDPB Guidelines 2/2023: secondary summary only.
- Brevo and Friendly Captcha pricing: unreadable.
- Not attempted: Stripe Sessions, Highlight, Depot, Graphite.
- The visual design of every page was not seen; text only.
