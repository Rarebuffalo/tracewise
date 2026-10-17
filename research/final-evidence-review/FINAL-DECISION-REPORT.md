# Final Decision Report

Date: 2026-10-17. Scope: an evidence-driven verification of The Plumber's observable behaviour and of Tracewise's MVP architecture.

| Source rule | Status |
|---|---|
| Sources | Public and unauthenticated only |
| Credentials | None used |
| GitHub accounts or orgs | None created |
| App installs | None |
| Files modified | None |

## 1. Executive conclusion

1. **The competitor's observable core workflow is well enough understood to specify parity.** The basis:
   - a GitHub App on `workflow_run`;
   - logs plus code read at the failing commit;
   - a structured report with root cause, location, fix, files examined and an agent block;
   - posting on the commit (observed) or the PR (advertised).

   This comes from the manifest, GitHub-verified permissions, the Marketplace listing and **one** correct public report (EV-C01…C12). **Runtime behaviour beyond that single April-2026 report is unknown.** The vendor site is Cloudflare-gated, and no live test was run.
2. **The current implementation plan does not implement parity.** It is attribution-only with the LLM off, has no code-context component, no commit or PR comment publishers, and no tasks for them. It also contains a platform error: PR association taken from `workflow_run.pull_requests`, which was empty in 20/20 sampled PR runs (EV-P23).
3. **The plan's Phase 0 and its commercial gate G-2 depend on downloading public CI logs.** That is **impossible without credentials**: anonymous downloads return 403 even on public repos (EV-P13). They must be redefined.
4. **Several platform assumptions are undocumented** and need live tests in an authorized environment: delivery of `startup_failure`; per-attempt delivery on re-runs; comment and Check Run length limits; fork-PR publishing; commit comments with Contents **read** only.
5. **The commercial recommendation is unchanged:** validate demand before committing to the full build.

## 2. Strongest findings (with evidence)

| # | Finding | Evidence |
|---|---|---|
| 1 | Competitor permissions are read-mostly. It can create, but not edit, commit comments. It cannot create Check Runs. | EV-C01, EV-C02, EV-P09 |
| 2 | Its only public report is correct on root cause, location and fix, but gives no attribution. The trigger was README-only. | EV-C08, EV-C09, EV-C11 |
| 3 | The vendor self-attests use of a third-party LLM API. It names no model. Its source repo is private. | EV-C03 |
| 4 | `workflow_run.pull_requests` cannot be relied on: empty in 20/20 PR runs; documented empty for forks. Commit→PR lookup fails for fork heads. | EV-P23, EV-P10, EV-P24 |
| 5 | Logs need authentication even on public repos | EV-P13 (contradicts a naive reading of EV-P12) |
| 6 | Events over 25 MB are never delivered. Failed deliveries are not auto-redelivered. Delivery IDs persist on redelivery. | EV-P04, EV-P06 |
| 7 | Length limits for comments and Check Run output are undocumented | EV-P11 |
| 8 | Public metadata supports job/step-level attribution labels (pre-existing, first failure, fix commit), not error-level truth. A real public example shows the "trigger edits a source file but only a dependency job fails" trap. | EV-P26 |
| 9 | Prior claims withdrawn or contradicted: "fixed 200-line window"; "commit comments need write"; "logs expired 410" (quarantined source) | EV-X01…X03 |

## 3. Material unknowns

| Unknown | Why it matters | How it could be resolved |
|---|---|---|
| Competitor behaviour on flaky, dependency, infra, multi-error, inconclusive cases, re-runs, PRs; current (post-April) behaviour | Differentiation claims | AT-CMP-01 (needs approval) |
| Competitor stack, LLM vendor and model, actual retention | Not needed for parity | Vendor pages (human must pass Cloudflare) |
| Whether `startup_failure` is delivered | Event filter | G-PLAT-1 |
| Re-run delivery per attempt | Dedupe and publishing | G-PLAT-2 |
| Output length limits | Renderer cap | G-PLAT-3 |
| Fork PR Check Run, comment and lookup | Fork support | G-PLAT-4 |
| Commit comment with Contents read only | The push-failure parity surface | G-PLAT-5 |
| Uninstall mid-job; declined permission upgrade | Reliability | G-PLAT-6/7 |
| Real-world accuracy, prevalence and willingness to pay | Commercial | G-0 (interviews, metadata-only G-2, commitments, written pilot terms) |

## 4. Blockers

These are the correction-matrix items that block implementation from starting:

| Item | Blocker |
|---|---|
| CM-02 | LLM on by default |
| CM-03 | Permissions and the three publishers |
| CM-04 | Code-context component |
| CM-05 | Diagnosis v2 |
| CM-06 | PR association by API |
| CM-09 | G-INT redefined (synthetic + metadata) |
| CM-15 | Publisher idempotency per surface |
| CM-18 | Log-spoofing defences |
| CM-19 | Injection tests in the MVP |
| CM-21, CM-27, CM-28 | Phase 0 and G-2 without credentials |
| CM-24 | Parity tasks |
| CM-25 | Re-estimate |
| CM-26 | Benchmark tracks |

