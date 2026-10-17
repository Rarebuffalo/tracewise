# Decision Register — reconciliation of the nine research documents

Date: 2026-10-15. Inputs: `EXECUTIVE-SUMMARY.md` and documents `01`–`08`. All nine were present and unmodified, and were read in full.

This register is the bridge from the research to [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md). Accepted and modified decisions are carried forward. Rejected and deferred items are **not** carried into the build.

**Evidence classes**

| Class | Meaning |
|---|---|
| OBS | Directly observed by us |
| DOC | Vendor or platform documented |
| IND | Independent research |
| INF | Inferred |
| UNT | Untested hypothesis |
| NEW-V | Newly verified on 2026-10-15 from official docs (see §Verification log) |

**Decisions:** Accept / Modify / Defer / Reject.

## A. Product direction and differentiation

| ID | Recommendation | Source | Evidence | Conf. | Dependencies / assumptions | Implications | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| DR-01 | Overall verdict: **VALIDATE FIRST**; don't build "explain + fix + verify" | ExecSum, 05 §1 | DOC (GitHub Fix with Copilot, verified), OBS (competitor installs) | High that the original idea is commoditized; low on WTP | — | No production code until the Phase 0 gate passes | **Accept** | Nothing since has changed the evidence |
| DR-02 | Position as **attribution, not autofix**; hand code fixes to Copilot or Cursor | 05 §5 | INF from DOC | Medium | Copilot Fix remains manual; attribution remains unbundled | No `contents:write`; no patch generation | **Accept** | Smallest product that avoids competing with GitHub's own agent |
| DR-03 | Segment: 5–30 engineers, GitHub Actions, Python/TS, shared trunk | 05, 07 | IND (CircleCI size-band data), INF | Low-medium | Pain concentrated at this size | Parser scope limited to Python and TS | **Accept as a hypothesis** | Must be confirmed in interviews (gate G-1) |
| DR-04 | Differentiator D: first-bad-change attribution | 05 §3D | OBS n=1 (The Plumber demo missed it); bounded search | Low-medium | CI Doctor (preview) correlates the *triggering* commit; Harness offers change-impact analysis on Harness CI only | Central algorithm (Plan §7) | **Modify** | Treat as **unproven**. Gate G-5 tests it against Copilot Explain error, Fix with Copilot and CI Doctor before claiming a gap. |
| DR-05 | Differentiator B: dependency drift via resolved versions plus registry timestamps | 05 §3B | INF, UNT | Low-medium | Logs contain resolved versions (true for pip "Successfully installed" and uv; **not** for `npm ci`) | Python-first; npm only via lockfile diffs | **Modify** | Registry timestamps are *context*, never proof (Plan §7.5). Registry lookups are deferred to the pilot. |
| DR-06 | Evidence-checked claims plus abstention (C+H) | 05 §3C/H | IND (trust surveys) | Medium as a design property | — | Evidence validator is a hard gate before publishing | **Accept** as a design property, not the pitch | Customers rarely pay for "honesty" directly |
| DR-07 | Cross-tenant upstream-breakage network effect | 05 §5 | Speculative | Low | Needs scale | Schema keeps package/version per failure | **Defer** | Not testable with fewer than 10 customers |
| DR-08 | Exclude backend fix verification (E) and self-host (G) | 05 §3E/G | INF | Medium | — | No sandbox or execution in the MVP | **Accept** | Cost and risk too high; demand evidence weak |

## B. GitHub integration and permissions

