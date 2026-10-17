# Investigation Plan and Tool Inventory

Date: 2026-10-17 (UTC 17:23–18:00). Session: Claude Code opened in `~/tracewise`.

Credentials:

- `gh`: not logged in.
- `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`: none set. Only presence was checked; no values were printed.
- Every network request in this review was public and unauthenticated (see `evidence/FETCH-LOG.tsv`).

## 1. Starting state (read-only inventory)

### 1.1 Research documents found

All requested files exist except one. `PROVENANCE-QUARANTINE.md` is **not** in `research/final-audit-public/`; it is at `research/final-audit/PROVENANCE-QUARANTINE.md`.

| Group | Files (path relative to `research/`) | Modified (local) | Status |
|---|---|---|---|
| S1 original research (2026-10-15) | `01`–`08`, `EXECUTIVE-SUMMARY.md` | 10-15 16:41–16:49 | Unchanged (SHA-256 verified against S1 hashes) |
| S1 plan set (2026-10-15) | `IMPLEMENTATION-PLAN.md`, `IMPLEMENTATION-TASKS.md`, `ARCHITECTURE-DECISIONS.md`, `DECISION-REGISTER.md`, `RESOURCE-AND-SETUP-CHECKLIST.md`, `TEST-AND-RELEASE-PLAN.md`, `OPEN-QUESTIONS.md`, `PLAN-REVIEW.md` | 10-15 18:16–18:30 | Unchanged |
| S2 audit (2026-10-17, unintended authenticated session) | `FINAL-REVERSE-ENGINEERING-AUDIT.md`, `VERIFIED-FEATURE-SPEC.md`, `TRACEWISE-PARITY-ACCEPTANCE-TESTS.md`; `final-audit/evidence/**` | 10-17 02:14–03:07 | Unchanged; evidence partly quarantined |
| S3 public audit (2026-10-17) | `final-audit-public/{FINAL-REVERSE-ENGINEERING-AUDIT,VERIFIED-FEATURE-SPEC,TRACEWISE-PARITY-ACCEPTANCE-TESTS}.md`; `final-audit-public/evidence/**`, `provenance/**`; `final-audit/PROVENANCE-QUARANTINE.md` | 10-17 22:08–22:16 | Unchanged |

**Conflicting versions:** the audit, the spec and the acceptance tests each exist twice (S2 and S3). The S3 versions supersede S2 where they differ. They are the baseline for this review.

**Baseline hashes:** recorded before any work (24 files) in the session scratchpad. They were re-checked at the end (REPRODUCIBILITY §5).

### 1.2 Evidence and artifacts found

| Location | Content | Admissibility |
|---|---|---|
| `final-audit-public/evidence/` | Unauthenticated competitor artifacts (app manifest, org, demo repo, bot comment, commits, runs, jobs, upstream, raw source, Marketplace HTML and embedded listing JSON, 4 search results, Common Crawl results), plus the REA ledger export (3 records) | **Admissible** (public, logged) |
| `final-audit/evidence/{marketplace.html,gh-perms.md,gh-webhooks.md,dns.txt,crtsh.json,site-paths.txt,rea/*}` | S2 artifacts obtained without credentials | Admissible (provenance traced in the quarantine record) |
| `final-audit/evidence/{app-manifest,org,…,commit-3019c977}.json`, `demo-src/`, `plumbing-report-…md`, `marketplace-graphql.json`, `marketplace-plans.json`, `run-logs.*` | Obtained with the unintended `gh` account | **Quarantined.** Not used. Public duplicates exist for all but GraphQL and logs. |
| `final-audit/evidence/benchmark/**` (15 logs, 15 case JSONs, INDEX) | Authenticated log downloads | **Quarantined.** Run IDs are used only as *pointers*; nothing from their content is used. |
| S1 tool-results (2 REA captures, 2 screenshots) | `~/.claude/projects/-home-Krishna-Singh-tracewise/737af3f8…/tool-results/` | Admissible (public) but superseded by S3 captures |
| Prior transcripts | S1 (this session) and S2 (`~/.claude/projects/-home-Krishna-Singh-rea/96711343…`) | Inspected **only** for provenance in S3 (redacted extraction in `final-audit-public/provenance/`). Not re-read for content here. |

### 1.3 Benchmark artifacts found

| Set | Source | State |
|---|---|---|
| B-01…B-16 | `04-failure-benchmark.md`; amendments in `TEST-AND-RELEASE-PLAN.md` §2 | Designed; never built; no results |
| B-17 | S3 tests §6 | Designed; never built |
| R-01…R-15 | S2 `final-audit/evidence/benchmark/` | Quarantined (authenticated) |
| coffee_shop public demo | Public | One real competitor output (n=1) |

## 2. REA / MCP capability matrix

The REA MCP server `rea-agents` 6.5.0 is live in this session. `get_evidence_bundle` returned 3 retained records, all S3 captures from today. Native-binary providers (Ghidra, Hopper, IDA, JADX, WABT, TShark and others) were reported unavailable or unconfigured by `binary_session` on 2026-10-15. They are irrelevant: no shipped binary exists.

