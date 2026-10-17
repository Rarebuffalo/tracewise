# Tracewise Repository Audit: Source of Truth, Cleanup and Implementation Readiness

Date: 2026-10-18. Method: read-only inspection of `~/tracewise`, plus a filename-only search of `~` for other Tracewise workspaces (none found).

**No file was moved, edited or deleted.** This report is the only new file.

## 1. Repository path, branch, status

| Item | Finding |
|---|---|
| Path | `/home/Krishna-Singh/tracewise` (the only Tracewise workspace found) |
| Git | **Not a git repository.** No `.git` in this directory or any parent. No branch, history, `.gitignore` or remote. |
| Application code, tests, CI, config, migrations, `.env`, Dockerfiles | **None exist.** The only code is 3 research helper scripts (§2.6). |
| Content | `research/` only: 35 markdown files (34 before this report) + 3 evidence directories (150 files, ≈4.3 MB) |
| Filenames named in the brief (`LATEST`, `v1.1`) | **Not present** anywhere in the workspace |

**Implication:** nothing has been implemented, so there is no risk of implementing anything twice. The only rework risk is planning against the wrong document.

## 2. File inventory (grouped by purpose)

The four document generations:

| Generation | Session and date | Character |
|---|---|---|
| **S1** | Original research and plan, 2026-10-15 | Attribution-only plan |
| **S2** | Audit run under an unintended `gh` account, 2026-10-17 | Evidence quarantined |
| **S3** | Public-evidence audit, 2026-10-17 | Unauthenticated sources only |
| **S4** | Evidence and architecture review, 2026-10-17 | Unauthenticated sources only |

### 2.1 S1 market and competitor research (`research/`)

| File | Purpose |
|---|---|
| `01-product-teardown.md` | The Plumber teardown. Two claims since contradicted: EV-X02 "fixed 200-line window", EV-X03 "commit comments need write". |
| `02-architecture-reconstruction.md` | Competitor reconstruction + first Tracewise design (superseded) |
| `03-competitor-matrix.md` | The Plumber / FailBrief / FixSense / GitHub-native matrix, pricing, traction. **Unique competitor data** (FailBrief, FixSense) not repeated elsewhere. |
| `04-failure-benchmark.md` | **Defines benchmark cases B-01…B-16** (still referenced by 6 docs) |
| `05-opportunity-analysis.md` | Hypotheses A–H; positioning; segment |
| `06-mvp-technical-plan.md` | First MVP plan (superseded by IMPLEMENTATION-PLAN) |
| `07-validation-and-gtm.md` | ICP, **interview script**, decision thresholds, pricing hypotheses, landing copy |
| `08-sources-and-confidence.md` | S1 source list and confidence register |
| `EXECUTIVE-SUMMARY.md` | S1 summary: VALIDATE FIRST; attribution wedge |

### 2.2 S1 implementation plan set (`research/`)

| File | Purpose |
|---|---|
| `IMPLEMENTATION-PLAN.md` | Main engineering plan, ≈100 KB (attribution-only, LLM off) |
| `IMPLEMENTATION-TASKS.md` | Task list T0.01–T6.12, T4B.* |
| `ARCHITECTURE-DECISIONS.md` | ADR-01…13 |
| `DECISION-REGISTER.md` | DR-01…39 + verification log (2026-10-15) |
| `TEST-AND-RELEASE-PLAN.md` | B-case amendments, test layers, G-INT / G-PILOT |
| `RESOURCE-AND-SETUP-CHECKLIST.md` | Accounts, GitHub App setup, `.env.example` spec |
| `OPEN-QUESTIONS.md` | OQ-01…09 |
| `PLAN-REVIEW.md` | Self-critique, contradictions C1–C14 |

### 2.3 S2 audit (research root): **built on quarantined evidence**

| File | Purpose |
|---|---|
| `FINAL-REVERSE-ENGINEERING-AUDIT.md` | S2 audit. Cites the `ksingh-rovn` account and R-cases. |
| `VERIFIED-FEATURE-SPEC.md` | S2 spec |
| `TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` | S2 tests. L20 asks to confirm `ksingh-rovn`. |
| `final-audit/evidence/**` (74 files) | Mixed: a public subset, plus authenticated artifacts and R-case logs **quarantined** |
| `final-audit/PROVENANCE-QUARANTINE.md` | S3 record of what is excluded and why |

**These three filenames duplicate the S3 files in `final-audit-public/`.** Bare-name references are ambiguous.

