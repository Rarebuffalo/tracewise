# Implementation Plan Correction Matrix

Date: 2026-10-17. The plan files are **not edited**. Line numbers are from `grep -n` on the unchanged files (2026-10-15 versions). EV-IDs are from [EVIDENCE-LEDGER.md](EVIDENCE-LEDGER.md).

**Priority**

| Priority | Meaning |
|---|---|
| **P0** | Must be fixed before implementation proceeds past the affected phase |
| **P1** | Before the first external installation |
| **P2** | Documentation or commercial consistency |

**Blocks** = blocks starting implementation of the core MVP. "Yes" items must be corrected first.

| ID | Existing section / task | Inconsistency or unsupported assumption | Evidence | Required correction | Impact | Priority | Blocks |
|---|---|---|---|---|---|---|---|
| CM-01 | `IMPLEMENTATION-PLAN.md` L370 (§4.4.3, Checks row) | "No output channel without `pull_requests:write` or `issues:write`" | EV-P09: a commit comment needs Contents **read** | Correct the statement. List all three output surfaces and their permissions. | Doc only; enables CM-03 | P2 | No |
| CM-02 | PLAN L329 (LLM "Off in the MVP"); FR-018 L171; ADR-08; DECISION-REGISTER DR-27, DR-30 | Attribution-only, deterministic MVP **cannot produce the competitor's core output** (root cause, location, fix) | EV-C07, EV-C08 | LLM investigation **on by default** for parity, bounded and read-only (ARCH-REVIEW §5). DR-30 stays: no patches or PRs, but a *text* fix is required. | New components; eval task; cost model | P0 | **Yes** |
| CM-03 | DR-09, DR-15; PLAN §4.4.3 | `pull_requests:write` dropped. No commit-comment or PR-comment publisher. | EV-C04 (advertised), EV-C06 (commit comment observed), EV-P09 | Permissions: Actions r, Contents r, Metadata r, **Pull requests w**, Checks w. Publishers: commit comment (write-once), PR comment (upsert), Check Run. | Permission set; publisher module | P0 | **Yes** |
| CM-04 | PLAN §7.8 L5 and §4.4.7 (contents API only for lockfiles and test files) | No general code-context component | EV-C08 (code reading is necessary for parity) | Add a code-context component: shallow single-commit fetch or the API fallback, with path confinement (ARCH-REVIEW §4) | New component and tasks | P0 | **Yes** |
| CM-05 | PLAN §4.6.2 `Diagnosis` and LLM schema v1 | No `root_cause`, `why`, `problem_location`, `fix`, `files_examined`, `failed[].step` and `command` | EV-C07, EV-C12 | Adopt S3 Diagnosis v2 plus validator rules 7–8 | Contracts, renderer | P0 | **Yes** |
| CM-06 | PLAN L439 (`pr_numbers` from payload), L643, L853; UC-2 | PR association taken from `workflow_run.pull_requests` | EV-P23 (empty in 20/20 PR runs), EV-P10 (documented empty for forks), EV-P24 (commit→PR lookup empty for a fork head) | Resolve PRs by API: `GET /commits/{sha}/pulls` (same repo), `GET /pulls?head=owner:branch` (forks). Treat payload `pull_requests` as a hint only. | Publisher correctness | P0 | **Yes** |
| CM-07 | PLAN L986 (`lane_key = repo:workflow_id:event_class:branch`) | Fork branches with the same name share a lane | EV-P23 (fork PR runs carry `head_repository`) | Add `head_repo_id` to the lane key | Lane attribution (P2 feature) | P1 | No |
| CM-08 | PLAN L508; ARCHITECTURE-DECISIONS L215 (U-3 → "T2.06") | Task T2.06 does not exist (it is T6.03, `IMPLEMENTATION-TASKS.md`). U-3 is also now answerable from docs. | `IMPLEMENTATION-TASKS.md` T6.03 row; EV-P06 (endpoint paths) | Reference T6.03. Record the paths `GET /app/hook/deliveries`, `POST /app/hook/deliveries/{id}/attempts`. | Doc | P2 | No |
| CM-09 | TEST-AND-RELEASE §6 G-INT and PLAN L1592 (G-INT needs "real held-out"); TASKS L26 (G-INT at the end of Phase 5) vs L631 (T6.12 "G-INT real" in Phase 6) | G-INT depends on a Phase 6 task, and its real data (T0.03 logs) is not obtainable under the no-credential rule | TASKS L26/L27/L631; EV-P13 | Redefine G-INT = synthetic Tracks A–E (BENCHMARK §3) plus public-metadata Track D. Move any real-data evaluation to a later gate that names its data source. | Gate definitions | P0 | **Yes** (the MVP exit criterion is otherwise undefined) |
| CM-10 | `07-validation-and-gtm.md` L104 (1,000 analyses) vs `OPEN-QUESTIONS.md` L27 and PLAN L1523 (1,500) | Conflicting $99 quota | Files cited | Pick one, after re-costing (CM-12) | Commercial | P2 | No |
| CM-11 | TEST-AND-RELEASE L188 and PLAN L1574 (14-day soak) vs PLAN-REVIEW L63 ("7 days" option) | An option contradicts the release gate | Files cited | Either keep 14 days, or amend G-PILOT explicitly for a "friendly-partner" pilot with stated risk | Pilot timing | P2 | No (blocks pilot release only) |
| CM-12 | `06-mvp-technical-plan.md` L222 ($0.04–0.06), L225 ($60–150/mo infra); EXECUTIVE-SUMMARY L89; `05` L195 ($0.003–0.07); DR-36 and PLAN §14 ($0.007–0.021; $36–40/mo) | Five cost figures. **All assume ≤2 LLM calls; parity uses a tool loop of ≤12 calls.** | Files cited; ARCH-REVIEW §5 | Withdraw all cost figures for pricing. Re-model from measured tokens and calls on the synthetic benchmark. | Pricing, quotas | P1 | No (blocks pricing, not building) |
| CM-13 | `06` L127 (p50 45 s); PLAN NFR-002 L178 (p50 60 s / p95 180 s) vs worker timeout L300 (180 s); `05` L155 and `07` L139 ("under a minute" / "60 seconds"); S3 spec (p50 2 min / p95 5 min) | Unmeasured, mutually inconsistent targets. p95 equals the hard timeout. Marketing copy promises 60 s. | Files cited; EV-C10 (competitor 6m14s, n=1) | One set of **targets** marked unmeasured. p95 < hard timeout. Remove "60 seconds" from copy until measured. | NFRs, copy | P1 | No |
| CM-14 | TASKS (no quota task; "quota" appears only in pricing, PLAN L1522–1523) | Quota enforcement not implemented | grep result | Add a task: per-installation monthly quota, over-quota Check Run notice | Cost control | P1 | No |
| CM-15 | TASKS T5.02/T5.03 (re-runs only for Check Run update and outcome) | No write-once logic for commit comments; no PR-comment upsert on re-runs | EV-P09 (commit comment not editable without Contents write); EV-P02 | Publisher idempotency per surface (ARCH-REVIEW §7); G-PLAT-2 | Duplicate-comment risk | P0 | **Yes** (publisher) |
| CM-16 | PLAN L459 (`installation.deleted` cancels **queued** jobs) | Running jobs are not covered | EV-P21 | In-flight: token mint 401/404 → `cancelled_uninstalled`, no publish (G-PLAT-6) | Reliability | P1 | No |
| CM-17 | PLAN L501 (403 → `UNATTRIBUTED` for reads) | Publish-time 403 (permission removed or declined) not handled | EV-P21 | Publish failure path: record the missing permission; fall back to another surface; metric (G-PLAT-7) | Reliability | P1 | No |
| CM-18 | PLAN, TASKS, TEST-AND-RELEASE: **no mention of log spoofing** (grep empty) | Repo code can print fake markers and versions that steer attribution | ARCH-REVIEW §3; BENCHMARK E-03/E-04 | Steps from the jobs API; corroboration rule; tests E-03/E-04 in the MVP | Security | P0 | **Yes** (MVP done criteria) |
| CM-19 | TASKS L643 (T4B.05 prompt-injection tests in **optional** Phase 4B) | With the LLM on by default, injection tests must be in the MVP | CM-02 | Move them into the core phases; Track E | Security | P0 | **Yes** |
| CM-20 | PLAN L852 (contract enum includes `startup_failure`) | The enum is fine, but `startup_failure` delivery is undocumented | EV-P03 | Analyse only `failure` and `timed_out` until G-PLAT-1 | Event filter | P2 | No |
| CM-21 | TASKS T0.01 (`gh auth login`, lab PAT), T0.02/T0.03 (download and label 200 public logs), T3.09 (goldens from T0 logs); RESOURCE R3 (`GITHUB_TOKEN_LAB`) | **Conflicts with the 2026-10-17 instruction** (no personal or global credentials). Anonymous logs return 403. | EV-P13; user instruction | G-2 becomes a **metadata-only lower bound** (job/step level: pre-existing, flaky by attempt). Parser goldens come from synthetic offline logs. Remove the lab PAT. | Phase 0, Phase 3A, commercial gate G-2 | P0 | **Yes** |
| CM-22 | PLAN §4.4.9 (reconciliation redelivers *failed* deliveries) | Events over 25 MB are **never delivered**, so they cannot be redelivered | EV-P04 | Add a bounded hourly sweep of recent failed runs per enabled repo | Missed analyses | P1 | No |
| CM-23 | PLAN L522 (summary 8 KB, text 32 KB) vs S3 spec FS-RPT-10 (60,000 chars) | Caps differ; GitHub limits are undocumented | EV-P11 | One provisional cap, confirmed by G-PLAT-3 | Renderer | P2 | No |
| CM-24 | TASKS (Phases 1–5) | **The parity requirements have no concrete tasks**: code context, investigator plus tools, validator v2, competitor-section renderer, commit-comment and PR-comment publishers, PR lookup | S3 spec P0 list | Add tasks with acceptance criteria mapped to AT-IDs | Scope | P0 | **Yes** |
| CM-25 | PLAN L58, L1563, L1574 (22.5 / 31.5 dd); DR-37 | The estimate predates the scope change. S2's "+5–7 dd" is an unverified guess. | CM-02…CM-05, CM-24 | Re-estimate bottom-up (assumptions below). **No figure is given here.** | Schedule | P0 | **Yes** (for scheduling) |
| CM-26 | TEST-AND-RELEASE §2–§6 | Benchmark built for the attribution-only categories; relies on the T0.03 real set | BENCHMARK §1 | Replace with Tracks A–F and the grading in BENCHMARK §4 | Test plan | P0 | **Yes** (with CM-09) |
| CM-27 | PLAN §16 G-2 (≥20% of runs where blaming the push is wrong, from log-labelled data) | Not measurable as defined under the constraint | CM-21 | Redefine as a metadata-only lower bound (pre-existing + same-SHA-flaky shares). State that dependency and environment causes are not countable without logs. | **Commercial decision gate** | P0 | **Yes** (for the G-0 decision) |
| CM-28 | RESOURCE-AND-SETUP-CHECKLIST R3; TASKS T0.01 | Personal lab token and `gh auth login` | User instruction; S3 provenance incident | Project-scoped credentials only (dev App). No CLI login for research tooling. | Policy | P0 | **Yes** |
| CM-29 | PLAN §4.4.10 ("fork PRs [UNK]: skip publishing") | Acceptable, but untested | EV-P10, EV-P24 | Keep the fallback; add G-PLAT-4 | Forks | P1 | No |
| CM-30 | PLAN §7 (reads code at `head_sha`) | For PR runs CI tested the merge commit; base changes are invisible | EV-P20, EV-P22 | State the limitation in reports. Optionally compare base-branch status (P2). | Diagnosis caveat | P2 | No |

## Blocking set (must be corrected before implementation starts)

CM-02, CM-03, CM-04, CM-05, CM-06, CM-09, CM-15, CM-18, CM-19, CM-21, CM-24, CM-25, CM-26, CM-27, CM-28.

## Assumptions needed for a new bottom-up estimate (CM-25)

No figure is given. These must be fixed first:

1. **Final MVP scope:** whether the Check Run stays (UD-1) and whether lane attribution stays P2.
2. **Code-context approach:** shallow fetch vs API (UD-2), and the size limits.
3. **Language coverage at launch:** Python only, or Python + TypeScript (OQ-04).
4. **Investigator:** tool set and call limit (≤12); number of evaluation iterations allowed before the model choice.
5. **Benchmark:** whether the live track (Track F) is in scope before G-INT, which depends on approval of a test org.
6. **Pilot hardening items** retained from Phase 6: RLS, reconciliation, sweep, purge, quotas.
7. **Developer capacity:** ≈5 productive days per week, as previously assumed.
8. **Buffer policy** for unknowns from the G-PLAT-1…7 outcomes.
