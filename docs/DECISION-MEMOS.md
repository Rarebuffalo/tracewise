# Decision memos (Phase 29–31): for your review

Each memo quotes the canonical text, states the current behaviour (with evidence), and gives options with their consequences and tests. Where the canonical text was unambiguous, the fix is already made and the memo says so. Nothing marked **open** has been changed.

---

## P-2: Should repository content be redacted before it is sent to the model? (**open**)

**Canonical text:**
- FS-LOG-5: "Before any storage or LLM call: … redact secrets." It is in the **log** requirement group.
- AT-SEC-04: secrets in **a log** → "absent from storage, fake-provider request capture and report".
- FS-SEC-1: prompt-injection controls.

No requirement addresses secrets in **repository content** sent to the model.

**Current behaviour:**

| Sent to the provider | Redacted? | Bound |
|---|---|---|
| Evidence bundle: repo, SHA, run ids; job and step names; command (wrapped as untrusted); ±10/+30 log lines around each primary error; changed-file paths | Log lines: **yes** (FS-LOG-5, verified by `test_model_input_privacy.py::test_at_sec_04_*`). Other fields are metadata. | `MAX_BUNDLE_CHARS`, `MAX_CONTEXT_LINES` |
| `read_file` results (source windows) | **No** (`test_p2_*` pins this) | ≤250 lines and ≤8000 chars per call; ≤12 calls |
| `grep` results | **No** | ≤50 matches; lines ≤240 chars |
| `list_dir` | Names only | ≤300 entries |
| `get_diff` (trigger patches) | **No** | ≤8000 chars |
| Prior assistant turns (the model's own text) | n/a | `max_output_chars` |

No current behaviour contradicts an explicit requirement. The gap is that no requirement covers repository content.

**Trade-off:** redaction is pattern-based (tokens, keys, JWTs, URLs with credentials, private-key headers). Applied to source it would replace those tokens with `[REDACTED]`. The diagnosis rarely depends on a secret's value, so quality loss is expected to be small, but that is **unmeasured**. The risk of *not* redacting is that hard-coded credentials in a customer's repository reach the provider and fall under its retention terms (unknown until C-8).

| Option | What changes | Risks | Tests required |
|---|---|---|---|
| **A (recommended):** redact tool results and the diff with the same `redact()` before they enter a message | `ToolBox.call` output and `TriggerDiff.render` | A redacted line may confuse the model about a secret-related bug, which is rare. The validator still reads the raw file, so validated locations are unaffected. | Planted secrets in source, grep and diff absent from the provider capture (flip `test_p2_*`); the benchmark is unchanged (oracle); T-605 measures model impact |
| B: keep as is and disclose (the current draft notice does) | None | Third-party exposure of committed secrets | None new |
| C: A, plus refusing `read_file` on paths matching secret-file patterns (`.env`, `*.pem`, `id_rsa`) | `context/tools.py` | Could hide a legitimately relevant config file | Path-denial tests; benchmark cases must still pass |

**Decision needed:** A, B or C. A or C must be decided before any real-provider pilot.

---

## P-3: Does the "≤2 KB" rule apply to the stored source snippet? (**partly resolved**)

**Canonical text:**
- FS-SEC-3: "never persist raw logs or source. Redacted excerpts ≤2 KB for 90 days."
- AT-SEC-12: "excerpts ≤2 KB".
- SPEC §3.1 schema: `primary_errors[].excerpt: "<redacted>"`, and **separately** `problem_snippet: "≤15 lines copied by the system from the file at head_sha (FS-DX-4)"`.
- FS-RPT-4: the report shows a "≤15-line snippet".

**What was unambiguous, and is fixed (Phase 30):**
- **Log excerpts** (`primary_errors[].excerpt`, the schema field literally named "excerpt") fall under "≤2 KB". KB is a byte unit, but the code capped at 2048 **characters**, so non-ASCII text could reach about 8 KB.
- Now: redact first, then cap at **2000 UTF-8 bytes** without splitting a character. That satisfies 2 KB under both the 1000-byte and the 1024-byte reading (`excerpt_of`; `test_log_excerpts_are_at_most_2kb_in_bytes_*`).
- The benchmark is unchanged.

**Interpretation of "≤2 KB":**
- The spec does not define KB (1000 or 1024 bytes).
- 2000 bytes is ≤2 KB under **both** readings. 2048 would breach the 1000-byte reading.
- The cap applies to the **stored and rendered** `primary_errors[].excerpt`. FS-SEC-3 is a persistence rule.
- The log context sent to the model is bounded separately (`MAX_CONTEXT_LINES`, `MAX_BUNDLE_CHARS`) and is not an "excerpt" in this sense.

**Verified (Phase 38):**
- redaction runs before the cut, so redaction cannot push it over the limit;
- no character is ever split;
- the cap holds on the full pre-pass path for traceback, generic and multi-line shapes (`test_excerpt_cap_holds_through_the_full_prepass_path`).

**What is ambiguous (open):** whether the **source snippet** is an "excerpt". The schema names it differently and bounds it by lines (15). FS-SEC-3's "never persist … source" plus "excerpts ≤2 KB" can be read to include it.

| Path | Current |
|---|---|
| Stored `problem_snippet` | ≤15 lines and ≤4000 chars (model constraint, not in the spec); redacted (P-1) |
| Rendered report | ≤15 lines; redacted at render; stored on GitHub under the customer's control |
| Model input | Not affected: the snippet is created after the model answers |

| Option | Privacy | Diagnostic and UX | Tests |
|---|---|---|---|
| **1 (recommended):** treat the snippet as an excerpt; cap the stored snippet at 2000 bytes (keep whole lines, mark it truncated) | Matches the strict reading of FS-SEC-3 | Long lines are cut in the stored copy only; the report could still show 15 lines from the live file at publish time | Byte-cap test on the stored snippet; benchmark Track C "snippet identical" must still pass (the B-case snippets are short). Confirm no truth change. |
| 2: snippet is not an excerpt; keep ≤15 lines and set the 4000-char limit in the spec | Larger stored source fragments for 90 days | Unchanged | Spec edit only; existing tests |
| 3: do not store the snippet at all; re-derive it at render time | Strongest | Re-renders need source access, so later report edits would need a fetch | Persistence test that the snippet is absent; render path change |

**Implications in more detail:**
- **Option 1:** caps the *stored* copy only. The in-memory diagnosis and the published report can keep 15 lines, so the benchmark (which scores the in-memory diagnosis) is unaffected. Storage drops from ≤4000 characters to ≤2000 bytes per analysis.
- **Option 2:** changes no behaviour, only the spec.
- **Option 3:** removes the snippet at persistence. Reports are rendered in the same job from the in-memory diagnosis, so publication is unaffected. Later re-renders within the same job are unaffected. Stored analyses lose the snippet: no analysis UI or API reads it today.

None of the options has a measured effect on diagnostic quality. The model never sees the snippet, because it is built after the model answers.

**Decision needed:** 1, 2 or 3.

---

## C-CFG-1: Log-size configuration versus large logs (**resolved from the spec**)

**Canonical text:**
- FS-LOG-4: "Stream. Keep the failed-step section, ±200 lines around each error marker and the first error-like line, **≤2 MB per job**. Set `log_truncated` and show it."
- AT-LOG-04: a 200 MB log keeps the error at line 3,000,000, sets `log_truncated=true`, and has a peak RSS under 300 MB.

**Finding:** there are three distinct boundaries, and the documented 2 MB is the **retention** budget, not a download limit.

| Boundary | Value | Enforced | Status |
|---|---|---|---|
| Download per log | 512 MB (`Limits.max_log_bytes`) | While streaming; decoded bytes, so gzip cannot inflate past it | **Defect fixed:** a cut download was invisible. If the failed step lay past the cut, `log_truncated` stayed false. The stream now exposes `truncated` and collection flags that job's log (`test_download_cap_truncation_is_reported_as_log_truncated`). |
| Retained per job | 2 MB (FS-LOG-4) | `prepass.envelope.retain`, O(budget) memory | **Wired:** `LOG_MAX_BYTES_PER_JOB` was documented but unused. It is now the retention budget, default unchanged (`test_retention_budget_per_job_is_configurable`; worker build path `test_worker_wires_the_log_retention_setting_*`). |
| Jobs per run | 5 (`MAX_JOBS`) | `collect_evidence` | Unchanged |

**Units and boundaries (verified, Phase 37):**
- **Download cap:** counts decoded UTF-8 bytes while streaming. At exactly the cap the log is complete; one byte over drops the partial tail line and sets `truncated`. Multibyte characters are never split (`test_download_cap_boundaries_and_truncation_signal`).
- **Retention budget:** counts **sanitised and redacted** retained line bytes, plus a newline each. Its four parts (first error, windows, head, tail) sum exactly to the budget.
- **Truncation signal:** observable after consumption. A mid-stream error is recorded as a missing log, which also sets `log_truncated`.
- **Report wording:** with a truncated log and no error line, the report now says that no error line was found *in the retained part* and that the error may lie beyond it. It no longer says "the log has no error line" (`test_truncated_log_without_error_line_never_claims_*`).

**Remaining for review (open, minor):**
- The 512 MB download cap is not in the spec, and a slow 512 MB stream could take up a large share of the 10-minute deadline (30 s read timeout per chunk).
- Options:
  - keep 512 MB (AT-LOG-04 needs at least 200 MB);
  - lower it to, say, 256 MB, which is still ≥200 MB, to bound time;
  - make it configurable.
- Memory is bounded by the retention budget (5 × 2 MB per job), not by the download size. AT-LOG-04 (slow test) verifies peak RSS.

---

## Decision-queue classification (Phase 40)

| # | Item | Class | Evidence and what is needed |
|---|---|---|---|
| 1 | P-2 (model-input redaction of repository content) | **User decision** | No requirement covers repository content (FS-LOG-5 and AT-SEC-04 are about logs). Recommendation: option A before any real-provider pilot. |
| 2 | P-3 (stored snippet size) | **User decision** (log-excerpt half resolved by FS-SEC-3 and AT-SEC-12) | SPEC treats the snippet separately ("≤15 lines"). Recommendation: option 1. |
| 3 | C-CFG-1 (512 MB download cap) | Budget wiring **resolved by FS-LOG-4**; cap value is a **user decision** | Neither the spec nor AT-LOG-04 fixes it beyond ≥200 MB. Recommendation: keep 512 MB until staging measures download time. |
| 4 | G-PLAT-11 (bundled vs per-surface tokens) | **Live validation**, then a decision | LIVE-VALIDATION-PLAN S2 needs a test org and dev App |
| 5 | D-10 (re-checks between surfaces; re-analysis after suspension) | **User decision** (product semantics) | Behaviour pinned by `test_github_contracts.py` and `test_adversarial.py` |
| 6 | D-11 (role provisioning) | **External resources** | A real database, credentials and a secret store; the template is ready (`scripts/db/provision_roles.sql`) |
| 7 | D-12 (retention interpretations) | **User decision** | DECISIONS D-12; implemented in migration 0008 |
| 8 | AWS signed-URL redaction in `marketplace.html` | **User decision** (evidence file) | SECURITY-AUDIT §1 |
| 9 | Benchmark D-5, B-04, B-12, A-05, E-01, B-02 | **User decision** (truth or policy); E-01 also needs T-605 | BENCHMARK-REVIEW-QUEUE |
| 10 | OpenAI reference, then T-605 | **External authorisation**, then key and evaluation | MODEL-ADAPTER §2a |
| 11 | T-1002 (platform, schedules, alert routing) | **External resources** and decisions | DEPLOYMENT-BLUEPRINT |
| 12 | Alert threshold 0.2 | **User decision** | `ops.py` labels it `provisional` |
| 13 | Live GitHub test org and dev App | **External authorisation** | LIVE-VALIDATION-PLAN preconditions |

No item above is resolved by this memo alone. Items 2 and 3 are resolved only for the parts that the cited canonical text fixes.
