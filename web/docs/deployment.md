# Deploying the Tracewise website and waitlist

**Status (2026-10-21):** implemented and tested locally. **Not deployed.** Nothing here has been run against
Vercel, Resend or a hosted database. Every step below is for the owner to do; no account, domain, key or inbox has
been created or assumed.

> **Signups stay closed until email works.** With `WAITLIST_EMAIL_MODE=disabled` (the default), or, on Preview and
> Production, without `WAITLIST_OWNER_NOTIFY_EMAIL`, the API refuses new signups (`503 signups_closed`, nothing is
> stored). The page shows "Signups aren't open yet" and disables the buttons. Confirmation and "remove me" links keep
> working. `GET /api/waitlist/health` reports `"accepting_signups": true|false`. So a deployment without email
> configured is safe to put online: it simply isn't taking signups yet.
>
> **Confirmed on Vercel:** the build step (`node web/build.mjs`, from `[tool.vercel.scripts]`) runs. The first
> deployment reached it and stopped at the production identity guard (section 5, troubleshooting).
>
> **Not verified on Vercel or with real email** (everything else was tested locally; see section 14):
> - installation of the Python dependencies and start-up of the FastAPI function from `[tool.vercel] entrypoint`;
> - CDN promotion of `app.frontend()`;
> - `vercel.json` headers and cron;
> - `.vercelignore` on Git deployments;
> - Resend delivery and DNS;
> - Turnstile.

Contents:
1. What gets deployed
2. Database
3. Email provider and sending domain
4. Owner notification inbox
5. Environment variables
6. Deploy steps
7. URL and custom domain
8. End-to-end test after deploying
9. Verifying the owner notification
10. Failed deliveries and retries
11. Export and deletion requests
12. Manual steps checklist
13. Features
14. Tests run
15. Known limitations and open questions

---

## 1. What gets deployed

One Vercel project serves both halves of the site from the same origin:

| Path | Served by | Source |
|---|---|---|
| `/`, `/confirm/`, `/unsubscribe/`, `/privacy/`, assets, film | Vercel's CDN (static files) | `web/src`, `web/public` → `node web/build.mjs` → `web/dist` |
| `/api/waitlist/*` | One Vercel Python Function (FastAPI) | `src/tracewise/waitlist/`, entrypoint `web/vercel_app.py` |
| Daily retry job | Vercel Cron → `GET /api/waitlist/internal/outbox` | `vercel.json` |

External services you need:

- **Vercel**, to host the site and the API.
- **A PostgreSQL 15+ database.** Neon (available through the Vercel Marketplace) or Supabase both work. Use a
  database used only for the waitlist.
- **Resend**, to send email (free tier: 3,000/month, 100/day).
- **A domain you control**, for the email sender. It is needed even if the site stays on `*.vercel.app` for now.
- **Optional:** Cloudflare Turnstile, to block bots.

Why this shape:

- **FastAPI on Vercel.** It runs on Vercel as a Python Function. Vercel's FastAPI support reads
  `[tool.vercel] entrypoint` in `pyproject.toml`. `app.frontend()` serves the built site, and Vercel promotes those
  files to its CDN.
- **Same origin.** The browser never makes a cross-origin call, so no CORS is needed.
- **Built for serverless.** Rate limits, the email outbox and the public counter all live in the database. Nothing
  depends on process memory or a long-running worker.

The GitHub App backend (`src/tracewise/web`) is **not** part of this deployment and is not affected by it.

## 2. Database

1. **Create a database** at your provider, for example a Neon project named `tracewise-waitlist`. Keep two
   connection strings, both secrets that never go in git:
   - the **owner/admin** one, for migrations from your machine;
   - the **pooled** one, for the runtime role below.
2. **Create the least-privilege runtime role.** Review `scripts/db/provision_waitlist_role.sql`, run it once as the
   owner in the provider's SQL console, then set a password for the role in that console:
   `ALTER ROLE tracewise_waitlist PASSWORD '…'`. Generate the password; don't reuse one. The role:
   - **can:** SELECT/INSERT/UPDATE/DELETE on the five `waitlist.*` tables, and nothing else;
   - **cannot:** create, alter or truncate tables, or read any other schema.
