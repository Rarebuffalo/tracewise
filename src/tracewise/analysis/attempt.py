"""One deadline for a whole analysis attempt (C-4).

The job's durable `deadline_at` (FS-ERR-2: 10 minutes from the first claim) is the only clock that spans an attempt.
`AttemptDeadline` is derived from it **once**, when the attempt starts, and passed down; no stage starts a fresh
timeout of its own beyond what is left:

    claim ─▶ collect (log streams stop at the deadline; git fetch ≤ remaining) ─▶ investigate (timeout = remaining)
          ─▶ validate + render (local, size-bounded) ─▶ persist ─▶ publish (the reserve below)

Publication is not cut mid-way: a POST cut after sending is an uncertain write, which the reconcile logic handles
only between attempts. Instead the work stages stop `PUBLISH_RESERVE_S` before the job deadline, so the report (or
an honest "incomplete" result) can still be published within it. A stage that runs out of time records that fact;
it never turns into a complete-looking diagnosis.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from tracewise.jobs.queue import JOB_DEADLINE_S

# Kept back from the work stages for persisting and publishing (three surfaces, each bounded by client timeouts).
PUBLISH_RESERVE_S = 60.0
# Below this, an investigation cannot do one useful provider step with tools; it is skipped and the result says why.
# O-2: raised from 10 s (approved for this milestone): a tool-using step regularly needs several seconds.
MIN_INVESTIGATION_S = 20.0


@dataclass(frozen=True)
class AttemptDeadline:
    """A monotonic instant by which the attempt's work stages must stop. Immutable: it can only be read."""

    at: float
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)

    @classmethod
    def for_job(
        cls,
        deadline_at: datetime | None,
        now: datetime,
        *,
        clock: Callable[[], float] = time.monotonic,
        reserve_s: float = PUBLISH_RESERVE_S,
    ) -> AttemptDeadline:
        """From the job's wall-clock deadline, converted once to the monotonic clock (immune to clock steps later)."""
        left = (deadline_at - now).total_seconds() if deadline_at is not None else float(JOB_DEADLINE_S)
        return cls(clock() + max(0.0, left - reserve_s), clock)

    @classmethod
    def for_publication(
        cls, deadline_at: datetime | None, now: datetime, *, clock: Callable[[], float] = time.monotonic
    ) -> AttemptDeadline:
        """O-2: the deadline for publishing: the job deadline itself (the work stages stop `PUBLISH_RESERVE_S` before
        it). A notice-only attempt claimed after the job deadline (it does no investigation) gets one reserve's worth
        from now, so the user is still told (FS-ERR-1) within a bound."""
        left = (deadline_at - now).total_seconds() if deadline_at is not None else float(JOB_DEADLINE_S)
        return cls(clock() + (left if left > 0 else PUBLISH_RESERVE_S), clock)

    def remaining(self) -> float:
        return max(0.0, self.at - self.clock())

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def cap(self, seconds: float) -> float:
        """A stage's own limit, never beyond what the attempt has left."""
        return min(seconds, self.remaining())
