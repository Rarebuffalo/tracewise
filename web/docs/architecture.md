# Architecture: website and early-access signup in the Tracewise monorepo

> **As built (2026-10-21).** The approved design and the signup system are implemented. Operator guide:
> `deployment.md`. The proposal below is kept as the design record; the implementation differs as follows.
>
> - **No Astro or npm.** `web/build.mjs` is a ~150-line zero-dependency Node build: partials, build-time
>   `PUBLIC_*` variables, versioned JS/CSS, robots/sitemap, and output checks (no template leftovers, no preview
>   markup, no inline script/style, nothing secret-looking). The preview's HTML/CSS/JS were ported almost verbatim.
>   No Playwright/axe dependency either: `web/test/e2e.mjs` drives headless Chromium over the DevTools protocol.
> - **Hosting chosen: Vercel**, website and API on one origin. `web/vercel_app.py` → `web/site.py` mounts the built
>   site with `app.frontend()` behind the FastAPI waitlist app.
> - **Migrations are not product migration 0011.** The waitlist has its own Alembic chain
>   (`src/tracewise/waitlist/migrations`, revision `w0001`, version table `waitlist.alembic_version`). A dedicated
>   signup database therefore never receives product tables, and product migrations are untouched. Runtime role:
>   `tracewise_waitlist` (`scripts/db/provision_waitlist_role.sql`).
> - **Serverless-safe state.** Rate limits, the email outbox (with leases and retries) and the public aggregate are
>   database tables, not process memory or a worker.
> - **Email.** Modes `disabled` (default, sends and claims nothing), `file` (local only) and `resend`. The owner
>   notification goes to `WAITLIST_OWNER_NOTIFY_EMAIL`, once per confirmed signup.
> - **Tokens in URL fragments** (`/confirm/#token=…`, `/unsubscribe/#token=…`), so they never reach request logs.
>   Confirmation needs a button press. Unsubscribe tokens and follow-up receipts are HMACs (no stored token).
>   Duplicate signups get a decoy receipt, so the follow-up question can't edit someone else's record.
> - **Routes:** `GET /form` (form token), `POST /signup`, `POST /confirm`, `POST /profile`, `POST /unsubscribe`,
>   `GET /count`, `GET /internal/outbox` (cron, Bearer secret), `GET /health`.

**Status (original):** proposal for review. See the "As built" note above for what was implemented.

## 1. What exists today (inspected)
- **Backend:** Python 3.12, FastAPI, Postgres via psycopg/SQLAlchemy, Alembic migrations in
  `src/tracewise/db/migrations` (0001–0010). There are separate database roles:
  - app role (row-level security);
  - system role;
  - owner role (migrations only).
- **Web app:** `src/tracewise/web` exposes only `POST /webhooks/github`, `GET /healthz`, `GET /readyz`.
- **Quality gates:** `make check` / `make ci` (ruff, strict mypy, pytest with disposable PG clusters, docs check, network
  guard). CI: `.github/workflows/ci.yml`, Ubuntu 24.04, uv.
- **No frontend, no Node toolchain** in the repo. `tracewise-brand/` (untracked) holds the logo, fonts and the film.
- **Hosting:** not chosen (`docs/DEPLOYMENT-BLUEPRINT.md`). The production database is not assumed to be reachable.

## 2. Proposed layout
```
tracewise/
├── src/tracewise/                  # existing backend — unchanged by the website
│   ├── web/                        # GitHub App webhook service (unchanged)
│   └── waitlist/                   # NEW (phase 2): early-access API, its own ASGI app
│       ├── app.py                  #   create_app(): routes below, no webhook routes
│       ├── service.py              #   validation, dedupe, tokens, counting
│       ├── email.py                #   EmailSender protocol: NoopSender (dev), ProviderSender (gated)
│       └── settings.py             #   WAITLIST_* settings (pydantic-settings, like config.py)
├── src/tracewise/db/migrations/versions/0011_waitlist.py   # NEW: schema + role grants (owner applies)
├── tests/waitlist/                 # NEW: unit + DB tests on the existing disposable-cluster fixtures
├── web/                            # NEW: the website (static)
│   ├── docs/                       #   this phase's documents
│   ├── design-preview/             #   this phase's static prototype (archived after approval)
│   ├── src/ (pages, components, styles/tokens.css, scripts)
│   ├── public/ (fonts, logo copies, favicon, film poster)
│   ├── package.json, package-lock.json, astro.config.mjs, tsconfig.json
│   └── tests/ (Playwright smoke + axe accessibility)
└── .github/workflows/ci.yml        # + a `web` job (Node 22 LTS): install, check, build, smoke + axe
```

