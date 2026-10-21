"""T-903 dependency drift (FS-ATR-4, AT-ATR-08) from the B-05 and B-06 benchmark fixtures (read only) and synthetic
patches. Offline; nothing is published (ADR-13)."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

from tracewise.analysis.drift import (
    MAX_CHANGES,
    assess,
    dependency_file_kind,
    implicated_packages,
    installed_versions,
    manifest_changes,
)
from tracewise.context.trigger import ChangedFile, TriggerDiff

CASES = Path(__file__).resolve().parents[2] / "src" / "tracewise" / "bench" / "cases"
CAUSAL = re.compile(r"(?i)\bcaus|introduc|broke|responsible|fault of")
HEAD, BASE = "b" * 40, "a" * 40


def patch(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), n=3))


def diff(*files: ChangedFile, truncated: bool = False) -> TriggerDiff:
    return TriggerDiff(HEAD, BASE, tuple(files), truncated)


def b06_diff() -> TriggerDiff:
    before = (CASES / "B-06/repo/C0/requirements.txt").read_text()
    after = (CASES / "B-06/repo/C1/requirements.txt").read_text()
    return diff(ChangedFile("requirements.txt", "modified", 1, 1, None, patch(before, after)))


def test_at_atr_08_b06_manifest_bump_is_corroborated_by_the_conflict_report() -> None:
    log = (CASES / "B-06/handwritten/pip.log").read_text().splitlines()
    sig = assess(b06_diff(), log)
    assert sig.kind == "manifest_change" and sig.corroborated
    assert [(c.package, c.old, c.new) for c in sig.changes] == [("bar", "==1.4", "==2.0")]
    assert {"bar", "foo"} <= set(sig.implicated_packages)
    assert "bar" in sig.statement and not CAUSAL.search(sig.statement)


def test_at_atr_08_b05_upstream_drift_needs_install_output_to_be_corroborated() -> None:
    docs_only = diff(ChangedFile("docs/notes.md", "added", 3, 0, None, "@@ -0,0 +1 @@\n+notes"))
    log = (CASES / "B-05/logs/C1/101.log").read_text().splitlines()
    plain = assess(docs_only, log)
    assert plain.kind == "upstream_drift" and not plain.corroborated and "uncorroborated" in plain.statement
    sig = assess(
        docs_only,
        log,
        installed_now=["Successfully installed foo-2.0.0 pytest-8.3.3"],
        installed_last_green=["Successfully installed foo-1.9.3 pytest-8.3.3"],
    )
    assert sig.kind == "upstream_drift" and sig.corroborated
    assert [(c.package, c.old, c.new) for c in sig.changes] == [("foo", "1.9.3", "2.0.0")]
    assert not CAUSAL.search(sig.statement)


def test_same_installed_versions_are_not_drift() -> None:
    log = (CASES / "B-05/logs/C1/101.log").read_text().splitlines()
    same = ["Successfully installed foo-2.0.0"]
    sig = assess(diff(), log, installed_now=same, installed_last_green=same)
    assert sig.kind == "none" and not sig.corroborated


def test_a_manifest_change_the_error_does_not_name_is_reported_uncorroborated() -> None:
    p = patch("requests==2.31\n", "requests==2.32\n")
    sig = assess(diff(ChangedFile("requirements-dev.txt", "modified", 1, 1, None, p)), ["E   AssertionError: 1 != 2"])
    assert sig.kind == "manifest_change" and not sig.corroborated and sig.changes[0].package == "requests"


def test_unknown_truncated_and_unreadable_diffs_are_never_guessed() -> None:
    log = ["ModuleNotFoundError: No module named 'yaml'"]
    unknown = TriggerDiff(HEAD, None, known=False, reason="x")
    assert assess(unknown, log).kind == "unknown"
    assert assess(diff(truncated=True), log).kind == "unknown"
    nopatch = assess(diff(ChangedFile("poetry.lock", "modified", 900, 800, None, None)), log)
    assert nopatch.kind == "manifest_change" and not nopatch.corroborated and "could not be read" in nopatch.statement
    assert assess(diff(), ["all good"]).kind == "none"


def test_lock_files_toml_and_npm() -> None:
    toml = (
        '@@ -10,3 +10,3 @@\n [[package]]\n name = "foo"\n-version = "1.9.3"\n+version = "2.0.0"\n'
        ' [[package]]\n name = "Other_Pkg"\n-version = "1"\n+version = "1"\n'
    )
    changes, _ = manifest_changes(diff(ChangedFile("uv.lock", "modified", 1, 1, None, toml)))
    assert [(c.package, c.old, c.new) for c in changes] == [("foo", "1.9.3", "2.0.0")]
    npm = (
        '@@ -1,4 +1,4 @@\n     "node_modules/@scope/left-pad": {\n-      "version": "1.0.0",\n+      "version": "2.0.0",\n'
        '       "resolved": "x"\n'
    )
    changes, _ = manifest_changes(diff(ChangedFile("web/package-lock.json", "modified", 1, 1, None, npm)))
    assert [(c.package, c.old, c.new) for c in changes] == [("@scope/left-pad", "1.0.0", "2.0.0")]


def test_manifests_pyproject_package_json_go_mod_added_and_removed() -> None:
    py = patch('dependencies = [\n  "foo>=1.9",\n]\n', 'dependencies = [\n  "foo>=2",\n  "Bar_Baz[extra]~=1.0",\n]\n')
    js = patch(
        '  "dependencies": {\n    "react": "^18.2.0",\n    "lodash": "4.17.21"\n', '  "dependencies": {\n    "react": "^19.0.0"\n'
    )
    go = patch("require example.com/mod v1.2.3\n", "require example.com/mod v1.3.0\n")
    changes, _ = manifest_changes(
        diff(
            ChangedFile("pyproject.toml", "modified", 2, 1, None, py),
            ChangedFile("package.json", "modified", 1, 2, None, js),
            ChangedFile("go.mod", "modified", 1, 1, None, go),
        )
    )
    got = {(c.package, c.old, c.new) for c in changes}
    assert ("foo", ">=1.9", ">=2") in got and ("bar-baz", None, "~=1.0") in got
    assert ("react", "^18.2.0", "^19.0.0") in got and ("lodash", "4.17.21", None) in got
    assert ("example-com/mod", "v1.2.3", "v1.3.0") in got


def test_only_dependency_files_are_read() -> None:
    assert dependency_file_kind("src/requirements.py") is None
    assert dependency_file_kind("requirements/dev.txt") == "requirements"  # the directory layout
    assert dependency_file_kind("docs/requirements/notes.md") is None
    assert dependency_file_kind("ci/requirements-test.txt") == "requirements"
    assert dependency_file_kind("a/b/package.json") == "package_json"
    p = patch("foo==1\n", "foo==2\n")
    changes, _ = manifest_changes(diff(ChangedFile("notes/requirements.md", "modified", 1, 1, None, p)))
    assert changes == []


@pytest.mark.parametrize(
    "line",
    [
        "foo==1 ; rm -rf /",
        "-r other.txt",
        "# foo==2",
        "--index-url https://evil.invalid/simple",
        "../../etc/passwd==1",
        "x" * 300 + "==1",
    ],
)
def test_hostile_or_irrelevant_manifest_lines_never_produce_names_outside_the_pattern(line: str) -> None:
    changes, _ = manifest_changes(diff(ChangedFile("requirements.txt", "modified", 1, 0, None, f"@@ -0,0 +1 @@\n+{line}")))
    for c in changes:
        assert re.fullmatch(r"[a-z0-9@][a-z0-9._/@-]*", c.package) and len(c.package) <= 214
        assert c.new is None or (len(c.new) <= 64 and " " not in c.new)


def test_parsing_is_bounded() -> None:
    big = "@@ -0,0 +1 @@\n" + "".join(f"+pkg{i}=={i}\n" for i in range(10_000))
    changes, _ = manifest_changes(diff(ChangedFile("requirements.txt", "added", 10_000, 0, None, big)))
    assert len(changes) <= MAX_CHANGES


def test_implicated_and_installed_extraction() -> None:
    lines = [
        "E   AttributeError: module 'foo.sub' has no attribute 'bar'",
        "ImportError: cannot import name 'x' from 'Requests' (/x)",
        'npm error peer react@"^17" from some-lib@1.0.0',
        "Error: Cannot find module '@scope/thing'",
        "No matching distribution found for Not_Real",
    ]
    assert {"foo", "requests", "react", "@scope/thing", "not-real"} <= implicated_packages(lines)
    got = installed_versions(
        [
            "Successfully installed Foo_Bar-2.0.0 baz-1.0rc1 junk",
            " + uvpkg==3.1.4",
            "+ @scope/thing@1.2.3",
            "Successfully installed ../../x-1",
        ]
    )
    assert got == {"foo-bar": "2.0.0", "baz": "1.0rc1", "uvpkg": "3.1.4", "@scope/thing": "1.2.3"}


def test_statements_never_use_causal_wording() -> None:
    log = (CASES / "B-06/handwritten/pip.log").read_text().splitlines()
    sigs = [
        assess(b06_diff(), log),
        assess(diff(), log),
        assess(diff(), log, installed_now=["+ foo==2"], installed_last_green=["+ foo==1"]),
        assess(TriggerDiff(HEAD, None, known=False), log),
    ]
    assert all(not CAUSAL.search(s.statement) for s in sigs)


# ------------------------------------------------------------------ ambiguous, conflicting, insufficient evidence


def test_ambiguous_error_naming_several_packages_is_corroborated_only_by_the_changed_one() -> None:
    p = patch("alpha==1\nbeta==1\n", "alpha==1\nbeta==2\n")
    log = ["ModuleNotFoundError: No module named 'alpha'", "ImportError: cannot import name 'x' from 'beta'"]
    sig = assess(diff(ChangedFile("requirements.txt", "modified", 1, 1, None, p)), log)
    assert sig.corroborated and [c.package for c in sig.changes] == ["beta"] and "alpha" not in sig.statement


def test_conflicting_evidence_a_manifest_change_wins_over_installed_versions() -> None:
    # The push changed a declaration the error names, and the install output also moved: one claim, the manifest.
    p = patch("foo==1\n", "foo==2\n")
    sig = assess(
        diff(ChangedFile("requirements.txt", "modified", 1, 1, None, p)),
        ["ModuleNotFoundError: No module named 'foo'"],
        installed_now=["+ foo==2"],
        installed_last_green=["+ foo==1"],
    )
    assert sig.kind == "manifest_change" and sig.corroborated


@pytest.mark.parametrize(
    ("now", "before"),
    [
        (["+ foo==2"], None),
        (None, ["+ foo==1"]),
        ([], []),
        (["+ other==2"], ["+ other==1"]),  # versions moved, but not for the named package
        (["+ foo==2"], ["no install output here"]),
    ],
    ids=["no-last-green", "no-current", "both-empty", "other-package", "one-side-unlisted"],
)
def test_insufficient_install_evidence_is_never_corroborated(now: list[str] | None, before: list[str] | None) -> None:
    sig = assess(
        diff(), ["E   AttributeError: module 'foo' has no attribute 'bar'"], installed_now=now, installed_last_green=before
    )
    assert not sig.corroborated and sig.kind in ("upstream_drift", "none")


def test_missing_logs_and_empty_diff_say_nothing() -> None:
    sig = assess(diff(), [])
    assert (sig.kind, sig.corroborated, sig.implicated_packages) == ("none", False, ())


def test_an_error_naming_only_a_function_is_not_attributed_to_a_package() -> None:
    # A known recall limit (benchmark B-17): a signature change surfaces as a TypeError naming the function only.
    sig = assess(diff(), ["E   TypeError: parse() got an unexpected keyword argument 'strict'"])
    assert sig.kind == "none" and not sig.corroborated
