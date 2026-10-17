# Provenance and Quarantine Record for `research/final-audit/`

Written: 2026-10-17 by a Claude Code session in `~/tracewise`.

**Nothing in this directory was deleted, moved or edited.** This file is the only addition. It marks which artifacts are **excluded** from the competitor findings and why.

## 1. What happened

The earlier audit session (transcript `~/.claude/projects/-home-Krishna-Singh-rea/96711343-….jsonl`, opened in `~/rea`) used the GitHub CLI. It was logged in as an account the user had **not** intended for this project.

| Fact | Evidence (local transcript, no new requests) |
|---|---|
| Account | `gh auth status` at **2026-10-16T20:43:47Z** printed: "Logged in to github.com account **ksingh-rovn** (keyring) — Active account: true" |
| Window of authenticated use | First `gh api` call 2026-10-16T20:43:56Z; last 2026-10-16T21:36:21Z. Logged out at **2026-10-17T14:48:43Z** ("Logged out of github.com account ksingh-rovn"). |
| Which calls used the account | Every `gh api …` invocation in the main session and in subagent `agent-abdf49dc…` ("Mine real CI failure ground truth"). `gh` sends the active account's token. Two endpoint types used only work authenticated (`search/code`, GraphQL), which confirms auth was in use. |
| Calls that did **not** use the account | `curl` without auth headers (Marketplace HTML, GitHub docs, crt.sh, DNS-over-HTTPS, site-path probes, PyPI JSON) and REA CLI browser captures |
| Credential handling during logout (2026-10-17 14:46–14:48Z) | Read `~/.config/gh/hosts.yml` with the token value redacted by `sed`; listed keyring entry labels via `secret-tool search`; grepped `~/.config`, `~/.ssh` and `~/.gitconfig` for the account name. No token value appears in the transcript output we inspected (our extraction also redacted token patterns). |

## 2. Repositories touched with the account

All of them are **public**. On 2026-10-17 we checked every one with an unauthenticated `GET https://github.com/<owner>/<repo>`: 200 means public, 404 means private or absent.

| Group | Repositories | Visibility check |
|---|---|---|
| Competitor | `theplumber-dev/coffee_shop`, `andrewcampi/coffee_shop` (upstream of the demo); App `the-plumber-app`; user `theplumber-dev`; Marketplace listing via GraphQL | 200 public |
| Benchmark (third-party OSS) | fastapi/typer, honojs/hono, pallets/flask, pallets/werkzeug, pallets/click, encode/starlette (→ Kludex/starlette), tox-dev/tox, python-poetry/poetry, jazzband/pip-tools (→ pypa/pip-tools), pypa/pip-tools, psycopg/psycopg, python-attrs/attrs, torchgeo/torchgeo, python/mypy, Textualize/textual, pydantic/pydantic-ai, pydantic/pydantic-settings, encode/httpx, pypa/hatch, pytest-dev/pytest-xdist, colinhacks/zod, trpc/trpc, vitest-dev/vitest, psf/black, aio-libs/aiohttp, redis/redis-py, celery/celery | 26 × 200, 2 × 301 (renamed → 200) |
| Global search results returned to the account | 73 repos listed in `search-result-repos` (e.g. results for `"Plumbing Report" in:comments`, `the-plumber-app`, a Dependabot query constrained with `is:public`). Code search returned **0** for `the-plumber-app` and `theplumber.dev`. | 73 × 200, 1 × 301 → 200. **No private repository appeared in any result.** |

- **Private repositories inspected:** **none found.**
- **Account-owned or organization repositories of `ksingh-rovn`:** none appear in any command or result.

Limitations:

- "Public today" does not prove "public on 2026-10-16". For the competitor items, §4 below shows that the same data is publicly retrievable now.
- We did not query what the account itself can see, by design.

## 3. Per-artifact classification