3. **Run the migration from your machine** with the owner URL. It is never run by the web process.

   ```bash
   WAITLIST_DATABASE_URL_MIGRATIONS='postgresql://OWNER:…@…/…?sslmode=require' uv run python -m tracewise.waitlist.migrate upgrade
   ```

   What the migration does:
   - It only **creates** objects: schema `waitlist`, five tables, and the grants to `tracewise_waitlist`.
   - It keeps its own version table, `waitlist.alembic_version`, separate from the product's migration history. It
     never touches other schemas.
   - Running it again is a no-op.
   - The downgrade drops the five tables. **Never run a downgrade against real data.**
4. **Check it:** `… migrate current` should print `w0001 (head)`.
5. **Build the runtime URL** for `WAITLIST_DATABASE_URL`:
   `postgresql://tracewise_waitlist:PASSWORD@POOLED-HOST/DB?sslmode=require`.
6. **Region.** Put the Vercel Function in the same region as the database: Vercel → Project → Settings → Functions →
   Region.

**Sharing a database with the product later.** That is possible but not recommended. It works because the schema
and the roles are isolated, and the tests prove it: the waitlist role cannot read product tables, and the product
roles cannot read `waitlist.*`.

## 3. Email provider and sending domain

1. Create a Resend account.
2. Add a sending domain. A subdomain such as `updates.example.com` keeps the reputation of your main domain separate.
3. Add the DNS records Resend shows you (SPF and DKIM). Adding a DMARC record for the domain is recommended. Wait
   until Resend shows the domain as **Verified**.
4. Create an API key with **Sending access** only, restricted to that domain, and put it in `RESEND_API_KEY` in
   Vercel. Never paste it anywhere else.
5. Set `WAITLIST_EMAIL_FROM`, for example `Tracewise <hello@updates.example.com>`. Optionally set
   `WAITLIST_EMAIL_REPLY_TO` to the inbox you read.
6. Set `WAITLIST_EMAIL_MODE=resend` **only after** the domain shows Verified. Until then, the default `disabled`
   mode sends nothing, records nothing as sent, and **keeps signups closed** (see the note at the top). Enabling
   email = set the variables, redeploy, then check that `/api/waitlist/health` says `"accepting_signups": true`.

Additional points:

- Every email has a **"remove me" link**, which deletes the signup, and a `List-Unsubscribe` header.
- If you'll send commercial mail, set `WAITLIST_POSTAL_ADDRESS`; some places require a postal address in the footer.
- No open or click tracking is requested by the code. Keep Resend's open and click tracking **off** for the domain.
  The privacy notice says there is none.
- Resend deduplicates retries with the `Idempotency-Key` header, kept for 24 hours. The code sends a stable key per
  owner notification and a per-attempt key per verification email. Each verification attempt carries a new link, so
  the email body changes and the key has to change with it.

## 4. Owner notification inbox

- Set `WAITLIST_OWNER_NOTIFY_EMAIL` to the inbox that should receive **one email per confirmed signup**. There is no
  default and no address in the code.
- **When it's sent:** only after the person clicks the confirmation link. It is never sent for unverified signups,
  and never twice for the same signup.
- **What it contains:** the email address, confirmation and signup times (UTC), GitHub username, product-updates
  consent, the CI-failure answer (if given before confirming; see section 15) and the disposable-domain flag.
- **If the inbox isn't set:** on Preview and Production, **signups stay closed** until it is. (Locally, and if the
  variable is removed later, notifications wait in the outbox with the error `WAITLIST_OWNER_NOTIFY_EMAIL is not
  set`, re-checked hourly, without using up retry attempts. Set the variable and redeploy; the next job sends them.)

## 5. Environment variables

Placeholders and comments are in `web/.env.example`. Set real values in **Vercel → Project → Settings → Environment
Variables**. Every variable there has an **Environments** checkbox list:

