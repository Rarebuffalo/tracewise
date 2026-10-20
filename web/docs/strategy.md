# Strategy: audience, positioning, conversion, signup, trust and the live count

## 1. Goal of the pre-launch site
Earn the first **~100 genuinely interested users** and learn **which teams feel this pain often enough to install a
pre-release GitHub App**. Success is not raw signups. It is:

1. **Confirmed** (double opt-in) signups.
2. The share with a GitHub username.
3. The share reporting CI failures daily or weekly.
4. Replies to the first pilot email.

## 2. Audience
| Segment | Why they care | How to recognise them |
|---|---|---|
| **Primary:** maintainers and engineers on GitHub Actions with frequent red runs (Python and JS/TS test suites) | Time lost reading logs and rerunning; can install a GitHub App on repos they own | GitHub username present; "daily/weekly" failures |
| Platform/DevEx engineers at small and medium teams | Own CI health; want triage that doesn't touch code | Org-looking email domain; later follow-up |
| Open-source maintainers | Contributor PRs fail CI for unclear reasons | Public repos; GitHub username |

**Not now:** enterprises needing SSO, SOC 2 or data residency. There's nothing honest to offer them yet.

## 3. Positioning
**Category:** CI failure diagnosis for GitHub Actions.
**Position:** the evidence-first, read-only diagnosis that says when it doesn't know.

**One-liner:** *Tracewise reads your failed GitHub Actions run and posts a diagnosis where every claim points to the
line it came from — or says "inconclusive" instead of guessing.*

### Messaging hierarchy
| Question | Answer on the page |
|---|---|
| What is it? | A GitHub App for failed GitHub Actions runs. |
| What problem? | The red check is easy; finding *why* in a long log isn't. You scroll, guess, rerun. |
| How does it work? | Run fails → finds the lines that matter → follows them into the code (read-only) → posts a cited report. |
| What's different? | Receipts, not guesses: citations per claim, stated confidence, "inconclusive" when the evidence runs out, read-only, no code changes. |
| What supports the claims? | The report format itself (shown); the exact permission list; a public build-status receipt. **No metrics**, because none exist. |
| What can early users expect? | Confirm email → a small pilot invite when ready → install on repositories you choose; a pre-release product that wants to hear when it's wrong. |
| Why sign up now? | Be one of the first repositories it reads, and shape what it reports. |

### Copy rules
- Plain verbs ("reads", "finds", "posts").
- Never: "AI-powered", "instantly", "fix", "accuracy", "in seconds", customer logos, or user counts that aren't real.
- "Assessment" and "likely" wording mirrors the real report.
- The tagline appears exactly as **Trace failures. Find answers.**, always inside the official lockup or as its own
  line, never rewritten.
- **Supporting line** (not a replacement): "Receipts, not guesses."

## 4. Conversion design
- **One primary action everywhere:** "Request early access". It appears in the header, the hero (inline email), the
  signup section and the final CTA.
  - No secondary sales CTAs.
  - "Watch the 68-second film" is the only alternative path.
- **Friction budget.**
  - The hero asks for **email only**.
  - The full form adds **one optional field** (GitHub username) and **one optional consent box** (product updates).
- **Progressive profiling.** "How often does CI fail on you?" is asked **after** submit, on the confirmation state, as
  one-tap chips. Role and team size wait for the pilot-invite email.
- **Proof without customers.**
  - A real report format (diagnosed and inconclusive).
  - The permission list.
  - What it won't do.
  - The public build status.
  - The film.
- **Honesty as conversion.** The research shows nobody else displays abstention or readiness. That is the
  differentiator, not a weakness to hide.

