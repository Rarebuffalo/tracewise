# Implementation plan after owner decisions (conditional; nothing approved)

**Status:** every step below is **pending approval**. No decision has been recorded as approved: see OWNER-DECISION-SHEET.md. Each step is one commit, or a small group, with no unrelated behaviour bundled. "Validation" means focused tests, then the full suite under the network guard, `make check`, the benchmark (truth lock unchanged unless the step says otherwise) and the secret-output scan.

## 1. P-2: redact repository content before model calls (if A or C is approved)

| Aspect | Plan |
|---|---|
| Files and interfaces | Tool results enter messages in `investigate/loop.py` (the `ev.tools.call(...)` result, wrapped by `Delimiter.wrap`). The diff comes from `context/trigger.py::TriggerDiff.render` (via `get_diff`). Apply `prepass.sanitize.redact` to the content **before** wrapping. **C only:** a path deny-list in `context/tools.py` (`_read_file`, `_grep` file selection) for `.env*`, `*.pem`, `*.key`, `id_rsa*` and similar, which returns a fixed "not readable" result. |
| Regression tests | Flip `test_model_input_privacy.py::test_p2_*`: secrets planted in source, grep and diff must be **absent** from the provider capture. Add the same to the operator acceptance test (planted secret in a repository file). C: deny-list tests, including path tricks such as case, `./`, and symlinks already blocked. |
| Privacy and behaviour change | Committed secrets no longer reach the provider. The validator still reads the raw file, so validated locations, snippets and fixes are unaffected. |
| Compatibility | The oracle benchmark is unaffected (scripted answers). A real-model quality impact is **unmeasured**: check it in T-605. |
| Validation criteria | Zero planted repository secrets in any provider request; benchmark identical; no change to stored or published data. |
| Commit boundary | One commit for A. C as a second commit. |

## 2. P-3: stored source snippet (A, B or C)

| Aspect | Plan |
|---|---|
| Files and interfaces | The snippet is built in `investigate/validate.py` and persisted via `jobs/handlers/analyze.py::_persist` → `repositories.upsert_analysis`. **A:** cap the *stored* copy to 2000 UTF-8 bytes in `_persist`, on whole lines, with a truncation marker. **C:** drop `problem_snippet` in `_persist`. **B:** spec edit only (SPEC §3.1 and FS-SEC-3 note). |
| Regression tests | A: a persistence test with a long multibyte snippet stays ≤2000 bytes and remains redacted. C: the stored diagnosis has no snippet. For both: the rendered report still shows ≤15 lines (rendered in the same job from the in-memory diagnosis), and `test_privacy_flow.py` still passes. |
| Privacy and behaviour change | A: smaller stored source fragments. C: none stored. Published reports are unchanged. |
| Compatibility | The benchmark scores the in-memory diagnosis, so it is unaffected. Nothing reads the stored snippet back (only the purge touches `diagnosis`). |
| Commit boundary | One commit |

## 3. D-10: authorisation and suspension (two independent approvals)

**(a) Re-check before each surface (if approved).**
- **Files:** `jobs/handlers/analyze.py::_run` and `_publish_notice`. Call `_recheck(deps, job)` immediately before each of `pr_comment`, `commit_comment` and `check_run`.
- **Tests:** flip `test_github_contracts.py::test_suspend_between_surfaces_*` and `test_adversarial.py::test_repository_removed_during_publication_pending_d10`. Expect the job `cancelled`, no Check Run after the suspension, and the earlier surface left in place.
- **Behaviour:** a just-suspended or just-removed installation receives no further surfaces.
- **One commit.**

**(b) Re-analyse runs cancelled during a suspension (only if approved separately).**
- **Files:** `web/lifecycle.py` (the `unsuspend` path) re-enqueues jobs cancelled with `installation_suspended` within a bounded window, using a new dedupe key.
- **Tests:** flip `test_github_contracts.py::test_run_cancelled_by_suspension_*`; check the bound, idempotence and no duplicate publication.
- **Separate commit.**

## 4. Explicitly specified or owner-confirmed benchmark items

| Item | After approval | Commit |
|---|---|---|
| B-04 | Implement the chosen variant in `investigate/confidence.py`, conditioned on attempt metadata (`job.attempt` > 1 or recorded prior attempts): (a) cap at medium, or (a′) inconclusive. Truth is **unchanged**; the B-04 outcome should move from `overconfident` to an accepted outcome. If required, add a held-out flaky check in T-605. | One |
| A-05 | Truth correction (drop `first_error_contains`): bump the case version, regenerate and commit `TRUTH.lock` **with explicit approval** | One (truth only) |
| D-5 / B-12 | Validator or confidence policy, only if approved, with B-01 and B-12 regression updates | Separate |
| E-01 | Nothing until T-605 | — |

## 5. OpenAI adapter (after reference approval)

Record the official reference (C-1 to C-8) as dated evidence. Write `OpenAIWire` and golden tests. Wire `LLM_PROVIDER=openai` in `investigate/providers.py`, updating `test_providers.py` and the structural no-real-model test deliberately. No key is needed. Separate commits: evidence, codec, wiring.

## 6. Live and real-model work (only with access)

LIVE-VALIDATION-PLAN S0–S3 (test org and dev App), then G-PLAT-11 and D-10 confirmation. T-605 with a key: benchmark, E-01, model choice, prices (C-9). Neither is run offline.