- **Production:** deployments of the production branch (`main`). The first deployment of a new project is a
  Production deployment.
- **Preview:** deployments of every other branch and pull request.
- **Development:** only `vercel dev` and `vercel env pull` on your machine. Not needed for this project, which runs
  locally with `web/dev.py`.

A variable only reaches the environments you tick. Use **separate values** for Production and Preview for every
secret, and ideally a separate database (or branch) for Preview.

There are two kinds of variable, and they behave differently.

### 5a. Build-time variables (`PUBLIC_*`): read by `node web/build.mjs`, baked into the static HTML

- These are read **once, during the build**, and written into the generated pages. `PUBLIC_OPERATOR_NAME` and
  `PUBLIC_CONTACT_EMAIL` are printed on `/privacy/`.
- They are **public, not secrets**: anyone can read them in the page source. Never put a secret in a `PUBLIC_*`
  variable. The build only reads `PUBLIC_*` (plus `WAITLIST_VERIFY_TTL_HOURS`, a number), and it fails if any output
  looks like a key or database URL. A test proves that runtime secrets set during the build never reach the output
  or the build log.
- **Changing one has no effect until you rebuild.** Use Deployments → ⋯ → **Redeploy**: a redeploy runs the build
  again with the current values. A redeploy that reuses the build cache still reruns `node web/build.mjs`, which
  regenerates every page from scratch.
- Both builds read the values of their own environment:
  - A **Production** build gets the Production values.
  - A **Preview** build gets the Preview values.

| Variable | Production | Preview | Value |
|---|---|---|---|
| `PUBLIC_OPERATOR_NAME` | **required** (build fails without it) | recommended | The person or organisation that runs the waitlist, as it should appear in the privacy notice |
| `PUBLIC_CONTACT_EMAIL` | **required** (build fails without it) | recommended | The inbox people write to for privacy questions and data requests |
| `PUBLIC_DATABASE_PROVIDER` | recommended | optional | e.g. `Neon (AWS us-east-1)`; otherwise the notice says "named here before launch" |
| `PUBLIC_SITE_URL` | after the custom domain is live | no | Canonical origin, e.g. `https://www.example.com` |
| `PUBLIC_TURNSTILE_SITE_KEY` | optional | optional | Turnstile site key (pair with `WAITLIST_TURNSTILE_SECRET`) |
| `PUBLIC_ALLOW_INDEXING` | optional | no | Default: Production is indexed, Preview is not |
| `PUBLIC_API_BASE` | leave unset | leave unset | Only for a separate API origin |

**Why the two identity values are required.** The privacy notice must say who runs the waitlist and how to reach
them (section "Who runs this"). Without them the page would show a red "not set" placeholder.

- **Preview builds:** the placeholder is allowed. They are noindex and the build prints a warning.
- **Production builds:** they are refused. A Production build also rejects obvious placeholders: names such as
  `CHANGE_ME`, `TODO`, `TBD`, `Your Name` or `example`, and addresses on `example.com/.org/.net`, `.invalid`,
  `.test`, `.example` or `localhost`.
- There is no default, and nothing is substituted.

### 5b. Runtime variables: read by the API function on every cold start

- These are read when the Python function starts. They never reach the browser.
- Changing one also needs a **Redeploy**, because Vercel functions get environment values at deployment.
- Mark every secret as **Sensitive** in Vercel.

