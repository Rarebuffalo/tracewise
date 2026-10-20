# Design system: "Paper Trail" for the web

The website extends the Paper Trail film into an interactive page. **Rule zero:** every paper element explains the
product. Cards are evidence, the cyan thread is the link between evidence and conclusion, stamps are verdicts, and
receipts are reports. Decoration that doesn't carry meaning is cut.

Reference implementation: `web/design-preview/styles.css` (tokens at the top).

## 1. Colour
| Token | Hex | Role | Contrast on `--paper` |
|---|---|---|---|
| `--paper` | #F3EFE6 | The working surface (page background) | — |
| `--paper-2` | #E8E2D4 | Recessed bands (problem, status, final) | — |
| `--card` | #FCFBF8 | Cards, receipts, report sheets | — |
| `--ink` | #0B1220 | Brand Ink: text, buttons, ink stamps | 16.3:1 (18.1 on card) |
| `--ink-2` | #334155 | Secondary text | 9.0:1 |
| `--ink-3` | #5B6474 | Labels, notes | 5.2:1 (4.6 on paper-2) |
| `--red` | #C01B33 | **Failure and guesswork only** (FAILED / RERUN stamps, ✕, error text) | 5.3:1 (4.7 on paper-2, 5.9 on card) |
| `--cyan` | #06B6D4 | **Evidence only**: threads, pins, highlights, citation borders. **Never text on light.** | 2.1:1 (graphics only) |
| `--cyan-ink` | #0B6A80 | Evidence *text* on light (citations, "On the list") and focus rings | 5.4:1 (4.8 on paper-2, 6.0 on card) |
| `--cyan-wash` | rgba(6,182,212,.16) | Highlighted evidence lines | — |
| `--blue`, `--violet` | #3B82F6, #8B5CF6 | **Logo gradient only** | — |