### 2.4 S3 public audit (`research/final-audit-public/`)

| File | Purpose |
|---|---|
| `FINAL-REVERSE-ENGINEERING-AUDIT.md` | Public-only competitor audit (P-1…P-19) |
| `VERIFIED-FEATURE-SPEC.md` | **Parity spec (FS-…)**. The most complete requirements list. |
| `TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` | **Acceptance tests (AT-…)** |
| `evidence/**` (34 files) | Public competitor artifacts + REA ledger export |
| `provenance/**` (2 scripts + 2 text files) | Redacted provenance extraction |

### 2.5 S4 evidence review (`research/final-evidence-review/`)

| File | Purpose |
|---|---|
| `FINAL-DECISION-REPORT.md` | Decision: YES WITH GATES A–D |
| `IMPLEMENTATION-PLAN-CORRECTION-MATRIX.md` | CM-01…30; 15 blocking |
| `TRACEWISE-ARCHITECTURE-REVIEW.md` | Recommended architecture, UD-1…6 |
| `GITHUB-PLATFORM-VERIFICATION.md` | Platform facts with doc line refs; G-PLAT-1…7 |
| `BENCHMARK-AND-GROUND-TRUTH-REVIEW.md` | Tracks A–F, grading |
| `PARITY-VS-DIFFERENTIATION.md` | CP-1…9, DH-1…7 |
| `EVIDENCE-LEDGER.md` | EV-C/P/T/X records |
| `COMPETITOR-BEHAVIOR-VERIFICATION.md` | Observed / documented / unknown competitor behaviour |
| `INVESTIGATION-PLAN-AND-TOOL-INVENTORY.md` | Tools and methods |
| `REPRODUCIBILITY-AND-PROVENANCE.md` | How to reproduce without credentials |
| `evidence/**` (42 files) | 26 official GitHub doc snapshots, public CI metadata, fetch log, grep script |

### 2.6 Scripts

| File | Purpose |
|---|---|
| `final-audit-public/provenance/extract.py` | Redacting transcript extractor (provenance) |
| `final-audit-public/provenance/extract2.py` | Repository and search-result extractor (provenance) |
| `final-evidence-review/evidence/grep_docs.py` | Doc-claim grep |

## 3. Recommended source of truth

The current documents are **not internally consistent**: the S1 plan set predates S3/S4 and conflicts with them (§5). Until the plan is corrected, the source of truth is this set, in priority order:

| Rank | Document | Role | State |
|---|---|---|---|
| 1 | `final-evidence-review/FINAL-DECISION-REPORT.md` | Current decision and gates | KEEP |
| 2 | `final-evidence-review/IMPLEMENTATION-PLAN-CORRECTION-MATRIX.md` | What must change in the plan | KEEP |
| 3 | `final-audit-public/VERIFIED-FEATURE-SPEC.md` | Requirements (FS-…) | **UPDATE** (§5, F-03/F-04/F-05) |
| 4 | `final-evidence-review/TRACEWISE-ARCHITECTURE-REVIEW.md` | Architecture | KEEP |
| 5 | `final-evidence-review/GITHUB-PLATFORM-VERIFICATION.md` | Platform constraints | KEEP |
| 6 | `final-evidence-review/BENCHMARK-AND-GROUND-TRUTH-REVIEW.md` + `04-failure-benchmark.md` §2 (case definitions) + `TEST-AND-RELEASE-PLAN.md` §2 (amendments) | Benchmark | Consolidation needed (F-07) |
| 7 | `final-audit-public/TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` | Acceptance tests | **UPDATE** (F-03) |
| 8 | `final-evidence-review/EVIDENCE-LEDGER.md` + `final-audit/PROVENANCE-QUARANTINE.md` | Evidence and admissibility | KEEP |
| 9 | `07-validation-and-gtm.md` | Commercial validation (interview script) | UPDATE (F-09, F-10) |
| 10 | `IMPLEMENTATION-PLAN.md`, `IMPLEMENTATION-TASKS.md`, `ARCHITECTURE-DECISIONS.md`, `DECISION-REGISTER.md`, `TEST-AND-RELEASE-PLAN.md`, `RESOURCE-AND-SETUP-CHECKLIST.md`, `OPEN-QUESTIONS.md` | Engineering plan set | **UPDATE**. Not authoritative until the blocking CM items are applied. |

**Proposed end state** (after approval): one `research/README.md` index listing the above. The plan set is regenerated as a single corrected plan; superseded documents move to `research/archive/` (§4).

