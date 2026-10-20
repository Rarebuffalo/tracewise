# History rewrite record (2026-10-20)

Before the first push, the local history was rewritten **once** with `git filter-branch`, with the owner's approval
(Phase 53, option 3). The only change: in `research/final-audit-public/evidence/marketplace.html`, the values of
the signed-URL parameters `X-Amz-Credential`, `X-Amz-Signature` and `jwt` were replaced with `REDACTED`, from the
commit that introduced the file onward. Commit order, messages, authors and dates are unchanged, and every
commit's tree is identical apart from that file. See [SECURITY-AUDIT.md](SECURITY-AUDIT.md) §1.

Because every commit hash changed, **commit hashes quoted in dated records** (CHANGELOG entries, benchmark-run
records, the security audit, the benchmark review queue) are the **pre-rewrite** hashes. Those records are kept
as written; use this table to find the published commit.

| Pre-rewrite | Published | Subject |
|---|---|---|
| `9c4fdd7` | `85f190a` | docs: canonical documentation set, archive superseded research, consistency checker |
| `424b9c7` | `350bc8c` | feat: offline scaffold, contracts and deterministic pre-pass (T-101..T-206) |
| `2e8187d` | `9e8fde7` | feat(db): schema, repositories, Postgres job queue and worker (T-104, T-105) |
| `bac2c23` | `d0314cf` | feat(web): signed webhook endpoint with atomic, idempotent ingestion (T-106) |
| `7e76d77` | `508b212` | feat(github): App JWT, scoped in-memory installation tokens, REST client (T-301, T-302) |
| `dcdbfd9` | `8206089` | feat(github): fork-aware PR association by API (T-303) |
| `c6388f4` | `c24d73f` | feat(context): secure no-checkout code context with Contents-API fallback (T-304) |
| `7e39264` | `1ed8a11` | feat(context): read-only investigation tools with isolated grep (T-305) |
| `8beddcd` | `de069ae` | feat(context): trigger diff and three-valued touches_implicated (T-306) |
| `5affcd8` | `182e89b` | fix(github): report ambiguous PR association instead of guessing (T-303 review) |
| `539323a` | `83f77bd` | feat(analysis): deterministic evidence collection stage (T-307) |
| `9b9351c` | `8737b22` | feat(investigate): provider seam and bounded investigation loop (T-401, T-402) |
| `d497fde` | `660b3b4` | feat(investigate): evidence validation, inconclusive fallback, confidence (T-403, T-404) |
| `00b1558` | `6be2e0e` | feat(report): deterministic, escaped Markdown report renderer (T-501) |
| `803913d` | `e48ca48` | test+docs: connected offline diagnosis path and batch documentation |
| `cea5f66` | `f0b2e2e` | fix(github)+feat(db): no inline POST retries; publication state migration 0002 |
| `0e32ba1` | `dd7b561` | feat(publish): idempotent, reconciling GitHub publisher (T-502) |
| `e46f088` | `f5322ad` | feat(worker): wire the analyze handler end to end; failure outcomes (T-502, T-503) |
| `d4745aa` | `b328f1c` | feat(bench): benchmark fixtures, ground truth and TRUTH.lock (T-601 builder, T-602 cases) |
| `5da428c` | `8674f64` | feat(bench): scorer, per-track report and CLI (T-603); harness robustness |
| `6b71e49` | `defb063` | test+docs(bench): hand-calculated scorer tests, harness validation, findings |
| `3e2ceed` | `cd8acc0` | fix(bench): an unexecuted required run makes the suite incomplete; complete slow-inclusive run |
| `3055064` | `5be1bde` | feat(lifecycle): installation and repository lifecycle webhooks (T-701) |
| `caaf044` | `bc9c7fd` | feat(recovery): webhook redelivery and failed-run sweep (T-702) |
| `4635669` | `e149d45` | feat(security): Postgres row-level security and tenant isolation (T-705) |
| `7d3f44d` | `aa063af` | test(integration): cross-phase lifecycle, recovery and RLS audit; benchmark rerun |
| `c6ff8a8` | `1ea10e1` | fix(security): runtime roles cannot write migration state; tenant plane fails closed (audit) |
| `5f22172` | `c459f4b` | feat(ops): structured operational events, per-analysis record, report and failure-rate alert (T-706) |
| `a7b54b4` | `e49d358` | feat(retention): bounded, restart-safe retention and tenant purge (T-704) |
| `9d54137` | `7f5dcba` | test+docs(github): integration contract audit; pin token-bundling and lifecycle edge behaviour |
| `6ee3ca7` | `f4902dc` | test+docs(bench): pin current behaviour on the review items; review-only proposal queue |
| `9e85a02` | `4fd6046` | test(integration): full chain from signed webhook to tenant purge (Phase 10) |
| `fe90eed` | `95562ac` | docs(audit): final acceptance audit record and benchmark rerun (Phase 10) |
| `617907b` | `8597550` | fix(security): purge definer search_path; nested log scrubbing; CLI logging and failure handling (Phase 11 audit) |
| `4be7939` | `c2615fb` | test(db): fresh-install lifecycle from a reviewed role template (Phase 12) |
| `7e19cf5` | `9896455` | fix(recovery): isolate per-repository faults; correct stop labels; record uncertain redeliveries (Phase 13) |
| `db1b39e` | `492997a` | fix(ops): close redaction bypasses; tolerate malformed ops records (Phase 14) |
| `7154054` | `0af9d5e` | test(integration): independently verified full chain for push and PR runs (Phase 15) |
| `3717b46` | `1e6b39f` | docs(release): offline operations runbook and staged live GitHub validation plan (Phase 16) |
| `dd3196c` | `4ade890` | feat(runtime): runnable web (ASGI factory) and worker process entry points (Phase 18) |
| `03bac1a` | `eb76713` | feat(model): provider-neutral HTTP adapter core with contract tests; no real model (Phase 19) |
| `eec9a4b` | `49934f4` | test(acceptance): local operator acceptance across the runnable system (Phase 20) |
| `57ac589` | `26d6fd5` | docs(audit): Phase 21 final offline release-readiness audit and benchmark rerun |
| `890e806` | `d533e3a` | docs(audit): record the Phase 21 changelog entry and benchmark history line |
| `f23b41f` | `68b8840` | docs+fix(privacy): T-1001 notice draft and data inventory; redact the stored snippet and replacement (Phase 23) |
| `e6ebf09` | `ad35c80` | test+docs(model): close adapter contract-test gaps; OpenAI contract checklist C-1..C-9 (Phase 24) |
| `c911d87` | `d386d99` | docs(deploy): vendor-neutral T-1002 deployment blueprint; record the unwired log-cap setting (Phase 25) |
| `6f4c089` | `37dbf88` | test(repro): documentation-consistency and clean-environment workflow tests (Phase 26) |
| `2a9167e` | `2244836` | docs(security): Phase 27 release-gate review with evidence mapping |
| `b902270` | `71bde9a` | docs(audit): Phase 28 final offline gate record and benchmark rerun |
| `d2e495c` | `e803c4c` | test(privacy): independent end-to-end P-1 verification and AT-SEC-04 provider capture (Phase 29) |
| `1f30461` | `771909c` | fix(privacy): cap log excerpts at 2000 UTF-8 bytes (FS-SEC-3 '<=2 KB'; Phase 30) |
| `ab0d6de` | `d10842c` | fix(logs): flag download-cap truncation; wire LOG_MAX_BYTES_PER_JOB as the FS-LOG-4 budget (Phase 31) |
| `a2fb574` | `d1aa7be` | test(model): provider selection boundary in every environment (Phase 32) |
| `c9cb3cd` | `c56ae5d` | test(acceptance): privacy boundaries and malformed provider responses in operator acceptance (Phase 34) |
| `f7c923b` | `1f0681e` | docs: decision memos (P-2, P-3, C-CFG-1), privacy data-flow table, reconciled operator docs (Phases 29-33) |
| `c6b864f` | `641b0ef` | docs(audit): Phase 34 final gate record and benchmark rerun |
| `921c5e6` | `4454d2e` | fix(privacy): keep database and validation error text content-free in last_error (P-5) |
| `95053ee` | `fbcabe7` | fix(report): a truncated log with no error line no longer claims the log has none (L-2) |
| `d2c0b90` | `6e444b5` | fix(worker): install graceful signal handlers before startup (W-1) |
| `142c893` | `0478ff4` | test: download-cap boundaries, full-path excerpt cap, no-real-model proof; secret-free test ids |
| `6d55fbb` | `dd1a474` | docs: Phases 35-41 verification record, decision-queue classification, readiness report |
| `10eee06` | `f5a06d0` | fix(privacy): stored error text never depends on input (P-5 completion) |
| `b8ce802` | `25e2527` | fix(report): incomplete-log wording also covers partly unavailable logs (L-2 refinement) |
| `ebc430c` | `6775040` | test(worker): signal between start-up and the first claim (W-1 coverage) |
| `ded4dc8` | `3fc8f23` | docs: owner decision sheet; Phase 43 review record |
| `67e4ec3` | `41fef55` | docs(bench): resolve B-02 as documentation; correct the B-04 decision wording |
| `7e3022e` | `dd3509c` | docs: conditional implementation plan per owner decision (nothing approved) |
| `17c2f28` | `b82208c` | feat(privacy): redact all repository-derived content at the provider boundary (P-2, approved option A) |
| `c436a1f` | `aaaea58` | feat(privacy): cap the persisted source snippet at 2000 UTF-8 bytes (P-3, approved option A) |
| `ebc58e2` | `29843a2` | feat(publish): re-check authorisation before every surface; suspension needs an explicit retry (D-10) |
| `ad3b9ce` | `e2742a7` | docs(research): record the official OpenAI Responses API contract (R-1..R-14, gaps G-1..G-6) |
| `f24b3e3` | `6d93219` | feat(investigate): OpenAI Responses wire codec, tested offline; LLM_PROVIDER=openai still refused |
| `4b19d7a` | `33cefeb` | docs: C-1..C-9 status for the offline OpenAI codec; mark the Phase 45 approvals implemented |
| `2dae10d` | `6a953ab` | fix(investigate): keep provider-issued call ids exact; fail closed on ambiguous pairing |
| `917baff` | `573f28b` | fix(investigate): only provider-issued reasoning items may use the unredacted replay channel |
| `fd7cd94` | `48eb0bb` | fix(investigate): codec errors never quote the provider document; correct the stale adapter docstring |
| `ada3883` | `f1b6e2c` | test: P-3 boundary sweep and D-10 coverage for the PR and notice publication paths |
| `273494f` | `a6ab655` | docs: record the Phase 46 codec corrections, the replay-channel rules and gaps G-7/G-8 |
| `3ffcab4` | `e17e567` | feat(scripts): isolated OpenAI smoke harness, rehearsed offline only (not run against OpenAI) |
| `6762a81` | `d8a448e` | docs: smoke runbook and owner authorisation checklist; Phase 47 gap classification |
| `e229f94` | `3d94769` | fix(investigate): a message item whose content is not a list fails closed as WireError |
| `60a8dca` | `627f2c8` | fix(scripts): smoke harness handles unexpected JSON structures (D-48-1) and enforces wall-clock deadlines (D-48-2) |
| `d88189b` | `7220a94` | docs: smoke runbook deadline semantics (§4a), failure evidence and exit classes 1, 8 and 10 |
| `8e91a75` | `312f792` | fix(prepass): one pip resolution failure is one primary, not two (A-04) |
| `1603831` | `8e48caf` | fix(reliability): deadline-limited final attempts notify the user (A1); cooldown cannot drop a redelivery (A2) |
| `a971185` | `0b294b9` | fix(security): untrusted text cannot become a link (A3) or choose which report a marker names (A4) |
| `9f9bd7c` | `9007ef2` | fix(db): per-installation run, publication and signature keys (migration 0010); transfer no longer kills jobs |
| `efaafb3` | `e910bc0` | fix(ops): web process and ops CLI enforce the system-plane role (C, D) |
| `bb7b0c9` | `23a4645` | docs: Phase 50 change log |
| `c568ab4` | `0179271` | fix(reliability): final-attempt GitHub failures publish the notice when nothing can be visible (FS-ERR-1) |
| `9197f31` | `50e7fe3` | test(prepass): held-out checks for the A-04 grouping change, with recorded counterexamples |
| `cdb9f1b` | `34a454f` | ci: offline quality gate (lint, strict typing, docs, truth lock, full tests under the network guard) |
| `585b7f9` | `1fba155` | test(ops): backup/restore, privilege-matrix drift and alert-boundary evidence; stage coverage notes |
| `ead68af` | `3e33fc3` | docs: Phase 51 change log |
| `78e9ac0` | `0478956` | fix(prepass): one installer failure report is one primary across pip, npm and uv |
| `3c230d2` | `58150fb` | test+docs: network-guard decision tests, restored-grant check, and the consolidated owner-decision packet |
| `27e863e` | `27ea395` | docs: Phase 52 change log |
