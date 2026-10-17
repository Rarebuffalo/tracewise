# Parity vs Differentiation

Date: 2026-10-17. EV-IDs are from [EVIDENCE-LEDGER.md](EVIDENCE-LEDGER.md). Test IDs refer to `final-audit-public/TRACEWISE-PARITY-ACCEPTANCE-TESTS.md` (AT-…) and [BENCHMARK-AND-GROUND-TRUTH-REVIEW.md](BENCHMARK-AND-GROUND-TRUTH-REVIEW.md) (Tracks A–F).

## 1. Core parity

These are supported by sufficiently strong public evidence and needed for a comparable workflow.

| # | Requirement | Evidence strength | Acceptance |
|---|---|---|---|
| CP-1 | GitHub App; no repo config; installed from a public install page | Observed manifest and listing (EV-C01, EV-C04); "no config" documented (EV-C05) | AT-INS-01/02 |
| CP-2 | Triggered automatically by `workflow_run.completed` on failure | Observed manifest (EV-C01); fired on `failure`/`push` once (EV-C06/C09); platform-documented (EV-P01) | AT-EVT-01..03, 05, 06 |
| CP-3 | Reads failed-job logs; identifies the failed step and the first meaningful error; groups siblings | Observed n=1 (EV-C07) | Track A; AT-LOG-01..04, AT-DX-01..03 |
| CP-4 | Reads repository code at the failing commit | Observed: code was read (EV-C08). Mechanism documented only (EV-C05). | AT-CTX-01..04 |
| CP-5 | Diagnosis: root cause, why, file + line + snippet, recommended fix (text), files examined, confidence, fix size | Observed n=1, correct (EV-C07/C08) | Track B; AT-DX-01..06, AT-RPT-01..06 |
| CP-6 | Agent-oriented "edit and verify" block | Observed n=1 (EV-C07) | AT-RPT-08 |
| CP-7 | Post on the commit (push failures) | Observed n=1 (EV-C06) | AT-PUB-01 (G-PLAT-5) |
| CP-8 | Post on the PR (PR failures) | **Documented only** (EV-C04); never observed (EV-C13). Included because it is the advertised core journey and is platform-feasible (EV-P09). | AT-PUB-02/05 |
| CP-9 | Asynchronous processing, so the webhook is not blocked | Inferred strong (EV-C10) + platform-required (EV-P05) | AT-EVT-05 |

**Not parity requirements** (unverified competitor behaviour; do not design to them as fact):

- an agentic tool loop;
- clone vs API;
- latency under 2 minutes;
- retention claims;
- re-run behaviour;
- non-unit-test failure classes.

Our bounded tool loop is **our** design choice (ARCH-REVIEW §5). It is not "copying" the competitor.

## 2. Our own required properties

These are not parity: they are required by platform behaviour or safety.

| Property | Why | Basis |
|---|---|---|
| Signature validation, delivery dedupe, re-run dedupe | Platform | EV-P02, EV-P06, EV-P07 |
| Write-once commit comments; upserted PR comments | Platform (editing commit comments needs Contents write) | EV-P09 |
| PR lookup by API, not from the payload | Platform | EV-P23, EV-P24 |
| Inconclusive path; evidence validator; code-built links | Safety and quality | ARCH-REVIEW §5 |
| Secret redaction; path confinement; prompt-injection and spoofing defences | Security | ARCH-REVIEW §8 |

## 3. Differentiation hypotheses (unvalidated)

**None of these is a demonstrated competitive advantage.** A gap in one public April-2026 demo does not establish one.

| ID | Hypothesis | Problem addressed | Evidence the problem exists | Evidence type | Smallest validating test | In MVP? |
|---|---|---|---|---|---|---|
| DH-1 | **Trigger-diff relevance:** "this push changed only X; not implicated" | Developers wrongly assume their push broke CI | The competitor's only report omitted that the trigger was README-only (EV-C11). Market research on red-main and pre-existing failures (`05`, CircleCI data) is secondary. | Competitor limitation (n=1) + secondary research | Synthetic D-01/D-02/D-03/D-04: correct statement and **no false blame**. Then interviews (G-1) and AT-RPT-10 (≥80% of developers can tell the push didn't cause it). | **Yes.** It is cheap: one compare call, code-computed. Positioned as a signal, not proof. |
| DH-2 | Lane history: last green / first red; "pre-dates this push" | Pre-existing failures blamed on the latest push | Public metadata shows multi-run red streaks in real lanes (EV-P26: flask `Tests` lane, e.g. 7 consecutive reds Feb 2026) | Public observation (n=1 lane) + our hypothesis | Track D P-01/P-02 (metadata) + synthetic B-02 lane | No (P2). Validate on the benchmark first. |
| DH-3 | Flaky handling (same-SHA re-run passes) | Wasted debugging on non-deterministic failures | Platform supports detection (EV-P02). Prevalence is not measured by us. | Our hypothesis | Synthetic D-05/D-06 | No (P2) |
| DH-4 | Dependency-drift attribution | Upstream releases break unpinned projects | Public example of a dev-dependency job failing while the trigger edits app code (EV-P26, **cause unproven**) | Public observation (weak) + hypothesis | Synthetic B-05/B-17 | No (P2) |
| DH-5 | Evidence quality: repo-true paths and ranges, code-built links, confidence with a basis, abstention | Trust in AI output | The competitor's artifacts: wrong path prefix, inconsistent ranges, unexplained "High" (EV-C07, EV-C12) | Competitor observation (n=1) | Track C (evidence validity) + AT-DX-12/13/14 | **Yes:** part of the safety design, cheap |
| DH-6 | Editable surfaces with no duplicate comments on re-runs | Comment noise | Platform constraint (EV-P09) makes the competitor's commit comments write-once. Its actual re-run behaviour is unknown. | Platform inference | AT-PUB-05 | Yes (Check Run as the update channel) |
| DH-7 | Faster diagnosis | Latency | Competitor 6m14s n=1 vs "under 2 min" claim (EV-C10) | Weak (n=1) | AT-OPS-02 + AT-CMP-01 | No claim until measured |

**Rule for any external claim** ("better than The Plumber at X"): it requires **AT-CMP-01**, a head-to-head run on the same repos. That needs user approval for a test org and installing the competitor App. Without it, statements are limited to "Tracewise does X".

## 4. Commercial position (unchanged)

Validate demand before committing to the full build:

- **G-1:** interviews;
- **G-2:** metadata-only lower bound per CM-27;
- **G-3:** commitments;
- **G-PAY:** written paid-pilot terms.

Parity alone is a commodity position (`05` §1: GitHub Copilot, FailBrief, The Plumber). Any defensibility must come from DH-1/DH-5 first, and DH-2–4 later, **if** the benchmark and users validate them.
