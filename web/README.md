# web/ — Tracewise pre-launch website and early-access signup

**Status:** implemented and tested locally; **not deployed**. To deploy, follow `docs/deployment.md`: what to set up,
every environment variable, the deploy steps, end-to-end checks, retries, export and deletion, and known limits.

| Path | What |
|---|---|
| `src/` | Pages (`index`, `confirm`, `unsubscribe`, `privacy`, `404`), partials, `css/site.css`, `js/*.mjs` |
| `public/` | Fonts, logo, film (720p, 7.5 MB), poster, captions, copied as-is |
| `build.mjs` | Zero-dependency build → `dist/` (gitignored). Build-time `PUBLIC_*` variables: see `.env.example` |
| `site.py`, `vercel_app.py` | The waitlist API (`src/tracewise/waitlist`) plus the built site as one app; the Vercel entrypoint |
| `dev.py` | Local mode: disposable PostgreSQL, file-based email, the real app on 127.0.0.1 |
| `test/` | `node --test` unit and build tests; `e2e.mjs` headless-Chromium end-to-end test |
| `docs/` | Research, strategy, design system, page plan, architecture and plan (with "as built" notes), **deployment** |
| `design-preview/` | The approved prototype, kept for reference (not deployed) |

## Run it locally

Nothing leaves your machine:

- the database is a throwaway cluster;
- emails are JSON files in `.waitlist-mail/` (open one for the confirmation link);
- only 127.0.0.1 is bound.

```bash
node web/build.mjs && uv run python web/dev.py --port 8000
```

Then open <http://127.0.0.1:8000>. You need PostgreSQL server binaries (`initdb`) on PATH, and Node ≥ 22.

## Checks

```bash
make web
```

```bash
make web-e2e
```

```bash
PYTHONPATH=. uv run pytest -p tests.netguard tests/waitlist
```

`make check` and `make ci` include `make web`; CI also runs `make web-e2e`.
