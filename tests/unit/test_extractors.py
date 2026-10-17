"""AT-LOG-05: each extractor passes its golden fixtures.

Python fixtures are real tool output (scripts/gen_python_fixtures.py). TypeScript fixtures
are hand-written from the tools' documented formats (`*.handwritten.out`).
"""

from tests.helpers import fixture
from tracewise.prepass.extractors import generic, python, typescript
from tracewise.prepass.sanitize import clean


def lines(name: str) -> list[tuple[int, str]]:
    return [(i, clean(t)) for i, t in enumerate(fixture(name).splitlines(), 1)]


def test_pytest_b02() -> None:
    cs = python.pytest(1, lines("pytest_b02.out"))
    assert [c.test for c in cs] == [
        "tests/test_pricing.py::test_total_single",
        "tests/test_pricing.py::test_total_two",
        "tests/test_pricing.py::test_total_mixed",
        "tests/test_pricing.py::test_total_large",
    ]
    first = cs[0]
    assert first.message == "assert 0.21 == 1.21"
    assert (first.path, first.line, first.code, first.kind) == ("tests/test_pricing.py", 5, "AssertionError", "test")


def test_traceback_last_own_frame() -> None:
    (c,) = python.traceback(1, lines("traceback.out"))
    assert c.code == "TypeError" and c.message.startswith("TypeError: 'NoneType' object is not iterable")
    assert (c.path, c.line) == ("coffee_shop/pricing.py", 10)


def test_traceback_missing_module_and_libs_skipped() -> None:
    raw = [
        "Traceback (most recent call last):",
        '  File "/home/runner/work/a/a/app/main.py", line 3, in <module>',
        "    import yaml",
        '  File "/opt/hostedtoolcache/Python/3.12.7/x64/lib/python3.12/importlib/__init__.py", line 90, in import_module',
        "ModuleNotFoundError: No module named 'yaml'",
    ]
    (c,) = python.traceback(1, list(enumerate(raw, 1)))
    assert (c.kind, c.module, c.path, c.line) == ("missing_module", "yaml", "app/main.py", 3)
    assert c.span == (1, 5)


def test_ruff_concise_and_full() -> None:
    (a,) = python.ruff(1, lines("ruff_b10.out"))
    (b,) = python.ruff(1, lines("ruff_full_b10.out"))
    for c in (a, b):
        assert (c.code, c.path, c.line, c.message) == ("F401", "coffee_shop/greet.py", 1, "`os` imported but unused")


def test_mypy() -> None:
    (c,) = python.mypy(1, lines("mypy_b10.out"))
    assert (c.path, c.line, c.code) == ("coffee_shop/greet.py", 5, "return-value")
    assert c.message.startswith("Incompatible return value type")


def test_tsc_both_formats() -> None:
    cs = typescript.tsc(1, lines("tsc_b01.handwritten.out"))
    assert [(c.path, c.line, c.code) for c in cs] == [("src/app.ts", 3, "TS2305"), ("src/cart.ts", 12, "TS2305")]
    (m,) = typescript.tsc(1, lines("tsc_b12.handwritten.out"))
    assert m.module == "util" and m.kind == "compile"


def test_jest_missing_module_and_snapshot() -> None:
    cs = typescript.jest(1, lines("jest_b12.handwritten.out"))
    assert len(cs) == 40 and all(c.kind == "missing_module" and c.module == "util" for c in cs)
    (snap,) = typescript.jest(1, lines("jest_b03.handwritten.out"))
    assert snap.code == "snapshot" and snap.test == "src/Button.test.tsx › Button › renders label"
    assert (snap.path, snap.line) == ("src/Button.test.tsx", 11)


def test_vitest() -> None:
    (c,) = typescript.vitest(1, lines("vitest.handwritten.out"))
    assert c.test == "src/sum.test.ts > sum > adds numbers"
    assert c.message == "AssertionError: expected 4 to be 5 // Object.is equality"
    assert (c.path, c.line) == ("src/sum.test.ts", 6)


def test_eslint_errors_only() -> None:
    cs = typescript.eslint(1, lines("eslint.handwritten.out"))
    assert [(c.path, c.line, c.code) for c in cs] == [
        ("src/app.ts", 3, "@typescript-eslint/no-unused-vars"),
        ("src/cart.ts", 22, "eqeqeq"),
    ]


def test_generic() -> None:
    raw = [
        "ERROR: Could not find a version that satisfies the requirement foo==9.9 (from versions: 1.0)",
        "npm error code ERESOLVE",
        "##[error]The job running on runner GitHub Actions 2 has exceeded the maximum execution time of 10 minutes.",
        "##[error]Process completed with exit code 137.",
        "Error: connect ECONNREFUSED 127.0.0.1:5432",
    ]
    cs = generic.generic(1, list(enumerate(raw, 1)))
    assert [(c.kind, c.code) for c in cs] == [
        ("install", "install"),
        ("install", "install"),
        ("generic", "timeout"),
        ("exit", "exit 137"),
        ("generic", None),
    ]