Red is not in the brand guide; it comes from the film's failure stamps. The film's red (#D7263D, 4.3:1 on paper) is darkened here to #C01B33 so small red text passes AA.

The brand-guide rules hold:
- cyan and muted grey are never used for text on light backgrounds;
- the gradient is used only on the symbol;
- no glow, glassmorphism or neon.

## 2. Typography
- **Geist** (the brand guide's approved alternative to Inter; self-hosted, OFL) for everything.
- **Geist Mono** for logs, code, receipt headers, labels and status chips. Ligatures are off so code reads exactly.

| Style | Size | Weight / tracking |
|---|---|---|
| Display (h1) | clamp(2.4rem → 4.6rem) | 750, −0.04em, line-height 1.0 |
| h2 | clamp(1.9rem → 3rem) | 750, −0.025em |
| h3 | 1.25rem | 750, −0.015em |
| Lede | 1.125rem / 1.6 | 400, `--ink-2` |
| Body | 1rem / 1.6 | 400 |
| Label / kicker | 0.68–0.78rem mono, uppercase, +0.14–0.16em | 600–700, `--ink-3` |
| Code / log | 0.7–0.78rem mono | 400; highlighted line 700 `--cyan-ink` on `--cyan-wash` |

## 3. Spacing, grid, depth
- **Spacing:** a 4 px base (`--s1`…`--s10` = 4, 8, 12, 16, 24, 32, 48, 64, 96, 128). Sections use 96 px vertical (64
  on mobile).
- **Width:** content `--wrap` is 1180 px with 24 px side padding (16 on mobile). Two-column sections use 1fr / 1fr or
  0.86fr / 1.14fr.
- **Depth:**
  - `--lift-1` for small cards;
  - `--lift-2` for receipts and sheets;
  - a hover lift for evidence cards only.
  - Shadows are soft, warm and short.
- **Radius:** 3–6 px on paper (paper isn't rounded), 999 px on buttons and chips.

## 4. Components
| Component | Anatomy | Use | Don't |
|---|---|---|---|
| **Brand card** | Card + tape strip + official lockup (tagline-on-light SVG). The card tilts −1.2°; the lockup is counter-rotated so it stays level. | Header (168 px wide), final CTA (420 px) | Recolour, outline, add glow or shadow to the logo itself |
| **Evidence card** (`.ev`) | Pin, mono label, title or excerpt, footer reference (`log lines 12–14`) | The hero trail; one fact each | More than ~4 lines of code; rotation beyond ±3° |
| **Receipt** (`.receipt`) | Card with zig-zag torn top and bottom edges | Status, ledger, signup form, formats | Long prose |
| **Report sheet** (`.sheet`) | 3 px ink top rule, title with symbol, `dl` facts, sections with mono h4 labels, citations | Product preview; mirrors the real report (`report/render.py`) | Inventing sections the report doesn't have |
| **Stamp** (`.stamp`) | Uppercase 850 weight, double rule (border + outline), SVG-noise ink mask, −2 to −9° | Verdicts: FAILED, RERUN (red); CONFIDENCE: MEDIUM, early access (ink); INCONCLUSIVE (slate); ON THE LIST (cyan-ink) | Body copy; more than one stamp per card; red for anything except failure |
| **Pin** | Cyan radial pin, drop shadow | Where the thread attaches | Pins without a thread |
| **Thread** | 3.5 px cyan stroke, round caps, faint offset shadow; cubic curves; routed through gutters, entering each card on the edge that faces the next | Connects evidence in reading order | Crossing text; decorative loops |
| **Citation chip** | Mono, cyan border, `--cyan-ink` text | "log L12–14", "pricing.py:41", "push diff" | Fake links |
| **Ledger** | Two receipt columns: ✓ will / ✕ won't | Differentiation | Competitor names |
| **Status chip** | Dashed outline, cyan dot, mono "PRE-RELEASE" | Header | Removing it while pre-release |
| **Buttons** | Ink pill, 650 weight, pressed shadow | One primary action: "Request early access" | Secondary CTAs competing with it |
| **Inputs** | 48 px min height, 1.5 px border, cyan-wash focus ring, red invalid border with a text error | Signup | Placeholder-only labels |

## 5. Texture
- **Paper grain:** a fixed SVG fractal-noise overlay at about 9% alpha, multiply. One tile, no per-frame cost.
- **Stamp ink:** an SVG turbulence mask, so edges break a little.
- **Torn edges:** CSS gradients, not images.
- **Nothing else.** No paper photos, coffee stains or clip-art.

## 6. Motion
| Motion | Trigger | Duration / easing | Purpose |
|---|---|---|---|
| Evidence cards settle in | Page load | 500–600 ms, staggered 260 ms, `cubic-bezier(.2,.8,.2,1)` | Reading order of the trail |
| Thread draws through the pins | After the first card | 1.4 s | "Tracewise follows the evidence" |
| FAILED and CONFIDENCE stamps press | When the thread arrives | 220 ms overshoot | Verdicts arrive after the evidence |
| Steps thread draws, pins pop | Section enters the viewport (once) | 1.6 s, then 0–1.05 s pin stagger | The sequence |
| Report tabs | Click or arrow keys | Instant | Compare diagnosed and inconclusive |
| Loupe | Pointer over the cited log (hover devices only) | Follows the pointer | Literal "magnify the evidence" |
| ON THE LIST stamp | Successful submit | 240 ms | Confirmation |

**Rules:**
- No loops.
- No scroll-jacking or parallax.
- Never animate layout properties of text.
- Everything readable with motion off.
- `prefers-reduced-motion: reduce` removes all transitions and shows the final states.

## 7. Responsive
- **≤980 px:** sections stack; the nav collapses to the CTA; steps become 2 columns.
- **≤640 px:**
  - the evidence trail becomes a **vertical stack** with the thread running down the left margin through side pins;
  - rotations are removed for legibility;
  - steps become 1 column with the same left-margin thread;
  - the ledger stacks;
  - the status chip hides; the CTA stays.
- No horizontal overflow at 375 px (verified in the preview).

## 8. Accessibility
- Semantic landmarks, a skip link, one h1, headings in order.
- Report tabs use the WAI-ARIA pattern (roving tabindex, arrow keys).
- The trail has an `sr-only` figcaption describing the example. Decorative stamps are `aria-hidden` when the same
  information is in text.
- Form: visible labels, "required/optional" in text, an error tied to the input (`aria-describedby`,
  `aria-invalid`).
  - The success state is announced (to add: `role="status"` in production).
- **Focus:** a 3 px `--cyan-ink` ring.
- **Hit targets:** at least 44 px for chips, buttons and inputs.
- **Contrast** (computed with the WCAG 2.x formula): every text token is ≥ 4.5:1 on every surface it's used on; body text ≥ 9:1; placeholders 4.7:1 on the input background; cyan is never text.
- **Video:** a captions track (the film's VTT), `preload="none"`, poster.

## 9. Brand-guide notes
- **Logo:** the official SVG lockups only, never redrawn.
- **Tilted cards:** the card tilts and the lockup counter-rotates, so the logo itself is never rotated. This is a
  reading of the guide for the owner to confirm (see `strategy.md` §9).
- **Font:** Geist is used instead of Inter, matching the approved brand package.