| Artifact (in `evidence/`) | How obtained | Class | Status in the 2026-10-17 audit |
|---|---|---|---|
| `app-manifest.json`, `org.json`, `org-repos.json`, `repo.json`, `commit-comments.json`, `commits.json`, `runs.json`, `run-jobs.json`, `pulls.json`, `issues.json`, `forks.json`, `upstream-runs.json`, `upstream-commits.json`, `commit-3019c977.json` | `gh api` (ksingh-rovn) | **Authenticated access to public competitor data** | **EXCLUDED.** Superseded by unauthenticated copies in `../final-audit-public/evidence/` (identical content, §4). |
| `plumbing-report-b2ef8a12.md` | Derived from `commit-comments.json` (authenticated) | Authenticated origin | **EXCLUDED.** The public copy is identical. |
| `demo-src/*` | `gh api …/contents` (authenticated) | Authenticated origin | **EXCLUDED.** Public `raw.githubusercontent.com` copies are byte-identical. |
| `run-logs.zip`, `run-logs.err` | `gh api …/runs/24405466283/logs` (authenticated) | Authenticated | **EXCLUDED.** It contains **no log**: a 141-byte JSON error body, HTTP 410. Publicly the same endpoint returns 403 (auth required), so "logs expired" is **not publicly verifiable**. It is downgraded to INFERRED (90-day default retention, GitHub docs). |
| `marketplace-graphql.json`, `marketplace-plans.json` | GraphQL (authentication required by GitHub) | Authenticated | **EXCLUDED.** The same listing text and plan are in the public Marketplace HTML. |
| `marketplace.html` | `curl`, unauthenticated | Public | Retained. A fresh public copy is also in `final-audit-public`. |
| `gh-perms.md`, `gh-webhooks.md` | `curl` of GitHub docs, unauthenticated | Public (platform docs) | Retained |
| `dns.txt`, `crtsh.json`, `site-paths.txt` | DNS-over-HTTPS, crt.sh, curl; unauthenticated | Public | Retained |
| `rea/*` | REA CLI `capture-browser-scenario`, no credentials | Public | Retained |
| `fetched_at.txt` | Local timestamp | n/a | Retained (it timestamps the authenticated batch) |
| `benchmark/case-*-job-*.log` (15 logs) | `gh api …/jobs/{id}/logs` (authenticated). Public job logs require authentication (unauthenticated download returns 403). | **Authenticated access to public third-party CI logs** | **EXCLUDED** from all findings. Not competitor evidence. |
| `benchmark/case-*.json`, `benchmark/INDEX.md` | Subagent synthesis of the authenticated logs and API data plus unauthenticated PyPI JSON | Mixed; authenticated origin | **EXCLUDED** as ground truth. Treat as *candidate* cases only, to be re-validated with an approved credential or a project-scoped token. |
| Search-result listings (transcript only) | Authenticated `search/issues`, `search/code`, `search/commits` | Authenticated | **EXCLUDED.** The four bot-comment searches were re-run unauthenticated: all **0** (§4). Code and commit search (authentication-only) is not reproduced. |

**Our own test repositories:** none exist. No App was installed, no repository was created, and no CI run was triggered by any session.

**Uncertain origin:** none. Every file above maps to a logged command.

## 4. Independent public re-verification (2026-10-17, no authentication)

Location: `research/final-audit-public/evidence/` (see its `FETCH-LOG.tsv`).

| Competitor fact | Public result | Matches quarantined copy |
|---|---|---|
| App permissions, events and `updated_at` | `actions/checks/contents/metadata` read, `pull_requests` write; `workflow_run`; updated 2026-04-15T22:57:14Z | Same |
| Org created; 1 public repo; demo is a fork of `andrewcampi/coffee_shop` | Same | Same |
| One commit comment by `the-plumber-app[bot]` on `b2ef8a12`, 2026-04-14T14:49:20Z, 2,218 chars, not line-anchored, never edited | Same; **body byte-identical** | Same |
| Commits, run 24405466283 (push, failure, updated 14:43:06Z), job "Tests (Python 3.11)" (completed 14:43:01Z) | Same | Same |
| `b2ef8a12` changes only `README.md` (+3); `3019c977` added `pricing.py` and the tests; upstream failed on `3019c977` and `585de1d2` | Same | Same |
| PRs, issues, forks of the demo = 0; upstream commit comments = 0 | Same | Same |
| Bot-comment searches (`commenter:app/…`, `author:app/…`, `involves:app/…`, `commenter:the-plumber-app[bot]`) | **0** each (unauthenticated search API) | Same |
| Source files at `b2ef8a12` (`pricing.py` 43 lines, `order.py` 30 lines, tests, workflow) | Retrieved from `raw.githubusercontent.com` | Byte-identical |
| Marketplace: 4 installs, Free $0, 10 analyses/month, public repos, "Commit & PR comments", "under two minutes", "never stored" | Public HTML | Same |
| Demo run logs | **403** unauthenticated, so they cannot be checked publicly | Authenticated 410 excluded |

## 5. Effect on conclusions

- **Competitor (The Plumber) conclusions: still supported.**
  - Every competitor finding in `FINAL-REVERSE-ENGINEERING-AUDIT.md` §4 (F1–F18, F20–F22) is reproduced from unauthenticated public sources.
  - F19 ("logs expired, HTTP 410") is **no longer supported by admissible evidence**. It is downgraded to INFERRED.
  - Code and commit search results are dropped.
- **Benchmark ground truth (§7.2, cases R-01…R-15): not admissible** in its current form. It rests on authenticated log downloads. The *case list* may be reused as candidates, but each case's ground truth must be re-established with an approved credential, or replaced by synthetic cases in our own test org.
- **Spec and acceptance-test items that cite R-cases** (e.g. AT-DX-07, AT-ATR-05/07/08/09, AT-DX-16) must be re-sourced before use as gates.
