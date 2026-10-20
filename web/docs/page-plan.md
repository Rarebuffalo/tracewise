# Page plan: sections, purpose, copy, CTAs

One page, eleven sections, one action. The order follows the research:

1. **Hook and promise:** a visitor understands the product from the hero picture alone.
2. **Pain:** recognition.
3. **Mechanism:** how it works.
4. **Proof by artefact:** the real report, including an inconclusive one.
5. **Difference:** receipts, not guesses.
6. **Fit:** who it's for.
7. **Film**
8. **Honest status**
9. **Signup**
10. **Objections:** FAQ.
11. **Final CTA**

The prototype implements all of them: `web/design-preview/index.html`.

| # | Section | Purpose | Copy (as in the prototype) | CTA |
|---|---|---|---|---|
| — | **Header** | Brand recall plus status, always visible | Brand card (lockup with tagline), nav: How it works · The report · Status · FAQ, chip **PRE-RELEASE** | **Request early access** (sticky) |
| 1 | **Hero** | Answer "what is it" in 5 seconds; show the product as an evidence trail | Stamp: *Early access · pre-release*. **H1:** "Your CI failed. Follow the paper trail to *why*." **Lede:** "Tracewise is a GitHub App for failed GitHub Actions runs. It reads the failed job's log, the code at that commit and what your push changed, then posts a short diagnosis where every claim points to the line it came from. When the evidence isn't enough, it says so instead of guessing." **Visual:** failed run (FAILED stamp) → the lines that matter (log lines 12–14) → the code at `9f3c2e1` → the Tracewise check run (likely root cause, citations, CONFIDENCE: MEDIUM), joined by one cyan thread. Labelled *Illustrative example · acme/storefront*. | Inline email + **Request early access**; note: "We'll send one email to confirm, then only early-access news. Unsubscribe in one click." Secondary: *Watch the 68-second film* |
| 2 | **Problem** | Recognition, not fear | **H2:** "The red check is the easy part." "A failed run hands you an exit code and a log that can run to thousands of lines… So you scroll. You guess. You rerun it and hope it was flaky. Tracewise does the reading for you, and shows its work." Visual: the film's guess posters with a RERUN stamp | — |
| 3 | **How it works** | Accurate mechanism in four steps | **H2:** "From a red check to a receipt, in four steps." 01 *A run fails*; 02 *It finds the lines that matter* (deterministic pre-pass, before any AI); 03 *It follows them into the code* (read-only: read, search, list, diff; 12 calls / 120 s); 04 *It posts the receipt* (every citation checked; a Check Run plus PR or commit comment). Pinned cards on one thread. | — |
| 4 | **The report** | Proof by artefact; show honesty | **H2:** "What lands on your pull request." Tabs: **Diagnosed** / **Inconclusive**. The sheet mirrors the real renderer: title, likely root cause (assessment), confidence with basis, what failed (observed in the log), problematic code (observed at commit), suggested fix (text only; not applied), attribution (computed from the push's diff). The inconclusive tab uses the real wording "a deliberate outcome, not an error in your build", plus *What would help*. Annotations 1–3; a loupe over the cited log. | — |
| 5 | **Receipts, not guesses** | Differentiation without naming competitors | Ledger, *Tracewise will:* cite evidence behind every claim; state confidence and why; say inconclusive; ask only for the listed permissions. *Tracewise won't:* push commits, open PRs or apply fixes; run your code or reach other systems; keep your full logs or source files*; pretend to know. *Footnote: as implemented and in the draft privacy notice. | — |
| 6 | **Who it's for** | Self-qualification | **H2:** "For whoever gets the red check." Receipt: *Recognises the output of* pytest · Python tracebacks · ruff · mypy · tsc · jest · vitest · eslint · pip · npm · uv. "GitHub Actions only, for now." | — |
| 7 | **Film** | Emotion and memorability; an alternative to reading | *Paper Trail*, 68 s, captions, poster frame | — |
| 8 | **Status** | Honest pre-GA framing as credibility | **H2:** "Honest about the build, too." Build-status receipt: ✓ pipeline built and tested offline; ✓ evidence validator and report format; ☐ first runs on live GitHub repositories; ☐ AI model provider connected; ☐ hosted service. | — |
| 9 | **Early access** | Convert; set expectations | **H2:** "Be one of the first repositories it reads." Next steps: confirm your email → wait for a pilot slot (small groups) → install it where you choose. Form: Email (required), GitHub username (optional), unticked "Also send me occasional product updates". Success: ON THE LIST stamp, "We sent a confirmation link… expires in 24 hours", then the one-tap question "How often does CI fail on you?". Counter: hidden below 50 verified. | **Request early access** |
| 10 | **FAQ** | Remove objections truthfully | Can I use it today? · What access does it ask for? · What happens to my logs and code? · Will it change my code? · What if it's wrong? · Which projects does it work with? · How is this different from an AI "fix it" button? · What will it cost? · How do I get off the list? | Links to the form |
| 11 | **Final CTA** | Brand recall plus a last invitation | Large brand card (lockup with tagline). "Next time CI fails, read the receipt — not the whole log." | **Request early access** |
| — | **Footer** | Truth in small print | "Pre-release software. Examples use a fictional repository, acme/storefront." · Privacy (draft) | — |

## Production pages beyond the landing page
- `/confirm`: "Confirm your spot" button (POST); success and expired states.
- `/unsubscribe`: one-click removal; states "removed" and "already gone".
- `/privacy`: the reviewed waitlist privacy notice (purpose, data, retention, controller, deletion).

## Copy checks
- **Avoided words:** AI-powered, instantly, in seconds, accuracy, fix (as something Tracewise does), trusted by,
  customers, numbers that aren't real.
- **Status:** pre-release is stated identically in four places.
- **Labels:** every example is labelled illustrative; the repository is fictional.
- **Tagline:** "Trace failures. Find answers." appears only inside the official lockup. The final-CTA heading uses it
  as an accessible name.