## 5. Signup fields
| Field | Status | Why |
|---|---|---|
| Email | **Required** | The only thing we need to invite you |
| GitHub username | Optional, labelled | Strongest relevance signal for a GitHub App; lets us plan invites. Never used to access anything. |
| "Also send product updates" checkbox | Optional, **unticked** | Separate, specific consent for marketing email (PECR/GDPR). The invite emails themselves are what the person asked for. |
| CI failure frequency | Optional, **after submit** | Qualifies demand without lowering top-of-funnel conversion |
| Honeypot `website` | Hidden | Bot trap |
| Role / team size / free text | **Not asked** | Ask in the pilot email instead |

**Consent wording** (stored with a version id and timestamp):

> "We'll email you to confirm, and again when a pilot slot opens. Nothing else unless you tick the box. No sharing,
> no tracking pixels, one-click unsubscribe and deletion."

**Legal note:** the wording, the controller identity and the privacy notice need the owner's (and counsel's) review
before launch. This is not legal advice.

## 6. Trust strategy
- **Status, said once and consistently:** a "Pre-release" chip in the header, a stamp in the hero, the build-status
  receipt, and the first FAQ answer. All four say the same thing.
- **Permissions:** listed exactly, with the reason for the two write permissions.
- **Data:** what's read, what's sent to the model provider *once enabled*, what isn't stored. All of it is quoted from
  the draft privacy notice and labelled draft.
- **Illustrative content** is labelled every time: `acme/storefront` is fictional.
- **No fabricated social proof:** no logos, testimonials, counts or "trusted by".

## 7. Live signup count: recommendation

**Show nothing until it's meaningful and true. Then show a rounded, cached, verified count.**

| Rule | Value | Reason |
|---|---|---|
| What is counted | Rows with `verified_at IS NOT NULL` and not deleted | Bots and typos can't inflate it; it matches "confirmed a spot" |
| Visibility threshold | Hidden below **50** verified | Small numbers are anti-social proof; tiny lists leak identity |
| Display | **Round down to the nearest 10** ("50+", "120+") | Never overstates; hides individual signups |
| Freshness | Recomputed at most **hourly**; served from a cached aggregate | No timing leak ("someone just joined") |
| Transport | `GET /api/waitlist/count` returns `{"count_floor": 50, "as_of": "2026-11-02T14:00Z", "shown": true}` with `Cache-Control: public, max-age=300, s-maxage=600, stale-while-revalidate=3600`; the page fetches once on load; no SSE or WebSocket | Cheap, CDN-friendly, nothing to keep open |
| After a successful signup | The page does **not** increment the public number locally | The person isn't counted until they verify, and the count isn't live |
| Wording | "50+ developers have confirmed a spot." | Exact; no "joining right now" |
| Never | Seeds, offsets, random numbers, "X people viewing", any count when verification is off | FTC "false activity messages"; trust |

The endpoint returns only an integer floor and a timestamp: no emails, IDs, domains or per-row data. Until email
sending is approved and verification exists, **there is no counter** (`shown: false`).

## 8. Measurement (privacy-preserving)
- **Server-side counts:** submits, verifications, GitHub-username share, frequency distribution.
- **Optional page analytics:** self-hosted, cookieless (Umami or GoatCounter) with an opt-out line, or none at
  launch. No third-party trackers or pixels.
- **Ask after signup:** "What made you sign up?", as a reply-to question in the pilot email.

## 9. Owner decisions needed before launch
1. **Legal and privacy.** Controller identity, contact, postal address (CAN-SPAM) and privacy-notice review.
2. **Email provider and domain.**
   - Recommended: Resend free tier, with SPF, DKIM and DMARC set up on the domain.
   - Needs owner approval and an account.
3. **The tilted brand card versus the brand guide.**
   - The guide says "don't rotate the logo".
   - The prototype tilts the paper card (≤1.5°) and counter-rotates the lockup inside it, so the logo itself stays
     exactly level.
   - The owner can confirm this reading or keep the card straight.
4. **Whether to publish the build-status receipt** (recommended).
5. **Pricing statement.** The FAQ currently says "pricing isn't decided".