## 4. Cleanup matrix

**Proposal only. Nothing has been done.**

| Path | Class | Reason | Dependencies / safety check |
|---|---|---|---|
| `final-evidence-review/*.md` (10) | KEEP | Current decision, architecture, platform, benchmark | — |
| `final-evidence-review/evidence/**` | KEEP | Source evidence for S4 claims | Never delete evidence |
| `final-audit-public/FINAL-REVERSE-ENGINEERING-AUDIT.md` | KEEP | Dated public competitor audit; S4 builds on it | Its §7.2 option 1 (project token) is superseded by your decision; noted in F-03 |
| `final-audit-public/VERIFIED-FEATURE-SPEC.md` | UPDATE | Requirements source; 3 gaps (F-03, F-04, F-05) | Referenced by 6 docs |
| `final-audit-public/TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` | UPDATE | REAL-SET option (a) and the real-accuracy gates conflict with your decision | Referenced by 6 docs |
| `final-audit-public/evidence/**`, `provenance/**` | KEEP | Admissible public evidence and provenance | — |
| `final-audit/PROVENANCE-QUARANTINE.md` | KEEP | Admissibility record | Referenced by 4 docs |
| `final-audit/evidence/**` | ARCHIVE (in place) | Quarantined. Retained as historical evidence, never used. | Do not delete (source evidence). Contains public-but-authenticated third-party logs; the decision is yours (Q-6). |
| `FINAL-REVERSE-ENGINEERING-AUDIT.md` (root, S2) | ARCHIVE | Superseded by the S3 version. Built on quarantined data. Duplicate basename. | Unique content: the R-case narrative (quarantined) and correction list C-P1…19 (carried into CM matrix) |
| `VERIFIED-FEATURE-SPEC.md` (root, S2) | ARCHIVE | Superseded by the S3 version; duplicate basename | Referenced ambiguously by basename |
| `TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` (root, S2) | ARCHIVE | Superseded; L20 instructs to confirm `ksingh-rovn` | Same |
| `EXECUTIVE-SUMMARY.md` | ARCHIVE | S1 decision. Next-step 3 instructs `gh auth login`; cost figures withdrawn (CM-12). | Referenced by DECISION-REGISTER and the S4 inventory (historical) |
| `PLAN-REVIEW.md` | ARCHIVE | Superseded by the S4 decision report and CM matrix. Its 7-day-soak option conflicts with G-PILOT (CM-11). | Referenced by IMPLEMENTATION-PLAN |
| `06-mvp-technical-plan.md` | ARCHIVE | Superseded by IMPLEMENTATION-PLAN | Referenced by CM-12/CM-13 (historical citations) |
| `02-architecture-reconstruction.md` | ARCHIVE | Part A superseded by the S3/S4 competitor docs; Part B by ARCH-REVIEW | 0 references |
| `01-product-teardown.md`, `08-sources-and-confidence.md` | ARCHIVE | Historical research; partly contradicted (EV-X02, X03) | 0 / 3 references (historical) |
| `03-competitor-matrix.md`, `05-opportunity-analysis.md` | ARCHIVE | Historical. **Contain unique info** (FailBrief/FixSense detail, hypotheses A–H). Keep accessible. | 0 / 1 references |
| `04-failure-benchmark.md` | NEEDS REVIEW | Still the **only definition of B-01…B-16** (6 references) | Archive only after its §2 is consolidated into one benchmark spec |
| `07-validation-and-gtm.md` | UPDATE | Interview script still needed for G-0. G-2 definition, quota and "60 seconds" copy are outdated. | — |
| S1 plan set (7 files, §3 rank 10) | UPDATE | See §5 | Heavily cross-referenced; update as one change |
| Helper scripts (§2.6) | KEEP | Needed to reproduce provenance and doc checks | — |
| **REMOVE CANDIDATES** | **None confirmed** | Every file is either evidence, holds unique historical content, or is referenced. Deletion would lose provenance. | — |

**Proposed archive layout** (needs approval; moving files breaks relative references, which must be fixed in the same change):

- `research/archive/2026-10-15-s1-research/`: 01, 02, 03, 05, 06, 08, EXECUTIVE-SUMMARY, PLAN-REVIEW
- `research/archive/2026-10-17-s2-audit-quarantined/`: the three root S2 files

Each archive folder gets a `README.md` stating what superseded it.

## 5. Contradictions and missing requirements

Ordered by severity.