**Why one repo, two clearly separated apps.** The website is static and has its own toolchain (Node). The signup API
is Python in the existing package, with the same conventions, settings style, migrations, logging and tests. There is
no second backend framework.

## 3. Frontend
- **Framework: Astro, static output.** No JavaScript by default. The few interactive parts ship as small scripts:
  - the evidence trail;
  - the report tabs;
  - the loupe;
  - the form.

  Astro also gives us components, scoped CSS, build-time asset handling and extra static pages (confirm, unsubscribe,
  privacy) without shipping a runtime framework. The design preview's plain HTML/CSS/JS ports almost one-to-one.
  The alternative is plain HTML plus esbuild: fewer dependencies, but every page has to be hand-assembled.
- **Styling:** plain CSS with the design tokens (`design-system.md`) as custom properties. No CSS framework.
- **Animation:** CSS transitions plus a little vanilla JS (SVG path measuring, IntersectionObserver). No animation
  library. `prefers-reduced-motion` disables all of it, and nothing is hidden behind motion.
- **Assets:** self-hosted Geist fonts (OFL) and the logo SVGs copied from `tracewise-brand/`. The film is re-encoded
  for the web: H.264 about 2.5 Mb/s at 1280×720 plus a poster, served from the static host or omitted at first.
- **Browser config:** only public values (`PUBLIC_SITE_ORIGIN`). No secrets reach the browser.

## 4. Signup API (`tracewise.waitlist`, a separate process)
A **separate ASGI process** (`uvicorn --factory tracewise.waitlist.app:create_app`):
- It has **its own database role**.
- The GitHub webhook service and its credentials are never exposed to the public website.
- A bug in either service cannot read the other's data.

Routes are served **same-origin** under `/api/waitlist/*` (the static host or proxy routes that path to this process):

| Method | Path | Body / returns | Notes |
|---|---|---|---|
| POST | `/api/waitlist/signup` | `{email, github?, updates?, website (honeypot), ts (signed)}` → **202** `{"status":"check_email"}` | Always the same body and similar timing (no enumeration). 4 KB body cap. |
| POST | `/api/waitlist/confirm` | `{token}` → 200 / 410 (expired) | Reached from the page `/confirm?token=…` via a **button** (POST); mail scanners prefetch GETs. |
| POST | `/api/waitlist/profile` | `{receipt, ci_failure_frequency}` → 204 | Optional follow-up on the success state. `receipt` is an HMAC-signed short-lived token returned by `signup`, bound to the normalised-email hash. |
| POST | `/api/waitlist/unsubscribe` | `{token}` → 204 | Hard-deletes the row. Linked from every email, which also carries `List-Unsubscribe` / one-click headers (RFC 8058). |
| GET | `/api/waitlist/count` | `{"shown": false}` or `{"shown": true, "count_floor": 50, "as_of": "…"}` | Verified rows only, rounded down to 10, hidden below 50, recomputed at most hourly. `Cache-Control: public, max-age=300, s-maxage=600, stale-while-revalidate=3600`. |

### Signup data flow
```
browser ──POST /api/waitlist/signup──▶ waitlist API
  1. size/content-type/Origin checks → 415/413/403
  2. honeypot filled or submitted < 2 s after render (signed ts) → pretend success (202), store nothing
  3. rate limits (in-process TTL buckets; Redis only if >1 replica): HMAC(ip) 5/hour, HMAC(email) 3/day → still 202
  4. validate: WHATWG email grammar, ≤254 chars; GitHub login ^[A-Za-z0-9-]{1,39}$; flag disposable domains (CC0 list)
  5. INSERT … ON CONFLICT (email_normalized) DO UPDATE only when unverified and last mail > 24 h (rotate token)
  6. EmailSender.send_verification(token)   (NoopSender logs "would send" in dev; provider only if EMAIL_SENDING_ENABLED)
  7. 202 {"status":"check_email", "receipt": "<signed, 30 min>"}   ← identical shape for new and existing emails
```