## 5. Risks

| Risk | Mitigation |
|---|---|
| Parity is commoditised (Copilot, FailBrief, The Plumber); differentiation is unproven | DH-1 and DH-5 in the MVP; validate with users; AT-CMP-01 before any claim |
| An LLM "valid citation" is mistaken for "causal support" | Code-computed causal fields; `high` confidence requires deterministic corroboration; Track B/D grading with a −3/−5 penalty for confident-wrong |
| Prompt injection and log spoofing through repo-controlled output | Read-only tools, schema output, jobs-API steps, corroboration rule, Track E |
| Live platform behaviour differs from docs | G-PLAT-1…7 before the publishing code is considered done |
| Cost and latency unknown under the tool-loop scope | Withdraw old figures (CM-12/13); measure on the benchmark |
| Benchmark realism (synthetic plus job-level metadata only) | Report tracks separately; no real-world accuracy claims |

## 6. Quality-gate results (this review)

| Gate | Result |
|---|---|
| High-impact claims cross-checked against the ledger | Every claim in §2 cites EV-IDs. Each EV-ID cites a saved artifact or REA evidence ID. |
| Contradictions | Kept explicit: EV-X01…X06; EV-P12 vs EV-P13 |
| Source references and local paths | 76 cited paths checked: **0 missing** |
| Quarantined data | Deliverables cite only the admissible S2 subset (`marketplace.html`, `gh-perms.md`, `gh-webhooks.md`, `dns.txt`, `crtsh.json`, `site-paths.txt`, `rea/*`). Other `final-audit/evidence` mentions are exclusion notes. **No quarantined content entered conclusions or the benchmark.** R-run IDs are allowed only as pointers with re-derived public labels. |
| Secrets | Token-pattern scan: 7 hits, all placeholder examples inside the official GitHub Docs pages ("Bearer YOUR-TOKEN", "Bearer JWT"). **No credentials.** |
| Originals unchanged | SHA-256 of all 24 pre-existing markdown files matches the 17:23Z baseline |
| Blockers identified, not just suggestions | Correction matrix "Blocks" column; blocking set listed |
| Acceptance tests measurable | Each Track case has an expected output and a ground-truth source; grading is fixed in advance (BENCHMARK §4). The live Track F is defined but gated. |
| Architecture sufficient without copying private internals | Yes: the ARCH-REVIEW components map to CP-1…CP-9, and no competitor internal is assumed |
| What could not be verified | §3 |

## 7. Recommended next actions

1. **Decide** on the blocking corrections (§4), then apply them to the plan in a separate, approved edit. This review does not edit the plan.
2. **Commercial validation (G-0)** in parallel, with G-2 redefined as a metadata-only lower bound (CM-27). No credentials needed.
3. **Build the offline synthetic harness and benchmark** (Tracks A–E). No GitHub account needed.
4. **When you choose**, approve a project-scoped test org and dev App for the live gates G-PLAT-1…7 and Track F.
5. **Optionally**, approve AT-CMP-01 (installing The Plumber in that test org). It is required before any competitive claim.

## 8. Decision

### Can we safely lock the MVP specification and begin implementation?

## **YES, WITH SPECIFIC GATES**

**Lockable now:**

- the core parity requirements CP-1…CP-9;
- the required safety and platform properties (PARITY §2);
- the minimum permission set (Actions r, Contents r, Metadata r, Pull requests w, Checks w);
- the architecture in ARCH-REVIEW §1.

**Not lockable yet** (left open in the spec by design):

- `startup_failure` handling;
- output size caps;
- fork-PR publishing details;
- shallow fetch vs API (UD-2);
- model and provider (UD-3).

**Unresolved items that determine the answer:**

1. **Gate A (before any implementation):** the 15 blocking plan corrections are applied and approved (CM-02, 03, 04, 05, 06, 09, 15, 18, 19, 21, 24, 25, 26, 27, 28).
2. **Gate B (before committing to the full build):** G-0 demand validation passes with the metadata-only G-2 definition. This is the commercial recommendation.
3. **Gate C (before the publishing and integration code is accepted):** live gates G-PLAT-1…7 pass. These need an authorized test org and dev App, which **you** must approve. Until then only UNIT/REPLAY work and Tracks A–E proceed.
4. **Gate D (before any "better than The Plumber" claim):** AT-CMP-01. This needs approval to install the competitor App in a test org.
5. **Open decisions:**
   - UD-1: Check Run in the MVP (recommended yes);
   - UD-2: code-context approach;
   - UD-3: model, by evaluation;
   - OQ-04: Python only vs Python + TypeScript.