| ID | Sev. | File / section | Conflict or gap | Evidence | Resolution | Human decision? |
|---|---|---|---|---|---|---|
| F-01 | **Critical** | `IMPLEMENTATION-PLAN.md` (L329 LLM "Off in the MVP"; §4.4.3; §4.6.2); `ARCHITECTURE-DECISIONS.md` ADR-06 (Check Run only), ADR-08; `DECISION-REGISTER.md` DR-09, DR-27, DR-30 | Plan is attribution-only. It cannot deliver the parity scope in the S3 spec: no AI diagnosis, no code context, no commit or PR comments, no parity tasks. | CM-02…05, CM-24 | Apply the blocking CM items; regenerate the plan and tasks | **Yes**: approve parity scope (Q-1) |
| F-02 | **Critical** | `IMPLEMENTATION-TASKS.md` T0.01 L53–55; `RESOURCE-AND-SETUP-CHECKLIST.md` R3 L16, L109; `EXECUTIVE-SUMMARY.md` L105; `04-failure-benchmark.md` L97; `OPEN-QUESTIONS.md` OQ-02 L20 | Instructs `gh auth login`, a personal lab PAT and authenticated log downloads, **contrary to your 2026-10-17 instruction** | User instruction; EV-P13 | Remove; Phase 0 G-2 becomes metadata-only (CM-21, CM-27, CM-28) | Already decided by you; apply |
| F-03 | High | `final-audit-public/TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` L16–18 (REAL-SET option a), L81, L89, L100, L102, L104, L194; `final-audit-public/FINAL-REVERSE-ENGINEERING-AUDIT.md` L229; `final-audit-public/VERIFIED-FEATURE-SPEC.md` FS-SEC-5 L82 ("benchmark uses a project-scoped token") | Still offers token-based real-log benchmarking and ≥70% real-accuracy gates, which you ruled out | Your decision (synthetic + public metadata) | Replace REAL-SET with S4 Track D (metadata, job/step-level only). Drop real-accuracy gates. | No (decided) |
| F-04 | High | `final-audit-public/VERIFIED-FEATURE-SPEC.md` FS-PUB-2 | **No PR-association method specified.** S1 plan uses payload `pull_requests` (`IMPLEMENTATION-PLAN.md` L439, L643, L853), which is unreliable. | EV-P23, EV-P24; CM-06 | Add the requirement: API lookup, fork-aware (`/commits/{sha}/pulls`; `/pulls?head=owner:branch`) | No |
| F-05 | High | Same spec FS-EVT-5 | Reconciliation covers failed deliveries only. Events over 25 MB are never delivered. | EV-P04; CM-22 | Add a bounded failed-run sweep | No |
| F-06 | High | `IMPLEMENTATION-PLAN.md`, `IMPLEMENTATION-TASKS.md`, `TEST-AND-RELEASE-PLAN.md` | No log-spoofing defence; prompt-injection tests only in optional Phase 4B (T4B.05 L643) | CM-18, CM-19 | Move into the MVP | No |
| F-07 | Medium | `04-failure-benchmark.md` §2 + `TEST-AND-RELEASE-PLAN.md` §2 + `final-evidence-review/BENCHMARK-AND-GROUND-TRUTH-REVIEW.md` §3 + S3 tests B-17 | The benchmark is spread over 4 files with amendments in 2 places | Cross-references (§2) | Consolidate into one benchmark spec with `truth.yaml` per case | No |
| F-08 | Medium | `TEST-AND-RELEASE-PLAN.md` §6; `IMPLEMENTATION-TASKS.md` L26/L631 | G-INT depends on Phase 6 T6.12 and on unobtainable real logs | CM-09 | G-INT = synthetic Tracks A–E + metadata Track D | No |
| F-09 | Medium | `07-validation-and-gtm.md` L139; `05` L96, L155; `06` L5 | "60 seconds" / "under a minute" promises. Latency is unmeasured; the competitor observed 6m14s (n=1). | CM-13; EV-C10 | Remove from copy until measured | No |
| F-10 | Medium | `07` L104 (1,000) vs `OPEN-QUESTIONS.md` L27, `IMPLEMENTATION-PLAN.md` L1523 (1,500); cost figures in `06` L222/L225, `EXECUTIVE-SUMMARY` L89, `05` L195, `DECISION-REGISTER` DR-36, PLAN §14 | Conflicting quota and cost figures; all predate the tool-loop scope | CM-10, CM-12 | Withdraw; re-model after benchmark measurement | Pricing later (Q-7) |
| F-11 | Medium | `IMPLEMENTATION-PLAN.md` L58, L1563, L1574 (22.5 / 31.5 dd) | The estimate predates the scope change | CM-25 | Re-estimate after Q-1…Q-3 | No (needs the decisions first) |
| F-12 | Low | Duplicate basenames (§2.3) | Ambiguous references | — | Archive the S2 trio | Approve cleanup (Q-6) |
| F-13 | Low | `IMPLEMENTATION-PLAN.md` L508, `ARCHITECTURE-DECISIONS.md` L215 | References nonexistent T2.06 | CM-08 | T6.03 | No |
| F-14 | Low | `PLAN-REVIEW.md` L63 vs `TEST-AND-RELEASE-PLAN.md` L188 | 7- vs 14-day soak | CM-11 | Pick at pilot time | Later |

