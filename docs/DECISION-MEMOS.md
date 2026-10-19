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

**Remaining for review (open, minor):**
- The 512 MB download cap is not in the spec, and a slow 512 MB stream could take up a large share of the 10-minute deadline (30 s read timeout per chunk).
- Options:
  - keep 512 MB (AT-LOG-04 needs at least 200 MB);
  - lower it to, say, 256 MB, which is still ≥200 MB, to bound time;
  - make it configurable.
- Memory is bounded by the retention budget (5 × 2 MB per job), not by the download size. AT-LOG-04 (slow test) verifies peak RSS.
