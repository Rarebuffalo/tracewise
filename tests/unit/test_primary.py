"""AT-DX-02 (cascades), AT-DX-03 (siblings), AT-DX-07 (misleading tail), AT-DX-16 (independent primaries)."""

from tests.helpers import build_job, fixture
from tracewise.prepass.primary import run_prepass


def test_dx03_b02_siblings() -> None:
    res = run_prepass([build_job(1, "Tests (Python 3.11)", "Run pytest", "pytest --tb=short -v", fixture("pytest_b02.out"))])
    (g,) = res.primaries
    assert g.primary.test == "tests/test_pricing.py::test_total_single"
    assert len(g.members) - 1 == 3
    assert g.sibling_names == [
        "tests/test_pricing.py::test_total_two",
        "tests/test_pricing.py::test_total_mixed",
        "tests/test_pricing.py::test_total_large",
    ]
    assert res.excerpt(g.primary) == "E   assert 0.21 == 1.21"
    assert res.failed[0].command == "pytest --tb=short -v"


def test_dx02_b12_tsc_primary_jest_cascades() -> None:
    res = run_prepass(
        [
            build_job(1, "typecheck", "Run tsc", "npx tsc --noEmit", fixture("tsc_b12.handwritten.out")),
            build_job(2, "test", "Run jest", "npx jest", fixture("jest_b12.handwritten.out")),
        ]
    )
    (g,) = res.primaries
    assert g.primary.tool == "tsc" and g.primary.code == "TS2307"
    assert len(res.cascades) == 40


def test_dx02_cascade_even_when_compile_job_listed_later() -> None:
    res = run_prepass(
        [
            build_job(2, "test", "Run jest", "npx jest", fixture("jest_b12.handwritten.out")),
            build_job(1, "typecheck", "Run tsc", "npx tsc --noEmit", fixture("tsc_b12.handwritten.out")),
        ]
    )
    assert [g.primary.tool for g in res.primaries] == ["tsc"]


def test_dx07_a04_misleading_tail() -> None:
    out = "\n".join(
        [
            "Collecting foo==9.9",
            "ERROR: Could not find a version that satisfies the requirement foo==9.9 (from versions: 1.0, 1.1)",
            "ERROR: No matching distribution found for foo==9.9",
            "Traceback (most recent call last):",
            '  File "/home/runner/work/a/a/app/main.py", line 1, in <module>',
            "ModuleNotFoundError: No module named 'foo'",
        ]
    )
    res = run_prepass([build_job(1, "test", "Install and test", "pip install -r requirements.txt && python -m app", out)])
    assert res.primaries[0].primary.kind == "install"
    assert "Could not find a version" in res.primaries[0].primary.message
    assert [c.module for c in res.cascades] == ["foo"]
    # Phase 50 (A-04): pip's "No matching distribution" line is the same failure, not a second primary.
    first = res.primaries[0].primary
    assert len(res.primaries) == 1 and first.span == (first.log_line, first.log_line + 1)


def test_a04_distinct_pip_requirements_stay_separate() -> None:
    out = "\n".join(
        [
            "ERROR: Could not find a version that satisfies the requirement foo==9.9 (from versions: 1.0)",
            "ERROR: No matching distribution found for bar==1.0",  # a different requirement: not folded
        ]
    )
    res = run_prepass([build_job(1, "test", "Install", "pip install -r requirements.txt", out)])
    assert len(res.primaries) == 2


def test_dx16_b11_two_independent_primaries() -> None:
    tests_out = "\n".join(
        [
            "=================================== FAILURES ===================================",
            "_________________________________ test_stamp __________________________________",
            "tests/test_stamp.py:4: in test_stamp",
            "    stamp()",
            "E   DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal",
            "=========================== short test summary info ============================",
            "FAILED tests/test_stamp.py::test_stamp - DeprecationWarning: datetime.datetime.utcnow() is deprecated",
        ]
    )
    res = run_prepass(
        [
            build_job(1, "test (3.12)", "Run pytest", "pytest -W error::DeprecationWarning", tests_out),
            build_job(2, "lint", "Run ruff", "ruff check .", fixture("ruff_b10.out")),
        ]
    )
    assert [(g.primary.tool, g.primary.job_id) for g in res.primaries] == [("pytest", 1), ("ruff", 2)]
    assert res.primaries[0].primary.code == "DeprecationWarning"


def test_exit_code_only_when_nothing_else() -> None:
    res = run_prepass([build_job(1, "build", "Run make", "make", "compiling...\nsomething odd happened")])
    (g,) = res.primaries
    assert g.primary.kind == "exit"
    res2 = run_prepass([build_job(1, "lint", "Run ruff", "ruff check .", fixture("ruff_b10.out"))])
    assert all(g.primary.kind != "exit" for g in res2.primaries)


def test_b10_two_locations() -> None:
    out = fixture("ruff_b10.out") + "\n" + fixture("mypy_b10.out")
    res = run_prepass([build_job(1, "lint", "Run checks", "ruff check . && mypy .", out)])
    assert [(g.primary.path, g.primary.line) for g in res.primaries] == [("coffee_shop/greet.py", 1), ("coffee_shop/greet.py", 5)]
