"""Evidence → bounded investigation → validated diagnosis with confidence (T-402..T-404 glue).

Must run inside the `collect_evidence()` block (the code source is only valid there). Retrieval is
already finished; this stage only reasons over the bundle and the read-only tool box.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable

from tracewise.analysis.attempt import MIN_INVESTIGATION_S, AttemptDeadline
from tracewise.analysis.collect import Evidence
from tracewise.investigate.loop import InvestigationLimits, investigate
from tracewise.investigate.prompt import Delimiter
from tracewise.investigate.provider import Provider
from tracewise.investigate.replay import ReplayContext
from tracewise.investigate.validate import SOURCE_UNAVAILABLE, ValidatedDiagnosis, finalize


def diagnose(
    ev: Evidence,
    provider: Provider,
    *,
    limits: InvestigationLimits | None = None,
    pr_number: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    delimiter: Delimiter | None = None,
    deadline: AttemptDeadline | None = None,
    replay_context: ReplayContext | None = None,
) -> ValidatedDiagnosis:
    """`deadline` (C-4): the attempt's single deadline. The investigation gets what is left of it, never a fresh full
    timeout; with too little left it is not started, and the result says so (never a guessed diagnosis)."""
    if ev.status != "ok":
        return finalize(ev, None, pr_number=pr_number)
    if not ev.source.available and ev.source.transient_failure:
        # I-3: the code could not be reached this attempt (a transient GitHub failure). No model call on a bundle
        # known to be incomplete; the result says the source was unavailable, and the job retries.
        return finalize(ev, None, pr_number=pr_number, not_run_reason=SOURCE_UNAVAILABLE)
    lim = limits or InvestigationLimits()
    if deadline is not None:
        if deadline.remaining() < MIN_INVESTIGATION_S:
            return finalize(ev, None, pr_number=pr_number, not_run_reason="attempt_deadline_exhausted")
        lim = dataclasses.replace(lim, timeout_s=deadline.cap(lim.timeout_s))
    inv = investigate(ev, provider, lim, clock=clock, delimiter=delimiter, replay_context=replay_context)
    return finalize(ev, inv, pr_number=pr_number)