| Capability | Available? | Appropriate for this question? | Used? | Result or limitation |
|---|---|---|---|---|
| `capture_browser_scenario` (Playwright Chromium 154) | Yes | Yes: vendor site and Marketplace UI | **Yes ×3 (S3, today)** | theplumber.dev: Cloudflare challenge (`ev_069567c3…`). Marketplace Transparency tab captured with expand clicks (`ev_cd63f2df…`, `ev_ee40b4dc…`). Not repeated in this review: no new first-party surface became reachable. |
| `inspect_web_page` / `observe_web_session` / `list_browser_targets` (passive CDP) | Yes (needs a CDP endpoint) | No | No | No reachable first-party page |
| `analyze_web_bundle`, `export_web_scripts`, `trace_web_module_imports`, source maps | Yes | No | No | Only Cloudflare challenge scripts load; analysing them says nothing about The Plumber |
| `analyze_javascript_application` / `trace_application_feature` | Yes | No | No | No first-party bundle or app artifact exists |
| `inspect_web_network_capture` (HAR / SAZ / qlog) | Yes | No | No | No first-party traffic recorded; a HAR of the challenge page adds nothing |
| `inspect_pcap_capture` | Yes (tshark present) | No | No | No relevant capture |
| `get_evidence_bundle` / `export_evidence_bundle` | Yes | Yes (ledger) | **Yes** (summary today; export in S3) | 3 records; export at `final-audit-public/evidence/rea-evidence-bundle-2026-10-17.json` |
| `record_unknown` / `list_unknowns` | Yes | Marginal | No | Unknowns are tracked in EVIDENCE-LEDGER.md instead, so they stay readable without REA |
| Native, Android, firmware, managed (.NET), WASM, EVM tools | Partly | No | No | No artifact of these types exists |
| **Non-REA:** unauthenticated `curl` to the GitHub REST API | Yes (60 req/h) | Yes: public CI metadata and platform behaviour | **Yes, 12 calls** | §4 |
| **Non-REA:** GitHub Docs article API (raw markdown) | Yes | Yes: official platform claims | **Yes, 26 pages** | `evidence/docs/` |
| **Non-REA:** WebFetch / WebSearch | Yes | Supporting only | Not in this review (used in S3) | — |
| In-app browser with a human passing Turnstile | Yes | Yes, for vendor pages | **No** | Needs the user personally; out of scope by instruction |
| Authenticated GitHub API, App install, test org | — | — | **No** | Forbidden in this investigation |

**What REA did *not* verify:** REA captured pages. It did not analyse or verify any backend behaviour. The Transparency content is GitHub-rendered:

- the Publisher and Permissions sections are verified by GitHub;
- the Security & Compliance section is self-attested by the vendor, as GitHub states on the page.

## 3. Investigation matrix (question → method)

| # | Question | Best available method | Second method (corroboration) | Outcome document |
|---|---|---|---|---|
| Q1 | Has the vendor surface changed or become reachable? | REA capture (S3, today) | curl status (S3) | COMPETITOR §2 |
| Q2 | Install, trigger and permissions | App manifest (public REST) | GitHub-verified Transparency permissions (REA) | COMPETITOR §3 |
| Q3 | Analysis behaviour and report content | The public bot comment + source at SHA | Arithmetic re-computation; vendor README | COMPETITOR §4 |
| Q4 | Publishing surfaces and lifecycle | Public comments API + GitHub permission table | Marketplace claims | COMPETITOR §5 |
| Q5 | Backend and stack | Marketplace self-attestation; DNS/CT | — (no first-party artifact) | COMPETITOR §6 |
| Q6 | `workflow_run` semantics, conclusions, SHAs | Official docs (raw) | Public run metadata (pallets/flask) | PLATFORM |
| Q7 | Permissions per Tracewise operation | Official permissions table | Endpoint pages | PLATFORM §3 |
| Q8 | Output limits (comments, Check Runs) | Official docs | — (only community reports) | PLATFORM §5 |
| Q9 | Delivery, retry, signature, ordering | Official webhook docs | — | PLATFORM §2 |
| Q10 | Forks and PR association | Official docs | Public metadata test (20 PR runs, 2 commit→PR lookups) | PLATFORM §6 |
| Q11 | What public metadata supports as ground truth | Public lane history + jobs + commit diff | Annotation and log access test | BENCHMARK §3 |
| Q12 | Plan inconsistencies | Grep of plan files with line numbers | Cross-file comparison | CORRECTION MATRIX |

## 4. Network activity in this review

All requests are listed in `evidence/FETCH-LOG.tsv`:

- 26 GitHub Docs article fetches, all 200;
- 12 unauthenticated `api.github.com` calls (11 × 200, 1 × 403 for job logs);
- the unauthenticated rate limit went from 59 to 47 remaining.

No vendor endpoint was contacted in this review. No data was sent to third parties beyond these GET requests.