| Variable | Secret | Production | Preview | Value |
|---|---|---|---|---|
| `WAITLIST_ENV` | no | `production` | `preview` | |
| `WAITLIST_DATABASE_URL` | **yes** | required | required | Runtime-role URL, pooled host, `sslmode=require` |
| `WAITLIST_SECRET` | **yes** | required | required (different) | ≥ 32 random chars: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `WAITLIST_EMAIL_MODE` | no | `resend` | `resend` | `disabled` keeps signups closed |
| `RESEND_API_KEY` | **yes** | required | required | Sending-only key for your verified domain |
| `WAITLIST_EMAIL_FROM` | no | required | required | e.g. `Tracewise <hello@updates.your-domain>` |
| `WAITLIST_OWNER_NOTIFY_EMAIL` | no (personal data) | required | required | Your inbox for confirmed-signup notifications |
| `CRON_SECRET` | **yes** | required | optional | ≥ 32 random chars; Vercel Cron sends it as a Bearer token (crons run on Production only) |
| `WAITLIST_PUBLIC_SITE_URL` | no | after custom domain | no | Empty = the Vercel production URL; Preview uses its own deployment URL |
| `WAITLIST_EMAIL_REPLY_TO` | no | optional | optional | Inbox for replies |
| `WAITLIST_POSTAL_ADDRESS` | no | optional | optional | Shown in email footers |
| `WAITLIST_TURNSTILE_SECRET` | **yes** | optional | optional | With `PUBLIC_TURNSTILE_SITE_KEY` |
| `WAITLIST_VERIFY_TTL_HOURS` | no | optional | optional | Default 48; also read by the build for the copy |
| `WAITLIST_ALLOWED_ORIGINS` | no | leave empty | leave empty | Same origin needs no CORS |
| `WAITLIST_DATABASE_URL_MIGRATIONS` | **yes** | **never in Vercel** | **never in Vercel** | Owner URL, for migrations from your machine only |

Set automatically by Vercel, not by you:

- `VERCEL=1`: client-IP headers are then trusted for rate limiting;
- `VERCEL_ENV`: `production` or `preview`, which decides the build guard and indexing;
- `VERCEL_URL`: the email-link origin on preview deployments;
- `VERCEL_PROJECT_PRODUCTION_URL`: the fallback for email links and the canonical URL.

### 5c. What happens when something is missing

| Situation | Result |
|---|---|
| Production build without `PUBLIC_OPERATOR_NAME` / `PUBLIC_CONTACT_EMAIL` (or with placeholders) | **Build fails** with a message naming the variable; nothing is deployed |
| Invalid runtime setting (e.g. `WAITLIST_SECRET` shorter than 32, `resend` without key, `production` without an https site URL) | The site still loads. Every `/api/waitlist/*` route returns 503 and nothing is stored. `/api/waitlist/health` lists the setting's *name* under `config_error`; the function log has the message. Values are never printed |
| `WAITLIST_EMAIL_MODE=disabled`, or (Production/Preview) no `WAITLIST_DATABASE_URL` or no `WAITLIST_OWNER_NOTIFY_EMAIL` | **Signups closed:** the form says "Signups aren't open yet"; `/health` shows `"accepting_signups": false` |
| Database unreachable | 503 "temporarily unavailable"; nothing stored |

### Troubleshooting: "production builds need PUBLIC_OPERATOR_NAME and PUBLIC_CONTACT_EMAIL"

The deployment was a Production build (`VERCEL_ENV=production`) and one or both values were not set for the
**Production** environment. This includes the very first deployment of a new project.

1. In Vercel → Project → Settings → Environment Variables, add `PUBLIC_OPERATOR_NAME` and `PUBLIC_CONTACT_EMAIL` with
   your real operator name and contact inbox. Tick **Production**, and Preview if you want previews to show them.
   They are public, so they don't need the Sensitive flag.
2. Deployments → the failed deployment → ⋯ → **Redeploy**.
3. Check that the build log now ends with `build: 5 pages, … (indexing on, …)`, and that `/privacy/` shows your
   details.

## 6. Deploy steps

Prerequisites: sections 2–5 done.

1. **Push the website commits.** The website, the waitlist code and the 720p film are committed on `main`
   (`c195dc6`…`172cd57`).
2. **Create the Vercel project.** Vercel → Add New → Project → import the GitHub repository. Framework preset:
   **FastAPI**, or "Other"; the `[tool.vercel]` entrypoint is what matters. Root directory: the repository root.
