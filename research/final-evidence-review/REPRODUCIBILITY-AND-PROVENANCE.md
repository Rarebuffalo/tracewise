# Reproducibility and Provenance

Date: 2026-10-17. Collection window for this review: 17:23–17:55 UTC.

## 1. Artifact locations

| Path (under `research/final-evidence-review/`) | Content | Origin |
|---|---|---|
| `evidence/FETCH-LOG.tsv` | Every request in this review: time, HTTP code, bytes, URL, saved file (38 rows: 26 docs + 12 API) | This review |
| `evidence/docs/*.md` (26 files) | Official GitHub Docs as raw markdown via `https://docs.github.com/api/article/body?pathname=…` | Public |
| `evidence/docs-claim-grep.tsv` | Line-referenced matches for each platform claim pattern | Derived (`evidence/grep_docs.py`) |
| `evidence/permission-rows.txt` | Permission-table rows for every Tracewise endpoint, with line numbers | Derived |
| `evidence/public-ci/*.json`, `*.txt` | Anonymous GitHub REST responses (pallets/flask) | Public, unauthenticated |
| `evidence/grep_docs.py` | Claim-pattern grep script | This review |

**Reused from earlier public work (unchanged, admissible):**

- `research/final-audit-public/evidence/**`: S3 public re-fetch of competitor artifacts and the REA ledger export (`rea-evidence-bundle-2026-10-17.json`: 3 records `ev_069567c3…`, `ev_cd63f2df…`, `ev_ee40b4dc…`).
- `research/final-audit/evidence/{marketplace.html,gh-perms.md,gh-webhooks.md,dns.txt,crtsh.json,site-paths.txt,rea/*}`: S2 artifacts obtained without credentials.

**Quarantined (never used for conclusions):**

- `research/final-audit/evidence/` authenticated artifacts and `benchmark/**`;
- see `research/final-audit/PROVENANCE-QUARANTINE.md`.

## 2. Tool usage that affects conclusions

| Tool | Question | Target | Public / unauth | Result | Artifact |
|---|---|---|---|---|---|
| REA `capture_browser_scenario` (S3) | Is the vendor site reachable? | `https://theplumber.dev/` | Yes | Cloudflare challenge | `ev_069567c3…` |
| REA `capture_browser_scenario` ×2 (S3) | What does Marketplace Transparency declare? | `github.com/marketplace/the-plumber-app?tab=transparency` | Yes | Publisher, permissions (GitHub-verified), self-attested security | `ev_cd63f2df…`, `ev_ee40b4dc…` |
| REA `get_evidence_bundle` (this review) | Ledger state | REA session | Local | 3 records | — |
| curl, GitHub Docs | Platform semantics | 26 pages | Yes | See PLATFORM doc | `evidence/docs/` |
| curl, GitHub REST (anonymous) | PR association; `head_sha`; annotations and log access; lane metadata | pallets/flask | Yes | EV-P13, P22–P26 | `evidence/public-ci/` |

## 3. How to reproduce without credentials

Prerequisites:

- `curl`, `python3`;
- no `GH_TOKEN` or `GITHUB_TOKEN` in the environment;
- do **not** use `gh`.

```bash
# 1. Official docs (raw markdown)
curl -sL "https://docs.github.com/api/article/body?pathname=/en/webhooks/webhook-events-and-payloads" -o webhook-events.md
grep -n "capped at 25 MB\|regardless of whether the workflow" webhook-events.md
```

```bash
# 2. Permission rows
curl -sL "https://docs.github.com/api/article/body?pathname=/en/rest/authentication/permissions-required-for-github-apps" -o perms.md
grep -n "commits/{commit_sha}/comments\|/check-runs\`\|issues/{issue_number}/comments\|actions/jobs/{job_id}/logs" perms.md
```

```bash
# 3. Competitor manifest and the single report (anonymous REST)
curl -s https://api.github.com/apps/the-plumber-app
curl -s "https://api.github.com/repos/theplumber-dev/coffee_shop/comments?per_page=100"
curl -s https://api.github.com/repos/theplumber-dev/coffee_shop/commits/b2ef8a1204cd1a370b27bca762c38c4b6c64be42
```

```bash
# 4. PR association and pull_requests emptiness
curl -s "https://api.github.com/repos/pallets/flask/actions/runs?event=pull_request&per_page=20"
curl -s https://api.github.com/repos/pallets/flask/commits/7689f98403/pulls
curl -s https://api.github.com/repos/pallets/flask/commits/afe8961b7c/pulls
```

```bash
# 5. Logs require auth even for public repos (expect 403)
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/pallets/flask/actions/jobs/103643345400/logs
```

```bash
# 6. Public lane metadata
curl -s "https://api.github.com/repos/pallets/flask/actions/workflows/1367898/runs?branch=main&event=push&per_page=40"
curl -s "https://api.github.com/repos/pallets/flask/actions/runs/34252544596/jobs?per_page=100"
```

Notes:

- The anonymous limit is 60 requests per hour.
- Results may drift as repositories change: new runs, retention expiry after 90 days (EV-P14).
- The saved files are the snapshot of record.

## 4. Collection dates

| Evidence | Date |
|---|---|
| Docs and public-ci (this review) | 2026-10-17 17:24–17:55Z |
| S3 competitor re-fetch | 2026-10-17 ≈16:15–16:45Z (`final-audit-public/evidence/FETCH-LOG.tsv`) |
| S3 REA captures | 2026-10-17 |
| S2 admissible public artifacts | 2026-10-16 ≈20:46–20:49Z |
| S1 observations | 2026-10-15 (`08-sources-and-confidence.md`) |

## 5. Integrity checks performed at the end of this review

See FINAL-DECISION-REPORT §6 for the results.

1. SHA-256 of all 24 pre-existing markdown files (baseline taken at 17:23Z) compared after writing the deliverables.
2. Token-pattern scan of `research/final-evidence-review/` (`gh[pousr]_…`, `github_pat_…`, `Authorization:`).
3. Scan of deliverables for references into quarantined paths outside the admissible list.
4. Every relative path cited in the deliverables checked for existence.
