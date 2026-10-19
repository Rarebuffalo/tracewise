"""Phase 51: pin the provisional failure-rate rule so it cannot change without a deliberate decision.

The 0.2 threshold and the 10-job minimum are provisional (OWNER-DECISION-SHEET item 6). These tests change nothing:
they make any change visible, and they fill in the cases next to the boundary that the main test does not cover.
"""

from __future__ import annotations

from tests.db.test_observability import NOW, _job
from tracewise import ops


def test_the_default_rule_is_still_the_provisional_one() -> None:
    rule = ops.AlertRule()
    assert (rule.threshold, rule.min_sample) == (0.2, 10)


def test_just_below_the_threshold_is_ok(pool, owner) -> None:  # type: ignore[no-untyped-def]
    for _ in range(9):
        _job(owner, "succeeded", outcome="diagnosed", age_min=5)
    _job(owner, "dead", age_min=5)
    res = ops.failure_rate(pool, now=NOW)
    assert (res["rate"], res["state"]) == (0.1, "ok")


def test_all_failed_but_below_the_minimum_sample_is_not_firing(pool, owner) -> None:  # type: ignore[no-untyped-def]
    for _ in range(9):
        _job(owner, "dead", age_min=5)
    res = ops.failure_rate(pool, now=NOW)
    assert (res["finished"], res["state"]) == (9, "insufficient_data")  # reported, never silently "ok"
