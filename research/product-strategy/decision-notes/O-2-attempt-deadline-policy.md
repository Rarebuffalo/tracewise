# O-2: attempt deadline policy

- **Date:** 2026-11-01 (fourth batch)
- **Status:** Proposal for owner decision. **Update 2026-11-02:** the §2 fix is implemented (per-request deadline for every
  GitHub call; ARCHITECTURE "Attempt deadline for GitHub requests"), and the investigation minimum is 20 s. The 600 s /
  60 s / 3-attempt values are unchanged and still need the owner's confirmation (§4 question 1).
- **Basis:** `src/tracewise/analysis/attempt.py`, `jobs/queue.py`, `github/client.py`, `context/gitfetch.py`,
  `investigate/http_adapter.py`, `config.py`; tests `tests/context/test_attempt_deadline.py`,
  `tests/db/test_phase50_reliability.py`, `tests/db/test_recovery_semantics.py`.

## 1. What is implemented

One durable clock spans a job: `job.deadline_at` = first claim + `JOB_DEADLINE_S` (600 s). Each attempt converts it
**once** to a monotonic `AttemptDeadline` = what is left − `PUBLISH_RESERVE_S` (60 s), and passes it down.

| Budget | Value today | Bounded by the attempt deadline? | Where |
|---|---|---|---|
| Job (all attempts) | 600 s from first claim | — (it *is* the clock) | `queue.JOB_DEADLINE_S` |
| Publication reserve | 60 s kept back from the work stages | — | `attempt.PUBLISH_RESERVE_S` |
| Minimum to start an investigation | 10 s | yes: below it, no model call (`attempt_deadline_exhausted`) | `attempt.MIN_INVESTIGATION_S` |
| Log collection | stream stops at the deadline; per-download cap 300 s (half the job) and 512 MiB | **yes** (`_LogStream`) | `collect.py`, `client.Limits` |
| Git fetch | 60 s, capped to what is left; skipped below 1 s | **yes** (`deadline.cap`) | `gitfetch.fetch_timeout_s` |
| Investigation (all provider steps and tools) | 120 s, capped to what is left | **yes** (`deadline.cap`) | `config.investigation_timeout_s` |
| One provider request | the investigation's remaining time; ≤ `max_retries` retries inside it | **yes** (`request.timeout_s`) | `http_adapter.py:187,227` |
| Transient code-read retry | one 1 s pause, skipped when less time is left | **yes** (`source.time_left`) | `source.py` |
| One GitHub request (tool read, validation read, publication) | 30 s read, 5 s connect, ≤3 inline retries, inline waits ≤10 s | **no**: client limits only | `client.Limits` |
| Lease | 120 s, renewed every 40 s | independent (crash detection) | `queue.DEFAULT_LEASE_S` |
| Retry budget | 3 attempts; backoff 30 s × 4^(n−1), ≤300 s, +20 % jitter; a retry is scheduled only if it ends before the deadline | yes (`retry_fits`) | `queue.py` |

## 2. Gaps found while reviewing

1. **GitHub requests are not capped by the attempt deadline.** A single read can take about 30 s × 4 attempts plus
   inline waits, which is over two minutes in the worst case. Tool reads run inside the investigation timeout, but that
   timeout is only checked between steps, not inside one read. Validation reads and the three publication surfaces
   have no deadline check at all. The 60 s reserve covers typical publication (three requests), not the worst case.
   The job deadline is not enforced mid-request either: a slow attempt overruns it and the job then ends `dead`
   (`deadline exceeded`) instead of being cut cleanly.
2. **The lease (120 s) is shorter than one worst-case GitHub request chain.** The heartbeat thread keeps the lease
   alive during it, so this is safe. Without heartbeats (a stalled process), the reaper takes over after 120 s; the
   fencing (0012) makes that safe.

**Proposed fix (not implemented; small, and needs owner sign-off):** give `RepoClient` an optional
`deadline: AttemptDeadline`. Each request would use `timeout = min(read_timeout, remaining)`, and inline retries would
stop when time is short (a `GitHubRetryable` then follows the existing transient path). Publication would use its own
deadline: the job deadline itself, not the reserve-reduced one.

## 3. Recommended policy

| Item | Recommended default | Owner approval needed? | Trade-off |
|---|---|---|---|
| Maximum job duration | **600 s** (keep) | Yes: it is the FS-ERR-2 user promise | Shorter: more "could not complete" on large logs. Longer: slower feedback and longer worker occupancy |
| Publication reserve | **60 s** (keep) and enforce it with §2 fix | No (engineering) | Larger: less investigation time. Smaller: risk of overrunning the deadline while publishing |
| Minimum to start investigating | **10 s** → **20 s** | No | One real provider step with tools takes several seconds; 10 s mostly yields `budget_exhausted` with spend |
| Log collection | stream to the deadline; 300 s per download (keep) | No | — |
| Git fetch | 60 s capped (keep) | No | — |
| Investigation | 120 s capped (keep; the settings ceiling) | Yes if raised: cost per analysis | Longer: more tool steps and tokens |
| One provider request | remaining investigation time (keep) | No | — |
| Validation | part of the attempt; its GitHub reads to be capped by §2 | No | — |
| Retry budget | 3 attempts, backoff as today (keep) | Yes: spend on repeated model calls | More attempts: more recovery, more model spend |

**Invariant to keep (tested today for log, fetch, investigation):** every stage receives `deadline.cap(own_limit)`
and none starts a fresh full timeout. §2 extends that invariant to GitHub requests.

## 4. Owner questions

1. Confirm 600 s as the job deadline (FS-ERR-2) and 3 attempts.
2. Approve the §2 fix (per-request deadline for GitHub calls) as the next reliability change.
3. Raise the minimum investigation start from 10 s to 20 s?
