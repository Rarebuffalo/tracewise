"""Phase 57 (F4): the diff parser treated removed/added lines whose content starts with `--`/`++` as context, so the
changed line numbers used by the confidence rules were wrong. Found by an offline audit, reproduced first."""

from __future__ import annotations

from tracewise.context.trigger import ChangedFile, TriggerDiff
from tracewise.investigate.confidence import changed_lines

# ------------------------------------------------------------------ F4


def diff(patch: str) -> TriggerDiff:
    return TriggerDiff("a" * 40, "b" * 40, (ChangedFile("f.txt", "modified", patch=patch),))


def test_f4_removed_and_added_lines_starting_with_dashes_or_pluses_count_as_changes() -> None:
    assert changed_lines(diff("@@ -1,3 +1,3 @@\n----\n+name: ci\n on: push\n jobs:"))["f.txt"] == {1}
    assert changed_lines(diff("@@ -1,2 +1,2 @@\n x = 1\n-y\n+++count;"))["f.txt"] == {2}


def test_f4_file_headers_before_the_first_hunk_are_still_ignored() -> None:
    assert changed_lines(diff("--- a/f.txt\n+++ b/f.txt\n@@ -1,1 +1,1 @@\n-a\n+b"))["f.txt"] == {1}
