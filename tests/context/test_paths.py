"""FS-CTX-5 path rules, tested directly."""

import pytest

from tracewise.context.paths import UnsafePath, resolve_link, validate_owner_repo, validate_repo_path, validate_sha


@pytest.mark.parametrize("ok", ["a.py", "src/a.py", "a b/c%2e%2e.py", "ünï/code.py", ".github/workflows/ci.yml", "x/.gitignore"])
def test_valid_paths(ok) -> None:  # type: ignore[no-untyped-def]
    assert validate_repo_path(ok) == ok


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/",
        "/a",
        "a/../b",
        "..",
        ".",
        "./a",
        "a//b",
        "a/",
        "a\\b",
        ".git",
        "x/.GIT/config",
        "a\x00b",
        "a\nb",
        "a​b",
        "a‮b",
        "café",
        "a" * 1025,
    ],
)
def test_invalid_paths(bad) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(UnsafePath):
        validate_repo_path(bad)


def test_root_only_when_allowed() -> None:
    assert validate_repo_path("", allow_root=True) == validate_repo_path(".", allow_root=True) == ""
    assert validate_repo_path("src/", allow_root=True) == "src"
    with pytest.raises(UnsafePath):
        validate_repo_path("/", allow_root=True)


@pytest.mark.parametrize(
    ("link", "target", "want"),
    [
        ("a/l", "b.py", "a/b.py"),
        ("a/l", "../c.py", "c.py"),
        ("l", "a/./b.py", "a/b.py"),
        ("l", "/etc/passwd", None),
        ("a/l", "../../x", None),
        ("l", "..", None),
        ("l", "", None),
        ("l", "a\\b", None),
        ("l", ".git/config", None),
    ],
)
def test_resolve_link(link, target, want) -> None:  # type: ignore[no-untyped-def]
    assert resolve_link(link, target) == want


def test_repo_and_sha() -> None:
    assert validate_owner_repo("pallets/flask") == ("pallets", "flask")
    for bad in ("pallets", "a/b/c", "-a/b", "a/..", "a/b.git", "a/b c", "a" * 40 + "/b"):
        with pytest.raises(UnsafePath):
            validate_owner_repo(bad)
    assert validate_sha("a" * 40)
    for bad in ("a" * 39, "A" * 40, "z" * 40):
        with pytest.raises(UnsafePath):
            validate_sha(bad)
