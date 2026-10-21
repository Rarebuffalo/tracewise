"""scripts/check_docs.py path checks are hermetic: a documented path must be part of the repository, not merely present
on this machine because it is git-ignored (the local-only quarantined evidence, D-3). Such a path failed only in CI
(fresh checkout) while passing locally; it now fails locally too. Ordinary missing paths and links still fail, and a
plain-text mention of a local-only directory is not a path reference. A throwaway local git repository; no network."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_docs.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607 - local only
    (tmp_path / ".gitignore").write_text("research/local/evidence/\nresearch/tracked-but-ignored.md\n")
    (tmp_path / "research" / "local" / "evidence").mkdir(parents=True)
    (tmp_path / "research" / "local" / "evidence" / "capture.json").write_text("{}")  # exists only locally
    (tmp_path / "research" / "notes.md").write_text("ok")
    (tmp_path / "research" / "tracked-but-ignored.md").write_text("ok")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "research/tracked-but-ignored.md"], check=True)  # noqa: S603, S607
    (tmp_path / "docs").mkdir()
    return tmp_path


def run(mod: ModuleType, repo: Path, body: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    doc = repo / "docs" / "GUIDE.md"
    doc.write_text(body)
    errors: list[str] = []
    monkeypatch.setattr(mod, "ROOT", repo)
    monkeypatch.setattr(mod, "ACTIVE", [doc])
    monkeypatch.setattr(mod, "errors", errors)
    monkeypatch.setattr(mod, "notes", [])
    mod.check_links()
    return errors


def test_a_backticked_path_that_exists_only_because_it_is_git_ignored_fails_as_in_ci(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = load()
    errs = run(mod, repo, "Do not touch `research/local/evidence/`.\n", monkeypatch)
    assert errs == ["[paths] docs/GUIDE.md -> research/local/evidence/ (missing or git-ignored)"]
    errs = run(mod, repo, "See [capture](../research/local/evidence/capture.json).\n", monkeypatch)
    assert len(errs) == 1 and errs[0].startswith("[links]")


def test_the_same_directory_named_in_plain_text_is_not_a_path_reference(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load()
    body = "Do not touch the quarantined directory research/local/evidence/ (local only).\n"
    assert run(mod, repo, body, monkeypatch) == []


def test_ordinary_missing_paths_and_links_still_fail_and_present_ones_pass(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load()
    body = "`research/notes.md` and `research/gone.md`; [ok](../research/notes.md) and [bad](../research/missing.md).\n"
    errs = run(mod, repo, body, monkeypatch)
    assert sorted(errs) == [
        "[links] docs/GUIDE.md -> ../research/missing.md (missing or git-ignored)",
        "[paths] docs/GUIDE.md -> research/gone.md (missing or git-ignored)",
    ]


def test_a_tracked_file_matching_an_ignore_pattern_is_part_of_the_repository(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load()
    assert run(mod, repo, "See `research/tracked-but-ignored.md`.\n", monkeypatch) == []


def test_outside_a_git_checkout_only_existence_is_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load()
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "notes.md").write_text("ok")
    (tmp_path / "docs").mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))  # never discover an enclosing repository
    assert run(mod, tmp_path, "`research/notes.md` and `research/gone.md`\n", monkeypatch) == [
        "[paths] docs/GUIDE.md -> research/gone.md (missing or git-ignored)"
    ]
