# Implementation plan (after design approval)

> **As built (2026-10-21).** Stages 1–3 are implemented and tested locally; Stages 4–5 (staging, launch) are the
> owner's, using `deployment.md`. Differences from this plan:
>
> - Stage 1 used a zero-dependency build instead of Astro, and the form is live, not disabled.
> - Stage 2 used its own migration chain (`w0001`) instead of product migration 0011.
> - Stage 3's email is implemented behind `WAITLIST_EMAIL_MODE`. The default `disabled` sends nothing until the owner
>   configures Resend.
> - Not done:
>   - axe and Lighthouse runs (no npm tooling was added);
>   - any deployment;
>   - real email delivery.
>
> Tests run are listed in `deployment.md` section 14.

Each stage ends with a review point. The plan assumes no hosting, no email provider
and no production database until the owner approves them.

## Stage 0: decisions (owner)
1. **Design:** approve the direction (or note changes) from the design preview.
2. **Brand-card tilt:** approve the counter-rotated reading of the guide, or keep cards straight.
3. **Legal and privacy:**
   - controller identity, contact and postal address;
   - counsel review of the waitlist privacy notice and the consent wording;
   - pricing statement.
4. **Email:** provider (recommended: Resend free tier, 3,000/month, 100/day) and the sending domain.
5. **Data:** a separate pre-launch database, or a schema in the future Tracewise cluster.
6. **Hosting:** static host plus a small process for `/api/waitlist/*`.

## Stage 1: website, static only (no backend)
- Scaffold `web/` with Astro, static output:
  - port the tokens, components and sections from the preview;
  - self-host the fonts and logo;
  - add a re-encoded film (720p, about 2.5 Mb/s) with poster and captions;
  - add `/privacy` (draft banner until approved), `/confirm`, `/unsubscribe`.
- The form posts to `/api/waitlist/signup`. In development a mock route returns 202. In production the form is
  disabled with an honest "opens soon" note until Stage 3 ships.
- **Tests:**
  - `astro check`;
  - Playwright smoke (form states, tabs, loupe on hover devices, no overflow at 375 px, reduced-motion snapshot);
  - axe (no serious violations);
  - Lighthouse budget: LCP < 2.5 s on simulated mobile, CLS < 0.05, JS < 30 KB gz excluding video.
- **CI:** add a `web` job (`actions/setup-node`, Node 22 LTS, `npm ci`, check, build, test). The existing `check` job
  is unchanged.
- **Dependencies:** `astro`, `@playwright/test`, `@axe-core/playwright` (dev). Nothing else.

## Stage 2: waitlist API, local only
- `src/tracewise/waitlist/`:
  - settings;
  - `create_app()`;
  - routes: signup, confirm, profile, unsubscribe, count;
  - service logic;
  - an `EmailSender` protocol with `NoopSender`.
- Migration `0011_waitlist.py`: schema `waitlist`, table `signup`, role grants. Add the role to
  `scripts/db/provision_roles.sql`.
- **Abuse controls:**
  - honeypot;
  - signed timestamp;
  - HMAC-keyed in-process rate limits;
  - identical responses;
  - a disposable-domain flag (CC0 list vendored as data with its license);
  - `WAITLIST_CHALLENGE=off|altcha|turnstile` (off).
- **Retention job:** purge unverified after 7 days; null `ip_hmac` after 30 days.
- **Count:** verified only, floor to 10, hidden below 50, recomputed hourly, cache headers.
- **Tests** (pytest, existing disposable PG fixtures):
  - validation;
  - dedupe;
  - enumeration-safe responses;
  - token expiry and single use;
  - unsubscribe deletes;
  - role isolation (the waitlist role cannot read `public.*`; app roles cannot read `waitlist.*`);
  - count rounding and threshold;
  - logs contain no email, IP or token (log-capture assertion).
- `.env.example` and `docs/CONFIGURATION.md` gain the `WAITLIST_*` and `EMAIL_*` placeholders (the existing settings
  test enforces this).
- `make check` and `make ci` stay green.

## Stage 3: email, gated on owner approval
- `ProviderSender`, behind `EMAIL_SENDING_ENABLED`:
  - verification email (transactional);
  - pilot invite;
  - `List-Unsubscribe` and one-click unsubscribe headers;
  - a postal address in commercial mail.
- Domain authentication (SPF/DKIM/DMARC). A test send to the owner's own address only.

## Stage 4: staging
- Deploy the static site and the API to staging hosts with a staging database. Run the migration with the owner role.
- **Smoke tests:**
  - signup → confirm → count stays hidden;
  - unsubscribe deletes;
  - rate limits trip;
  - headers (CSP, HSTS) present;
  - no secrets in the bundle (grep the build output).
- Check that the privacy notice links work and the copy is final.

## Stage 5: launch readiness checklist
- [ ] Legal and privacy approved; controller and contact filled in.
- [ ] Email sending verified; bounce and complaint handling understood (provider dashboard).
- [ ] Counter shows nothing below 50 verified (verified in staging with seeded **test** rows, then the rows are
      deleted; production starts empty).
- [ ] Analytics: none, or self-hosted cookieless with an opt-out line.
- [ ] Copy audit against `strategy.md` §3 (no metrics, no fixes, status consistent).
- [ ] Accessibility: axe clean, keyboard pass, reduced-motion pass, 375 px pass.
- [ ] Backups and retention jobs scheduled; a deletion request procedure written.
- [ ] Owner sign-off; then deploy. **No deploy, commit or push happens without explicit approval.**

## Effort (rough)
| Stage | Size |
|---|---|
| 1 | 2–3 days |
| 2 | 2–3 days |
| 3 | 0.5–1 day after approval |
| 4 | 1 day plus the platform choice |