3. **Check the build settings:**
   - The build step comes from `pyproject.toml` → `[tool.vercel.scripts] build = "node web/build.mjs"`.
     **Confirmed on Vercel:** the first deployment ran it, and failed in its production guard (section 5,
     troubleshooting).
   - If a deployment ever shows no `build:` line, set **Build Command** to `node web/build.mjs` in Project Settings.
   - A missing `web/dist` fails the build itself. On Vercel the function does not re-check the directory, because
     the static files may be served from the CDN rather than bundled with it.
   - Python: the project needs Python ≥ 3.12. Check the version in the build log.
4. **Add the environment variables.**
   - Build-time (5a): `PUBLIC_OPERATOR_NAME` and `PUBLIC_CONTACT_EMAIL` at least, ticked for **Production**.
   - Runtime (5b): ticked for Production, and with separate values for Preview if you'll use preview deployments.
5. **Deploy, or Redeploy the failed deployment.** Check that:
   - the build log contains `build: 5 pages, … (indexing on, …)`;
   - `/privacy/` shows your operator details;
   - `/api/waitlist/health` returns `"accepting_signups": true`. If it says false, or shows `config_error`, see 5c.
6. **Check the upload.** `.vercelignore` keeps `research/`, `tracewise-brand/`, `tests/`, `docs/` and local files out
   of the deployment. Confirm this in the deployment's **Source** view: no `research/` folder should be listed.
7. **Cron.** `vercel.json` schedules the retry job once a day (`17 9 * * *`). On Vercel's Hobby plan cron jobs are
   limited (reportedly to once a day); on Pro you can change it to every 15 minutes (`*/15 * * * *`). Emails are
   normally sent immediately during the request; the cron only retries failures.
8. **Turnstile (optional).** Create a Turnstile widget for your hostname(s), then set `PUBLIC_TURNSTILE_SITE_KEY` and
   `WAITLIST_TURNSTILE_SECRET`, and redeploy.

## 7. URL and custom domain

- **First deployment:** the site is at the Vercel-assigned `https://<project>.vercel.app`. Leave
  `WAITLIST_PUBLIC_SITE_URL` and `PUBLIC_SITE_URL` empty; email links and the canonical URL use
  `VERCEL_PROJECT_PRODUCTION_URL` automatically.
- **Custom domain later:**
  1. Vercel → Project → Domains → add the domain, and follow the DNS instructions.
  2. Then set `WAITLIST_PUBLIC_SITE_URL=https://www.example.com` and `PUBLIC_SITE_URL=https://www.example.com`, and
     redeploy.
  3. Links in emails already sent keep pointing at the `vercel.app` URL. They still work, as long as that URL keeps
     serving the project, which Vercel does by default.
- If Turnstile is on, add the new hostname to the Turnstile widget.
- **Preview deployments:**
  - Email links point at the preview deployment itself (`VERCEL_URL`), unless `WAITLIST_PUBLIC_SITE_URL` is set for
    the Preview environment.
  - Previews are usually behind Vercel's Deployment Protection, so opening a confirmation link from the email needs
    you to be logged in to Vercel in that browser.
  - Give Preview its own database (or database branch) and its own `WAITLIST_SECRET`, so test signups never mix
    with real ones.

## 8. End-to-end test after deploying

Use an inbox you own.

1. `curl -s https://<site>/api/waitlist/health` returns `{"ok": true, "email_mode": "resend", "accepting_signups":
   true}`. If `accepting_signups` is false, the email mode or owner inbox is not set: fix that first.
2. Open the site and check the page renders. The counter is hidden; it stays hidden until 50 confirmed signups.
3. Sign up with your own address. Add a GitHub username, tick or leave the updates box, and answer the CI question.
4. **The email arrives.**
   - If not, check spam.
   - Then run `python -m tracewise.waitlist.admin outbox` with `WAITLIST_DATABASE_URL` set locally.
   - The `last_error` column shows the provider's answer, for example an unverified domain.
5. Click **Confirm my spot**. The page shows "You're on the list". Click it again: "already confirmed".
6. **Owner notification:** see section 9.
7. Click "remove me" in the email. The page says "You're off the list". `admin stats` shows the count drop.
8. **Headers:** `curl -sI https://<site>/ | grep -iE 'content-security|strict-transport|x-frame'` shows the headers
   from `vercel.json`.
