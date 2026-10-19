# Owner decision sheet (Phase 43)

Plain-language summary of what is waiting on you. Detail and evidence are in [DECISION-MEMOS.md](DECISION-MEMOS.md), [BENCHMARK-REVIEW-QUEUE.md](BENCHMARK-REVIEW-QUEUE.md), [MODEL-ADAPTER.md](MODEL-ADAPTER.md) and [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md). Nothing here is decided in code.

## Already settled by the spec (no decision needed)

| Item | Settled by | Status |
|---|---|---|
| Log retention budget of 2 MB per job; the log must be flagged when incomplete | SPEC FS-LOG-4 | Implemented and tested |
| Stored log excerpts ≤2 KB (we use 2000 bytes, which satisfies both readings of KB) | SPEC FS-SEC-3; ACCEPTANCE-TESTS AT-SEC-12 | Implemented and tested |
| Inconclusive when the logs are truncated past the error | SPEC FS-DX-8 | Behaviour matches. The wording no longer claims "no error line" for incomplete logs (L-2). |
| Log secrets never reach the model | SPEC FS-LOG-5; ACCEPTANCE-TESTS AT-SEC-04 | Tested |
| `flaky_suspect` only with attempt metadata; otherwise inconclusive is acceptable (B-04) | ACCEPTANCE-TESTS AT-DX-11; BENCHMARK §2 (≤ medium) | **The product does not meet this yet.** The only open question is timing: see B-04 below. |

## Decisions

| # | What needs deciding | Options | Recommendation | Consequences | What it unblocks |
|---|---|---|---|---|---|
| 1 | **P-2.** Should repository content (file excerpts, search results, diffs) be redacted before it is sent to the AI provider? Logs already are. | **A** redact them. **B** keep as is and disclose it. **C** A, plus refuse to read secret-looking files (`.env`, `*.pem`, keys). | **A**, before any real-provider use | A: committed secrets stop reaching a third party; a small, unmeasured risk of confusing the model on secret-related bugs. B: no change; disclosure only. C: strongest, but could hide a relevant config file. | Offline implementation and tests (scoped in the memo); the privacy-notice wording |
| 2 | **P-3.** How large may the stored source snippet be? It is currently up to 15 lines and ≤4000 chars, redacted, kept 90 days. | **A** cap the stored copy at 2000 bytes. **B** write the 4000-char limit into the spec. **C** don't store it. | **A** | A: matches the strict reading of the 2 KB rule; reports still show 15 lines. B: no behaviour change. C: smallest footprint; reports are unaffected because they are rendered from memory. | Offline implementation |
| 3 | **C-CFG-1.** Per-log download cap | **A** keep 512 MB. **B** 256 MB. **C** make it configurable. | **A** until staging measures real download times | Bigger caps catch errors deep in huge logs but can consume much of the 10-minute job budget on a slow link. Smaller caps finish sooner but flag more logs as incomplete. The spec only needs ≥200 MB (AT-LOG-04). | A staging measurement task |
| 4 | **D-10.** (a) Re-check permission before *each* publishing surface? Today it is checked once, before publishing starts. (b) Should runs cancelled while an installation was suspended be re-analysed after unsuspend? Today they are not. | (a) yes or no. (b) yes, re-queue recent ones; or no. | (a) **yes** (one extra query per surface). (b) your product call. | (a) narrows the window in which a just-suspended installation still receives a report. (b) re-queueing means analyses arrive late; not doing it means suspended-period failures stay unanalysed. | Offline implementation; live stage S3 confirms GitHub's side |
| 5 | **D-12.** Retention interpretations | (a) Is the whole diagnosis document an "excerpt", cleared at 90 days? (b) 365 days for jobs, runs, usage and redelivery bookkeeping, where no period is stated. (c) Keep audit rows after a tenant purge. (d) Keep a minimal tombstone with no expiry, to stop re-activation. | Accept as implemented, or name changes | Affects the diagnosis text, job and run metadata, audit records, and the installation row | Privacy-notice §5 can be finalised |
| 6 | **Alert threshold.** It currently fires when (dead jobs + could-not-complete) ÷ finished jobs ≥ **0.2** over 1 hour, with at least 10 jobs. **Provisional.** | Confirm 0.2, or choose another value | Keep it provisional until staging traffic exists, then set it from the observed baseline failure rate | Too low means noisy pages; too high means missed outages | Schedule and routing (T-1002) |
| 7 | **AWS signed URLs** in `research/final-audit-public/evidence/marketplace.html` | Redact the query strings, or leave as is | **Redact** before any push. No history rewrite is needed. | They are GitHub's own S3 links and expired 2026-10-17 (5-minute signature), but a signature is a capability. Redacting keeps the evidence readable. | Only an edit to that file (it is evidence, so it needs your approval) |
| 8 | **Benchmark items** | see below | — | Never changed to make scores pass | — |
| 9 | **OpenAI adapter** | Approve recording the official API reference | **Approve** when ready | No key is needed to record it | Writing the codec offline; a key comes later for T-605 |
| 10 | **Live pilot prerequisites** | see below | — | — | — |

### 8. Benchmark items: what kind of problem each is

| Item | Kind | Plain explanation | Recommendation |
|---|---|---|---|
| D-5 | Diagnosis policy | When the compiler points at a different file from the real defect, the correct answer is rated *low* confidence | Keep strict until real-model data exists |
| B-04 | **Spec conformance** (AT-DX-11), timing only | A correct "flaky" answer is rated *high* without attempt data; the spec says ≤ medium | Implement the cap; decide whether a held-out evaluation must come first |
| B-12 | Validator policy | Citing a **deleted** file is treated as invalid evidence | Decide together with D-5 |
| A-05 | Ground truth | The product meets AT-LOG-04 (error kept, truncation flagged), but the truth file also expects `first_error`, which the canonical test does not require | Approve a truth correction (new lock), or keep |
| E-01 | Safety, needs a real model | Prompt-injection resistance cannot be shown with fake providers | Measure in T-605 |
| B-02 | Documentation only | The fixture says `0.21 == 1.21`; one catalogue row says `2.71` | Fix the catalogue text |

None of these is a test-harness defect: the harness is verified by hand-calculated scorer tests.

### 9. OpenAI adapter

- **Approval needed:** obtaining the official OpenAI API reference pages for the chosen API, and recording them as dated evidence with example requests and responses (C-1 to C-9 in MODEL-ADAPTER §2).
- **Then offline:** the wire codec (endpoint, auth header, encode, decode), golden tests, error and rate-limit handling, and enabling `LLM_PROVIDER=openai`.
- **Later, with a key:** a smoke call, behavioural checks, the T-605 benchmark evaluation, model choice and prices.

### 10. Live pilot prerequisites

1. A dedicated **test GitHub organisation** and a **development GitHub App** (permissions per SPEC FS-INS-2) to run LIVE-VALIDATION-PLAN S0–S3.
2. **Database roles** provisioned from `scripts/db/provision_roles.sql`, with separate credentials (D-11).
3. A **hosting platform** (ADR-09): TLS and a public webhook URL, a secret store, process supervision (DEPLOYMENT-BLUEPRINT).
4. **Alert routing** and schedules for recovery, retention and alerts.
5. A **model**: items 9 and T-605.
6. **Legal and privacy review**: complete PRIVACY-NOTICE-DRAFT (owner, contact, legal basis, provider terms) and the pilot terms.