## 6. Implementation status (code and tests)

**No application code or tests exist.** Each candidate requirement is therefore at most *specified*. "Specified in" cites the governing document.

| Candidate requirement | Status | Specified in | Gap |
|---|---|---|---|
| GitHub Actions failure ingestion | Specified, not implemented | Spec FS-EVT-1…4; PLATFORM §1–2 | `startup_failure` gated (G-PLAT-1) |
| Deterministic analysis before AI | Specified | Spec FS-LOG-2, FS-DX-1/2; ARCH §3 | — |
| Bounded read-only AI investigator | Specified | Spec FS-DX-3; ARCH §5 | Plan still says LLM off (F-01). Model not chosen (Q-4). |
| Evidence validation + inconclusive fallback | Specified | Spec §3 rules 1–8, FS-DX-8 | — |
| Diagnosis fields (root cause, why, location, text fix, files examined) | Specified | Spec FS-DX-4/5, FS-RPT-1…6 | Plan schema lacks them (CM-05) |
| Three surfaces (commit comment, PR comment, neutral Check Run) | Specified | Spec FS-PUB-1…4 | Check Run inclusion awaits Q-2. Commit comment with Contents read is untested (G-PLAT-5). |
| PR association via API, fork-aware | **Partially specified** (S4 only) | ARCH §2; CM-06 | Missing from the spec (F-04). Fork behaviour gated (G-PLAT-4). |
| Least-privilege permissions | Specified | PLATFORM §3; spec FS-INS-2 | Plan and DR-09 conflict (F-01) |
| Injection resistance, redaction, path safety, bounded tools | Specified | Spec FS-SEC-1/2, FS-LOG-5, FS-CTX-1; ARCH §8 | Plan lacks spoofing defences and MVP injection tests (F-06) |
| Missed-run recovery, quotas, lifecycle, failure handling | Partially specified | Spec FS-EVT-5, FS-QTA-1, FS-INS-3, FS-ERR-1…3 | Sweep missing (F-05). Quota has no task (CM-14). Uninstall mid-job (CM-16). |
| Synthetic benchmark + separate public-metadata track | Specified (S4) | BENCHMARK §3–4 | Not consolidated (F-07); harness not built |
| Acceptance tests | Specified, **none executed** | S3 tests AT-… | REAL-SET parts invalid (F-03) |

**No accuracy, latency, cost, production-readiness or parity claim is supported**, because no system exists.

## 7. Security and benchmark evidence findings

| # | Finding | Status |
|---|---|---|
| S-1 | S2 used the unintended `gh` account (`ksingh-rovn`) on 102 public repos. Artifacts are quarantined (`final-audit/PROVENANCE-QUARANTINE.md`). | Contained. Quarantined data is not used in S3/S4 conclusions (S4 quality gate). |
| S-2 | Instructions to authenticate remain in S1/S2 docs (F-02; the S2 tests file L20 says "confirm `ksingh-rovn`") | **Violation risk if followed**: fix or archive |
| S-3 | S3 docs still propose a project token for benchmarks (F-03) | Conflicts with your decision |
| S-4 | Synthetic and public-metadata results are kept separate in S4 BENCHMARK §4. Metadata is limited to job/step-level labels (EV-P26). | Compliant |
| S-5 | No document claims measured accuracy or parity. Vendor claims are labelled (e.g. the FixSense 87% case study in `03` is marked vendor). | Compliant. Marketing copy latency claims flagged (F-09). |
| S-6 | No Cloudflare bypass, no competitor install, no execution of repo code or log-suggested commands occurred in any session | Compliant (S3/S4 records) |
| S-7 | No secrets in the deliverables. S4 token-pattern hits are placeholder examples in the GitHub docs snapshots. | Compliant |
| S-8 | `final-audit/evidence/benchmark/` holds third-party public CI logs downloaded with the unintended account | Your call whether to retain (Q-6). They are not used. |