9. **Retry job:** `curl -s -H "Authorization: Bearer $CRON_SECRET" https://<site>/api/waitlist/internal/outbox`
   returns `{"delivery": …}`. Without the header it returns 401.

## 9. Verifying the owner notification

- After step 5 above, `WAITLIST_OWNER_NOTIFY_EMAIL` receives "New confirmed Tracewise signup: you@…".
- **If it doesn't arrive:** run `python -m tracewise.waitlist.admin outbox --status pending` (or `failed`). An
  `owner_notify` row with `last_error` explains why:
  - inbox not set;
  - domain not verified;
  - rate limited.
- **Once sent:** the row has `status = sent`, `provider = resend` and Resend's message id. Look that id up in Resend →
  Emails to see delivery details.
- Nothing is ever marked `sent` without a successful answer from the provider.

## 10. Failed deliveries and retries

| Event | Behaviour |
|---|---|
| Provider down, timeout, 429, 5xx | Row goes back to `pending` with a backoff (1 min → 24 h), at most 8 attempts, then `failed` |
| Permanent error (e.g. 403 unverified domain, 422 bad address) | Row is marked `failed` immediately with the sanitised error (addresses removed) |
| Function crashes mid-send | The 2-minute lease expires and the next run reclaims the row; owner notifications reuse the same Idempotency-Key, so Resend does not send twice within 24 h |
| Email mode `disabled` | Nothing is claimed, attempted or marked; rows wait |
| Confirmation succeeded but email failed | The confirmation stands (never rolled back); the notification is retried |

Commands (run locally with `WAITLIST_DATABASE_URL` and the email variables set):

```bash
uv run python -m tracewise.waitlist.admin outbox --status failed
```

```bash
uv run python -m tracewise.waitlist.admin retry --failed
```

```bash
uv run python -m tracewise.waitlist.admin process
```

`retry ID …` re-queues specific rows. Fix the cause first: verify the domain, set the inbox.

## 11. Export and deletion requests

- **Export:**
  - `admin export` writes a CSV of confirmed signups to stdout; `--all` includes unconfirmed ones and `--json`
    switches the format.
  - The columns are fixed: email, status, times, GitHub username, consent and its time and version, CI answer,
    disposable flag. There are no internal ids or tokens.
  - Store exports somewhere private and delete them when you are done.
- **Deletion:**
  - The person can use the "remove me" link in any email.
  - Or you run `admin delete person@example.com`.
  - Either way it is a hard delete: tokens and delivery records cascade.
  - Also delete the matching owner-notification email from your inbox (the privacy notice says this happens on
    request).
- **Access/correction:** reply from the contact address. Correct a field with the provider's SQL console as the
  owner role, or delete the signup and let the person sign up again.
- **Retention:** `admin purge`, also run by the daily cron, deletes unconfirmed signups older than 7 days, expired
  tokens, old delivery rows and rate-limit windows. Confirmed signups are kept until removed.
- **Internal numbers:** `admin stats` prints exact counts for you. The public counter only ever shows a figure rounded
  down to a multiple of 10, from 50, recomputed at most hourly.

## 12. Manual steps checklist

- [ ] Review and commit the untracked website and waitlist files (nothing was committed or pushed for you)
- [ ] Choose the operator name and contact address; set `PUBLIC_OPERATOR_NAME` and `PUBLIC_CONTACT_EMAIL`
- [ ] Have the privacy notice (`web/src/privacy.html`, "draft") and the consent wording reviewed
- [ ] Create the database; run `provision_waitlist_role.sql`; set the role password; run the migration
- [ ] Create a Resend account; verify a sending domain (SPF, DKIM, DMARC); create a sending-only key
- [ ] Decide the owner inbox; set `WAITLIST_OWNER_NOTIFY_EMAIL`
- [ ] Generate `WAITLIST_SECRET` and `CRON_SECRET` (separately for Production and Preview)
- [ ] Create the Vercel project, set the variables, deploy; check the build log and the Source view
- [ ] Set the Function region next to the database
- [ ] Run the end-to-end test (section 8) with your own address
- [ ] Optional: Turnstile; custom domain; Vercel Pro for a more frequent retry cron
- [ ] Keep Resend open/click tracking off

