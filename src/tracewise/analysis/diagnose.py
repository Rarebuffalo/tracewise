"""Evidence → bounded investigation → validated diagnosis with confidence (T-402..T-404 glue).

Must run inside the `collect_evidence()` block (the code source is only valid there). Retrieval is
already finished; this stage only reasons over the bundle and the read-only tool box.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from tracewise.analysis.collect import Evidence
from tracewise.investigate.loop import InvestigationLimits, investigate
from tracewise.investigate.prompt import Delimiter
from tracewise.investigate.provider import Provider
from tracewise.investigate.validate import ValidatedDiagnosis, finalize


def diagnose(
    ev: Evidence,
    provider: Provider,
    *,
    limits: InvestigationLimits | None = None,
    pr_number: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    delimiter: Delimiter | None = None,
) -> ValidatedDiagnosis:
    inv = investigate(ev, provider, limits, clock=clock, delimiter=delimiter) if ev.status == "ok" else None
    return finalize(ev, inv, pr_number=pr_number)