## 8. Missing information and files

You do **not** need to upload anything. All source documents are present.

| Category | Item | Why needed | Enables | Blocker? | Where |
|---|---|---|---|---|---|
| Product decisions | Q-1…Q-5 (§10) | Scope and plan regeneration | Corrected plan, tasks, estimate | **Hard** (Q-1, Q-5) | Your answer |
| Source documents | **None missing** | — | — | — | — |
| Implementation details | Bottom-up re-estimate | Scheduling | Timeline | Hard for scheduling; produced by us after Q-1…Q-3 | To be generated |
| Implementation details | Consolidated benchmark spec + `truth.yaml` per case | Gates G-INT | Testable MVP exit | Hard before the eval | To be generated from the 4 sources (F-07) |
| Environment / integration | A version-control location (Q-5) | Any code | Implementation start | **Hard** | Your decision |
| Environment / integration | Dev GitHub App + test org | Live gates G-PLAT-1…7, Track F | Accepting the publishing code | Deferrable (offline work first) | You create, when you choose. Never share secrets in chat. |
| Environment / integration | LLM provider account for evaluation | Track B, model choice | Q-4 | Deferrable to the investigator phase | You provision later; configured locally via env, never pasted |
| Tests and evidence | Synthetic harness, fixture repos, `truth.yaml` | Tracks A–E | G-INT | Generated during implementation | — |
| Tests and evidence | G-0 evidence: interview notes; metadata-only G-2 study | Commercial gate | BUILD vs NARROW/ABANDON | Hard for the **full build**, not for starting | Does not exist yet; produced by doing Phase 0 |

## 9. Recommended implementation sequence

1. **Decisions Q-1…Q-6** → then a single approved documentation change:
   - archive per §4;
   - apply the 15 blocking CM items;
   - fix F-03/F-04/F-05 in the spec and tests;
   - consolidate the benchmark (F-07);
   - add `research/README.md`.
2. **Set up version control** (Q-5) with the project-scoped identity. `.gitignore` excludes evidence bulk only if you choose so.
3. **In parallel, Phase 0 (G-0) without credentials:** interviews (07 script) plus the metadata-only G-2 lower bound.
4. **Offline foundation** (no GitHub account): repo scaffold, config, Postgres job queue, webhook ingest with HMAC + dedupe (REPLAY tests).
5. **Synthetic harness + Tracks A/C/E fixtures.** This depends on 4 only for the repo; it can start alongside.
6. **Deterministic pre-pass** (failed step via jobs-API fixtures, first error, siblings) → Track A.
7. **Code context** (shallow fetch against local fixture repos; path confinement) → AT-CTX.
8. **Investigator + validator + inconclusive path** → Tracks B/C/E. This needs the LLM provider (Q-4).
9. **Renderer + publishers** (commit comment write-once, PR upsert with API lookup, Check Run if Q-2) → REPLAY tests.
10. **Live gates G-PLAT-1…7 and Track F.** These need the dev App and test org you approve (Gate C).
11. **Pilot hardening:** RLS, sweep, quotas, purge. Then G-PAY before any external install (Gate B).

## 10. Decisions that require your input

| # | Question | Default if you agree |
|---|---|---|
| **Q-1** | Approve the parity scope (AI diagnosis on by default, code context, three publishing surfaces) and the 15 blocking plan corrections? | Approve |
| **Q-2** | Include the neutral Check Run in the MVP (adds `checks:write`)? | Yes |
| **Q-3** | Launch languages: Python only, or Python + TypeScript? | Python first; TypeScript second |
| **Q-4** | Which LLM provider to evaluate first? The model is then chosen by benchmark. | Your choice; no key needed until step 8 |
| **Q-5** | Where should code live? `git init` in `~/tracewise` using your `rarebuffalo` identity, or a separate repo? Private remote or none yet? | `git init` here; no remote until you say |
| **Q-6** | Approve the §4 cleanup (archive moves + link fixes)? Keep or delete the quarantined third-party logs in `final-audit/evidence/benchmark/`? | Archive as proposed; keep quarantined logs untouched |
| Q-7 (later) | Pricing and quota | After cost measurement |