## 13. Features

**Website**

- The approved Paper Trail design, ported from `web/design-preview/`:
  - hero with the evidence trail;
  - the problem;
  - how it works;
  - the Diagnosed/Inconclusive report preview with the loupe;
  - the difference;
  - who it's for;
  - the film (720p, captions);
  - status;
  - signup;
  - FAQ;
  - final CTA.
- Extra pages: confirm, unsubscribe, privacy (draft) and 404.
- The design preview's banner, review panel and fake form handling are removed.
- Zero npm dependencies: a small Node build with partials, asset versioning, robots and sitemap. JS modules only
  where needed; with JS off, every page still reads correctly.
- Responsive down to 375 px, with `prefers-reduced-motion` respected.
- Accessibility:
  - keyboard-operable tabs;
  - skip link;
  - labelled fields with linked error messages;
  - focus moved to the result after submitting.
- Content-Security-Policy as a meta tag and as a header. No inline script or style; no third-party requests (except
  Turnstile, if enabled).

**Signup**

- Fields: email (required), optional GitHub username, and an optional **unchecked** product-updates box. Consent is
  stored with its time and wording version.
- **Validation:**
  - in the browser and on the server, with the same rules;
  - length limits;
  - JSON only, 4 KB maximum;
  - unknown fields refused (no mass assignment).
- **Normalisation and dedupe:** addresses are trimmed and lower-cased; a unique constraint stops duplicates, including
  concurrent ones.
- **Generic responses:**
  - A new, pending or confirmed address gets the same answer, so nobody can find out who is on the list.
  - A repeat submission never changes stored data.
  - A pending address gets a new link at most every 10 minutes.
- **Verification:**
  - 256-bit single-use tokens, stored only as SHA-256, valid for 48 hours.
  - Links carry the token in the `#fragment`, so it never reaches server logs, and the page removes it from the
    address bar.
  - The person must press a button, so mail scanners that open links can't confirm.
  - Pages exist for confirmed, already confirmed, expired, invalid, missing, rate-limited and network-error states.
- **Follow-up question** ("how often does CI fail?"): only the person who just signed up or confirmed can answer it.
  An HMAC receipt is required; a duplicate submission gets a decoy that changes nothing.
- **Unsubscribe and deletion:** one link, a hard delete.
- **Owner notification:** once per confirmed signup, idempotent, retried, with stored delivery status. No
  notification is sent for unverified signups.
- **Public counter:** confirmed signups only, hidden below 50, rounded down to tens, updated at most hourly, cached in
  memory and at the CDN, never seeded. Database constraints make anything else impossible to publish.
- **Abuse protection:**
  - a honeypot;
  - a signed form token with a minimum time to submit;
  - per-IP and per-email rate limits (signup 20/h/IP, shown to the person; 5/day/email, silent; confirm,
    follow-up and remove 30/h/IP);
  - rate-limit keys stored only as keyed hashes;
  - optional Turnstile;
  - a disposable-domain flag.
- **Security:**
  - parameterised SQL only;
  - a least-privilege database role in its own schema;
  - transactions, constraints and row locks;
  - `SecretStr` settings;
  - security headers;
  - Origin checks;
  - no API docs exposed;
  - the cron endpoint requires a Bearer secret, checked in constant time;
  - unknown API paths return JSON 404.

## 14. Tests run (locally, 2026-10-21)

| Suite | Command | Result |
|---|---|---|
| Waitlist backend | `PYTHONPATH=. uv run pytest -p tests.netguard tests/waitlist` | 158 passed, 0 external connections |
| Website unit and build | `node --test web/test/` | 18 passed |
| Website end to end | `make web-e2e` (headless Chromium, disposable PostgreSQL, file email) | 24 passed |
| Full repository gate | `make ci` (lint, strict types, docs, truth lock, `make web`, all non-live tests under the network guard, no skips) | 1198 passed |