## 5. Database (migration 0011, applied by the owner role like every migration)
```sql
CREATE SCHEMA waitlist;
CREATE TABLE waitlist.signup (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email               text NOT NULL CHECK (length(email) <= 254),
  email_normalized    text GENERATED ALWAYS AS (lower(btrim(email))) STORED UNIQUE,
  github_login        text CHECK (github_login ~ '^[A-Za-z0-9-]{1,39}$'),
  ci_failure_freq     text CHECK (ci_failure_freq IN ('daily','weekly','monthly','rarely')),
  updates_consent     boolean NOT NULL DEFAULT false,
  consent_version     text NOT NULL,                 -- id of the exact wording shown
  created_at          timestamptz NOT NULL DEFAULT now(),
  verified_at         timestamptz,
  verify_token_hash   bytea,                         -- sha256(token); token never stored
  verify_expires_at   timestamptz,
  last_mail_at        timestamptz,
  unsubscribe_hash    bytea NOT NULL,                -- sha256(per-row unsubscribe token)
  disposable_flag     boolean NOT NULL DEFAULT false,
  ip_hmac             bytea,                         -- truncated HMAC, nulled on verify, purged after 30 days
  invited_at          timestamptz
);
CREATE INDEX ON waitlist.signup (verified_at) WHERE verified_at IS NOT NULL;
-- role: tracewise_waitlist — USAGE on schema waitlist; SELECT/INSERT/UPDATE/DELETE on waitlist.signup only.
-- No grants on public.* to this role; no grants on waitlist.* to the existing app/system roles.
```

**Retention job** (same pattern as `tracewise.retention`):
- delete unverified rows after 7 days;
- null `ip_hmac` after 30 days;
- re-consent or purge 12 months after launch (owner decision).

**Deletion:** hard `DELETE`. The backup retention window is documented in the privacy notice.

## 6. Security and privacy
- **Secrets** (environment only, never in the repo or the browser):
  - `WAITLIST_DATABASE_URL`, `WAITLIST_HMAC_SECRET`;
  - `EMAIL_PROVIDER_API_KEY`, `EMAIL_FROM`, `EMAIL_SENDING_ENABLED` (default `false`);
  - optional `ALTCHA_HMAC_KEY`.
  - Placeholders go in `.env.example`; the existing settings test enforces that every setting is documented.
- **Same origin:** no CORS. Mutating routes require `Content-Type: application/json` and an allowed `Origin`.
- **Headers** on the static site:
  - a strict CSP (`default-src 'self'`; no inline scripts — Astro can emit hashed or external scripts);
  - HSTS at the platform;
  - `Referrer-Policy: strict-origin-when-cross-origin`;
  - `Permissions-Policy` minimal.
- **Logs:** event names, outcome and HMAC prefixes only. Never emails, IPs or tokens. This reuses the existing JSON
  logging and scrubber.
- **Abuse escalation:** a self-hosted ALTCHA proof-of-work (no third party) or Cloudflare Turnstile is ready behind
  `WAITLIST_CHALLENGE=off|altcha|turnstile`. Off at launch.
- **No live database or provider access** is needed to develop or test: tests use disposable PG clusters and
  `NoopSender`.

## 7. Hosting (not chosen; requirements only)
- **Static site:** any static host or CDN that can route `/api/waitlist/*` to an origin process (proxy/rewrite rule)
  and set response headers.
- **Waitlist API:** one small container or process with outbound HTTPS to the email provider and private access to
  Postgres.
- **Postgres:** the waitlist schema can live in the future Tracewise cluster (separate role) or in a small separate
  database for pre-launch. **Owner decision**: a separate database decouples the website from the GitHub App's data
  entirely and is simplest to delete later.
- **DNS:** the site domain; SPF/DKIM/DMARC for the email-sending domain.

## 8. Testing
| Layer | What |
|---|---|
| Python unit | email grammar, normalisation, GitHub login rule, honeypot/timing, rate-limit buckets, token hashing/expiry, count rounding/threshold |
| Python DB | upsert dedupe, identical responses for new and existing, verify flow, unsubscribe deletes, role cannot read `public.*` |
| Web | `astro check`, build, Playwright smoke (form states with the API mocked, tabs, no horizontal overflow at 375 px), axe accessibility, a reduced-motion snapshot |
| CI | the existing `check` job unchanged, plus a parallel `web` job. No secrets, no network beyond package install. |