| ID | Recommendation | Source | Evidence | Conf. | Assumptions | Implications | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| DR-09 | Permissions `actions:r`, `checks:w`, `contents:r`, `metadata:r`, `pull_requests:w` | 06 §4, 02 B.6 | NEW-V (GitHub permission tables) | High | — | — | **Modify** to `actions:r`, `checks:w`, `contents:r`, `metadata:r`. **Drop `pull_requests:w`.** | Check Runs appear on PRs whose head is that SHA. A PR comment adds noise (Community #169148) and a write scope. See Plan §4.4.3. |
| DR-10 | Product described as "read-only" | 06, 02 | — | — | — | Messaging | **Modify** | Precise claim: *"cannot modify your code, workflows, issues or PRs; writes only its own Check Run."* |
| DR-11 | Logs-only mode without `contents` | 02 B.6, 06 §4 | INF | — | — | Without it: no compare, so no first-bad-change attribution | **Defer** | Offer only if a design partner refuses `contents:read` (OQ-01) |
| DR-12 | Webhook stage "no retry (GitHub redelivers)" | 02 B.2 | **Contradicted by NEW-V**: "GitHub does not automatically redeliver failed webhook deliveries" | High | — | Lost events if we are down | **Reject** → add a delivery reconciliation job (Plan §4.4.9) | Verified fact |
| DR-13 | Installation backfill of the last 50 runs on install | 06 §4 | INF | — | — | Extra API load and storage | **Reject** | History is fetched **on demand** per analysis (runs API plus logs retained 90 days by default, NEW-V) |
| DR-14 | Subscribe to `check_run.rerequested` for re-analysis | 06 §4 | NEW-V (`rerequested` requires checks write; event needs subscription) | High | — | — | **Defer** | Not needed to prove attribution |
| DR-15 | PR-comment upsert, "comment modes" | 06 §1/§3 | — | — | — | — | **Reject for MVP** | Same as DR-09 |
| DR-16 | Check Run conclusion | (new) | NEW-V: `neutral` is allowed | High | — | Must not block merges via branch protection | **Accept (new):** always `neutral` | Our check is information, not a gate |

## C. Architecture and infrastructure

| ID | Recommendation | Source | Evidence | Conf. | Assumptions | Implications | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| DR-17 | FastAPI API plus async worker | 06 §1 | — | High | — | — | **Accept** | Team skill fit; webhooks must return 2xx within 10 s (NEW-V) |
| DR-18 | `arq` + Redis queue | 06 §1 | — | — | — | Extra service; dual-write gap between DB and queue | **Reject** → Postgres job table (`FOR UPDATE SKIP LOCKED`), enqueued **in the same transaction** as the delivery row | Removes the crash-between-commit-and-publish failure mode, and Redis entirely (ADR-03) |
| DR-19 | Object storage (R2) for raw logs, 7-day TTL | 02 B.2, 06 | — | — | — | Retains customer logs | **Reject** | Raw logs stay in worker memory only; we persist only redacted ≤2 KB excerpts |
| DR-20 | Next.js dashboard plus GitHub OAuth | 06 §1/§3/§13 | — | — | — | About 4–5 dev-days | **Defer** | The Check Run *is* the UI. Admin work is done by CLI. |
| DR-21 | Slack main-branch alerts | 06 | — | — | — | — | **Defer** | Not needed to prove attribution. Revisit if partners ask. |
| DR-22 | Paddle/Stripe billing integration | 06, 07 | — | — | — | — | **Defer** | Manual invoice for the first pilots |
| DR-23 | Postgres RLS on all tenant tables | 02 B.4, 06 §2 | — | Medium | Pooling must not leak the tenant | — | **Modify** | Tenant = GitHub installation. Use `set_config(..., true)` (transaction-local), a non-owner app role and `FORCE RLS`. Required before the **external** pilot, not the internal MVP (ADR-05). |
| DR-24 | Hosting: Fly/Render/Railway plus Neon/Supabase plus Upstash plus Vercel plus R2 | 06 §10 | NEW-V (Fly, Neon prices) | Medium | — | — | **Modify** → Fly.io (one image, web and worker process groups) plus Neon Postgres | Fewest vendors. No Redis, Vercel or R2 needed. |
| DR-25 | Sentry plus OpenTelemetry → Grafana Cloud | 06 §10 | NEW-V (Sentry free: 5k errors, 1 user) | — | — | — | **Modify** | Sentry free plus JSON logs with correlation IDs. OTel deferred. |
| DR-26 | Concurrency of 1 job per (repo, branch) | 06 §5 | — | Medium | — | — | **Accept** | Implemented with a Postgres advisory lock |

## D. Attribution and AI pipeline

| ID | Recommendation | Source | Evidence | Conf. | Assumptions | Implications | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| DR-27 | Deterministic rules first, then ≤2 bounded LLM calls | 02 B.5, 06 §6 | INF | Medium | — | — | **Modify** | The internal MVP is **deterministic only**. The LLM is added later only (a) to summarize and (b) to choose among *existing* candidates by evidence ID. It can never introduce a new suspect. It is gated on an eval (ADR-08). |
| DR-28 | Default model Sonnet 5.5, escalate to Opus 5.5 | ExecSum, 06 | NEW-V pricing | — | — | Cost | **Modify** | Evaluate Haiku 5.5 and Sonnet 5.5 against the labeled set. Pick the cheapest that meets the gates. Opus only if measured to help. |
| DR-29 | Numeric calibrated confidence (0.82) | 02 B.5 | — | Low | Needs labeled data | — | **Modify** | Bands only (`supported` / `possible` / `insufficient`), defined by rule conditions. No numeric scores until ≥200 labeled outcomes. |
| DR-30 | `suggested_remediation.patch_unified_diff` | 02 B.4 | — | — | — | — | **Reject** | Attribution product: "next action" text only (e.g. "pin `pkg==1.9.3`", "re-run job") |
| DR-31 | "Verification" = the next real CI run | 02, 06 | — | High | — | — | **Accept, renamed "outcome tracking"** | We never claim we verified a fix |
| DR-32 | Never blame the triggering commit merely for triggering | (user requirement) | — | — | — | — | **Accept** | Encoded as invariant INV-1 in Plan §7 |

## E. Validation, benchmark, cost, timeline

| ID | Recommendation | Source | Evidence | Conf. | Assumptions | Implications | Decision | Reason |
|---|---|---|---|---|---|---|---|---|
| DR-33 | 16-case benchmark | 04 | UNT | — | — | — | **Modify** | B-11 must set `-W error::DeprecationWarning` to be deterministic. B-16 is redefined as an outcome-tracking case (we don't generate fixes). Every case is run twice (C1 and C2) to score attribution. |
| DR-34 | Thresholds: 05 says "≥25% external" and "<15% stop"; 07 says "continue ≥20%" and "abandon <10%" | 05 §3B/§6, 07 §3 | Inconsistent | — | — | — | **Modify** | Unified gates in Plan §16. Metric precisely defined as "share of red runs where blaming the triggering push would be wrong". Stated intent to pay is replaced by **written pilot terms**. |
| DR-35 | Pricing $99 flat; test $49/$99/$199 | 07 §5 | UNT | — | — | — | **Accept as an experiment** with analysis quotas (Plan §14) | |
| DR-36 | Cost of $0.04–0.06 per failed run | 06 §11 | NEW-V prices | Medium | Token sizes assumed | — | **Modify** | Recomputed: deterministic $0; Haiku ≈ $0.002; Sonnet ≈ $0.04; worst case ≈ $0.21–0.42 (Plan §14) |
| DR-37 | 3 build weeks plus 1 buffer to a paid pilot | 06 §13 | — | Low | — | — | **Reject as optimistic** | Task-level estimate: about 20 dev-days to the internal MVP and about 30 to a hardened pilot (Plan §15) |
| DR-38 | Zero-install "paste a repo URL" teaser | 07 §4 | NEW-V: unauthenticated log download → **403** | High | — | Needs an authenticated token | **Modify** | Build as a CLI for the Phase 0 labeling study. The public web teaser is deferred. |
| DR-39 | Inference that commit comments need `contents:write` (on The Plumber) | 01 §2 | NEW-V: the GitHub permissions table lists `POST /commits/{sha}/comments` under **Contents: read** | Medium (table looks unusual) | — | None for our plan | **Reject** the inference; note it as a correction to `01` | |

## Verification log (newly verified 2026-10-15)

| Fact | Source |
|---|---|
| GitHub does not automatically redeliver failed webhook deliveries | docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries |
| Respond 2xx within 10 s; use a queue; `X-GitHub-Delivery` is unique per event and identical on redelivery | …/best-practices-for-using-webhooks |
| `workflow_run` requires Actions read; actions are `requested`, `in_progress`, `completed`. `installation` and `installation_repositories` are delivered by default. `check_run` `rerequested` needs checks write. | …/webhook-events-and-payloads |
| Job logs: 302 redirect, URL expires after 1 minute. List jobs supports `filter=latest\|all`. | docs.github.com/en/rest/actions/workflow-jobs |
| Unauthenticated job-log download on a public repo returns **403** | Our own curl test (job 71287441089) |
| Runs list: `branch`, `event`, `status`, `head_sha`, `created`; `per_page` ≤ 100; ≤1,000 results per filtered search | …/rest/actions/workflow-runs |
| Required permissions: Actions read for runs, jobs, logs and attempts; Contents read for compare, commits and contents; Checks write for check-run create and update; Pull requests read for `commits/{sha}/pulls` | …/permissions-required-for-github-apps |
| Check runs: only GitHub Apps can create them; ≤50 annotations per request; 1,000 same-name runs per suite; conclusions include `neutral`; `external_id` available; **no documented summary length limit** | …/rest/checks/runs |
| Installation tokens expire after 1 h; can be scoped down by repositories and permissions | …/generating-an-installation-access-token-for-a-github-app |
| Installation rate limit: 5,000/h minimum, up to 12,500 (15,000 on Enterprise Cloud). Secondary limits: 100 concurrent requests, 900 points/min, 80 content-creating requests/min, 500/h. | …/rate-limits-for-the-rest-api |
| Compare: ≤250 commits unpaginated; ≤300 files total | …/rest/commits/commits |
| Actions logs are retained 90 days by default (public repos 1–90 days, private 1–400) | …/configuring-the-retention-period… |
| Run object includes `run_attempt`, `previous_attempt_url`, `head_sha`, `head_branch`, `event`, `workflow_id`, `pull_requests` (empty for forks) | Our API inspection (run 24405466283) |
| Claude per-MTok prices (input / cache hit / output): Opus 5.5 $4 / $0.20 / $20; Sonnet 5.5 $2 / $0.10 / $10; Haiku 5.5 $0.10 / $0.01 / $0.50 (≤100K-token prompts); Batch API −50%; `inference_geo: us` costs 1.1× | platform.claude.com/docs/en/about-claude/pricing |
| API data retention: deleted within 30 days by default per the privacy center; ZDR only by agreement; structured-output schemas cached ≤24 h | privacy.claude.com article 7996866; platform.claude.com/docs/en/manage-claude/api-and-data-retention |
| Fly.io shared-cpu-1x: 512 MB $3.69/mo, 1 GB $6.70/mo; Managed Postgres from $38/mo | docs.fly.io/about/pricing |
| Neon Free: 100 CU-h/project, 6 h history, scale-to-zero after 5 min. Launch: $0.106/CU-h, $0.35/GB-mo, no minimum, history up to 7 days. | neon.com/pricing |
| Render free Postgres expires after 30 days with no backups; Render paid prices were **not retrievable** | render.com/docs/free |
| Sentry Developer plan: 5k errors, 1 user, 30-day lookback; Team $26/mo | sentry.io/pricing |