All the waitlist's network access is in one module, `src/tracewise/waitlist/outbound.py`: Resend and Turnstile,
fixed URLs, no redirects. The repository's existing network-surface test (`tests/unit/test_github_client.py`) now
lists it next to the GitHub client and the model adapter. A new test there pins its two endpoints.

**What the backend tests cover:**

- valid signup and consent;
- invalid emails and malformed or oversized requests;
- unknown fields;
- SQL-injection strings;
- sequential and concurrent duplicates;
- confirmation: success, expiry, invalid, reuse, older link after a resend, and concurrent confirmations (one
  notification);
- unconfirmed signups excluded from the counter, with threshold, rounding, hourly recompute, memo and schema guard;
- owner notification: content, once only, unset inbox, provider failure with the same idempotency key, attempt cap,
  crash recovery, concurrent workers;
- disabled mode never claims a send;
- follow-up authorisation with real and decoy receipts;
- unsubscribe;
- rate limits;
- honeypot, too-fast and forged form tokens;
- cross-origin refusal and allowed-origin CORS;
- cron authorisation;
- database outage (503);
- no tokens or addresses in logs, and no secrets in responses or repr;
- role isolation in both directions, and the migration being idempotent and standalone;
- Resend request shape and error classification (mocked transport);
- file-sender permissions;
- template escaping;
- the admin CLI;
- the deployed app shape (pages, 404, API priority, asset links).

**What the end-to-end test covers:**

- client validation;
- 503 and network-failure messages;
- the loading state;
- double-submit (one request);
- success and the follow-up;
- the email file written;
- confirm: fragment stripped, success, owner notification content, repeat, invalid, missing;
- unsubscribe twice;
- skip link and arrow-key tabs;
- reduced motion;
- no horizontal overflow at 375 px on every page;
- the mobile hero signup;
- **zero console errors, exceptions or CSP violations**.

**Not tested:**

- real Resend delivery or DNS;
- a Vercel deployment, including the Python build, CDN promotion of `app.frontend()`, header application, cron, and
  `.vercelignore` with Git deployments;
- Turnstile against Cloudflare;
- a screen reader;
- automated accessibility (axe) and Lighthouse audits (no npm tooling was added);
- browsers other than Chromium.

## 15. Known limitations and open questions

- **The CI answer can miss the owner notification.** If the CI question is answered *after* confirming (on the
  confirm page), the notification already went out with "not answered yet". The answer is stored and appears in
  `admin export` / `stats`.
- **Rotating `WAITLIST_SECRET`** invalidates "remove me" links in emails already sent, and open follow-up receipts.
  Handle removal requests manually after a rotation.
- **Hobby cron frequency** (reportedly daily) is unverified on official pages. Immediate delivery covers the normal
  case.
- **Resend's test sender** restrictions (sending only to your own address before a domain is verified) are
  unverified. Plan on verifying a domain.
- **Email misconfigured after launch.** Signups close automatically only for a *missing* configuration (mode
  disabled, or no owner inbox). A configured-but-broken setup (for example a revoked Resend key, or an unverified
  domain) still accepts signups; their emails fail, are recorded as `failed`, and are visible with `admin outbox`.
  Run the section 8 check after every change to email settings.
- **Rate limits are per IP.** Shared networks (offices, carrier NAT) share the 20 signups/hour budget. Over it,
  people see "Too many attempts from your network, please try again later" (HTTP 429), so nobody is silently
  dropped. The per-address limit (5/day) is silent on purpose, so it reveals nothing about an address.
- **The privacy notice is a draft** and makes no legal claims beyond describing how the system works. It needs
  review before any pilot.
- **The design docs** (`architecture.md`, `implementation-plan.md`) describe the proposal; their "As built" notes list
  where the implementation differs.
