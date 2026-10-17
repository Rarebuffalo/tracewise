# Competitor Behaviour Verification: The Plumber

Date: 2026-10-17. All references are to [EVIDENCE-LEDGER.md](EVIDENCE-LEDGER.md).

**Bottom line:** we know the **declared integration** well (manifest, GitHub-verified permissions, Marketplace) and **one real output** in detail. Everything about runtime behaviour beyond that single April 2026 report is vendor claim or unknown. **The vendor site has never been reachable to us**, and no live test has been run.

## 1. Status vocabulary

| Status | Meaning |
|---|---|
| **Observed** | Seen directly in public data |
| **Documented** | Vendor statement, or GitHub-rendered listing data |
| **Inferred** | Reasoned from the above |
| **Contradicted** | Prior claim disproved by evidence |
| **Unknown** | No adequate evidence |

## 2. Access attempts (all legitimate, unauthenticated)

| Surface | Result | Evidence |
|---|---|---|
| theplumber.dev (`/`, plus 9 paths probed in S2), api.theplumber.dev (8 paths) | Cloudflare managed challenge only. Not bypassed. | EV-C14 |
| Wayback, archive.today, Common Crawl | No copy found; 4 CC indexes returned 504 | EV-C16 |
| GitHub Marketplace listing, README and Transparency tabs | Accessible | EV-C02–C05 |
| GitHub App manifest, org, demo repo, comments, runs, jobs | Accessible | EV-C01, C06, C09 |
| Demo job logs | 403 to anonymous callers | EV-C17 |
| Public JS bundles or source maps of the product | **None reachable.** Only Cloudflare challenge scripts load. | INVENTORY §2 |

**Conclusion carried forward:** current runtime behaviour remains **unknown** wherever this table shows no access.

## 3. Installation and triggering

| Question | Answer | Status | Evidence |
|---|---|---|---|
| Installation process | Marketplace → "Install it for free" → choose account → all or selected repos | Observed (UI); post-install behaviour unknown | EV-C04, EV-C02 |
| Configuration required | "No config changes" | Documented | EV-C05 |
| Trigger event | `workflow_run` is the only subscribed event | Observed (manifest) | EV-C01 |
| Failure conclusions that trigger analysis | `failure` on a `push` run, **seen once** | Observed (n=1) | EV-C06, EV-C09 |
| Other conclusions (`timed_out`, `cancelled`, `startup_failure`), PR runs, re-runs | — | **Unknown** | — |
| Declared permissions | `actions`, `checks`, `contents`, `metadata` read; `pull_requests` write; plus a GitHub-shown User public-data scope | Observed | EV-C01, EV-C02 |

## 4. Failure analysis (one sample: coffee_shop `b2ef8a12`)

| Question | Answer | Status | Evidence |
|---|---|---|---|
| First meaningful error | Picked the first failing assertion (`assert 0.21 == 2.71`) | Observed (n=1) | EV-C07 |
| Groups sibling failures | "…and 3 other test failures"; there are exactly 4 failing tests | Observed (n=1) | EV-C07, EV-C08 |
| Inspects code at the commit | Quotes `pricing.py:41`, which is not in any log | Observed: code was read. Mechanism (clone vs API) is Documented (clone) / Unknown. | EV-C08, EV-C05 |
| Root cause, file, line, snippet, explanation, fix | All present and **correct** | Observed (n=1) | EV-C07, EV-C08 |
| Confidence | "High", no basis given | Observed (n=1) | EV-C07 |
| Files examined | Listed with ranges. Ranges and paths are not repo-true (`coffee_shop/coffee_shop/…`, `1-200` on a 30-line file). | Observed (n=1) | EV-C12 |
| Agent-oriented block | "For AI Agents": edit steps + `pytest tests/test_pricing.py` | Observed (n=1) | EV-C07 |
| Distinguishes the triggering commit from the introducing commit | **Not in this report.** The trigger was README-only; the defect came from `3019c977`. | Observed absence (n=1, April 2026) | EV-C11 |
| "Agentic" tool loop | The vendor says so. The artifacts are compatible with either a tool loop or a single prompt. | Documented / Inferred (weak) | EV-C05, EV-C12 |
| Handles re-runs, flaky, multiple failures, dependency, infra, inconclusive | — | **Unknown** | EV-C18 |
| "Fixed 200-line read window" (prior research) | — | **Contradicted** | EV-X02 |

**Not supported by the evidence:**

- Any statement about The Plumber's accuracy beyond this one case.
- That it "cannot" attribute today. EV-C11 is one observation from April 2026.

## 5. Publishing and lifecycle

| Question | Answer | Status | Evidence |
|---|---|---|---|
| Destinations observed | A new commit comment on the trigger SHA | Observed (n=1) | EV-C06 |
| PR comments | Advertised ("Commit & PR comments"); none found publicly | Documented / not observed | EV-C04, EV-C13 |
| Check Runs | Impossible with declared permissions (Checks read only) | Platform-documented + Observed manifest | EV-C01, EV-P09 |
| Duplicated vs updated on re-runs | The commit comment *cannot* be edited with its permissions, so any re-analysis would add a new comment. Whether it re-analyses at all: unknown. | Inferred constraint / Unknown behaviour | EV-P09 |
| Asynchronous execution | 6 m 14 s after completion, far beyond the 10 s webhook response window | Inferred (strong), n=1 | EV-C10, EV-P05 |
| Latency claim | "Under two minutes" | Documented; not corroborated (n=1 shows 6 m 14 s) | EV-C05, EV-C10 |
| Data retention and deletion | "No user code or CI log data is stored after analysis completes"; environment destroyed after each report | Documented (self-attested) | EV-C03 |
| Insufficient permissions or cancelled runs | — | Unknown | — |
| LLM use | "AI inference provider (LLM API)"; model not named | Documented (self-attested) | EV-C03 |

## 6. Public technical artifacts and backend

| Artifact | Establishes | Does **not** establish |
|---|---|---|
| App manifest and Transparency | Permissions, events, publisher 2FA, self-attested third-party LLM, private source repo | Which permissions are used; LLM vendor or model |
| DNS and CT | A Cloudflare-fronted apex and an `api.` host | Origin hosting, framework, language, DB, queue, deployment |
| Bot comment | Output schema and quality on one case | Pipeline internals |

**Backend language, framework, database, queue, model, orchestration and deployment: Unknown. Not asserted.**

## 7. Summary by status

| Status | Items |
|---|---|
| **Observed** | Manifest; GitHub-verified permissions; Marketplace plan and installs; one commit-comment report (format, correctness, artifacts, no attribution, 6m14s); vendor site blocked; demo logs not public |
| **Documented** | Clone; agentic analysis; PR comments; under 2 minutes; no storage and environment destroyed; third-party LLM API; private repo; no config |
| **Inferred** | Asynchronous processing (strong); tool loop (weak) |
| **Contradicted** | Fixed 200-line window (EV-X02); commit comments need write (EV-X03); logs expired 410 (EV-X01, withdrawn) |
| **Unknown** | Every runtime behaviour except the one report; stack; current behaviour since April 2026 |
