#!/usr/bin/env python3
"""Regenerate Python extractor golden fixtures from real local tool runs (offline).

Builds a throwaway coffee-shop replica (B-02 defect + B-10 lint/type errors) in a temp
dir, runs pytest/ruff/mypy from this project's venv, and writes their raw output to
tests/fixtures/logs/*.out. No network.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "logs"
BIN = Path(sys.executable).parent

PRICING = (
    '''"""Pricing for the coffee shop."""
TAX_RATE = 0.21


def line_total(price: float, qty: int) -> float:
    return price * qty


def subtotal(items: list[tuple[float, int]]) -> float:
    return sum(line_total(p, q) for p, q in items)


def total(items: list[tuple[float, int]]) -> float:
    subtotal_ = subtotal(items)
'''
    + "\n" * 25
    + """    # B-02 defect (line 41): should be subtotal_ * (1 + TAX_RATE)
    return round(subtotal_ * TAX_RATE, 2)
"""
)

TESTS = """from coffee_shop.pricing import total


def test_total_single():
    assert total([(1.0, 1)]) == 1.21


def test_total_two():
    assert total([(1.0, 2)]) == 2.42


def test_total_mixed():
    assert total([(1.0, 1), (0.5, 2)]) == 2.42


def test_total_large():
    assert total([(10.0, 1)]) == 12.1
"""

LINT = """import os


def greet(name: str) -> int:
    return "hello " + name
"""


RUNNER_ROOT = "/home/runner/work/coffee/coffee"
RUNNER_PY = "/opt/hostedtoolcache/Python/3.12.7/x64/bin/python"


def run(cmd: list[str], cwd: Path) -> str:
    """Run a tool; rewrite local paths to GitHub-runner paths so no host details are stored."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    out = (p.stdout + p.stderr).replace(str(Path(sys.executable)), RUNNER_PY)
    out = out.replace(str(cwd.resolve()), RUNNER_ROOT).replace(str(cwd), RUNNER_ROOT)
    return out.replace(str(Path.home()), "/home/runner")


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "coffee_shop").mkdir()
        (root / "coffee_shop" / "__init__.py").write_text("")
        (root / "coffee_shop" / "pricing.py").write_text(PRICING)
        (root / "coffee_shop" / "greet.py").write_text(LINT)
        (root / "tests").mkdir()
        (root / "tests" / "test_pricing.py").write_text(TESTS)
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\npythonpath = ['.']\n")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "pytest_b02.out").write_text(
            run([str(BIN / "pytest"), "--tb=short", "-v", "-p", "no:cacheprovider", "--color=yes", "tests"], root)
        )
        (OUT / "ruff_b10.out").write_text(
            run([str(BIN / "ruff"), "check", "--no-cache", "--output-format=concise", "--select", "F", "coffee_shop"], root)
        )
        (OUT / "ruff_full_b10.out").write_text(
            run([str(BIN / "ruff"), "check", "--no-cache", "--output-format=full", "--select", "F", "coffee_shop"], root)
        )
        (OUT / "mypy_b10.out").write_text(
            run(
                [str(BIN / "mypy"), "--no-incremental", "--cache-dir=/dev/null", "--show-error-codes", "coffee_shop/greet.py"],
                root,
            )
        )
        tb = run([sys.executable, "-c", "import coffee_shop.pricing as p; p.total(None)"], root)
        (OUT / "traceback.out").write_text(tb)
    print("wrote", sorted(p.name for p in OUT.glob("*.out")))


if __name__ == "__main__":
    main()
