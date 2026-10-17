"""AT-SEC-15: adversarial lines and a ReDoS corpus never raise and stay fast."""

import random
import time

import pytest

from tracewise.prepass.extractors import generic
from tracewise.prepass.extractors.base import Candidate
from tracewise.prepass.primary import TOOL_EXTRACTORS
from tracewise.prepass.sanitize import clean

REDOS = [
    "a" * 50_000 + "!",
    "_" * 5000 + " test " + "_" * 5000 + "x",
    "E" + " " * 50_000,
    "x.py:" + "1" * 10_000 + ":",
    'File "' + "a" * 20_000,
    "src/" + "a/" * 5000 + "x.ts(1,1): error TS",
    "FAIL " + "a/" * 5000 + ".ts > " + "> " * 5000,
    "  1:1  error  " + "a " * 20_000,
    "##[error]" + "\x1b[" * 10_000,
    "\x1b]" + "8;;" * 10_000,
    "-----BEGIN PRIVATE KEY-----" + "A" * 50_000,
    "password=" + "=" * 50_000,
    "postgres://" + "a:" * 10_000 + "@",
    "eyJ" + "a" * 10_000 + "." + "b" * 10_000,
    "Traceback (most recent call last):",
]


def corpus(n: int, seed: int = 15) -> list[str]:
    rnd = random.Random(seed)
    alphabet = "aZ09_./\\:()[]{}'\" \t-=>›❯●E#\x1b\r\x85\x9b"
    out = list(REDOS)
    while len(out) < n:
        out.append("".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 400))))
    return out


EXTRACTORS = [*TOOL_EXTRACTORS, generic.generic]


@pytest.mark.parametrize("ex", EXTRACTORS, ids=lambda f: f.__module__.rsplit(".", 1)[-1] + "." + f.__name__)
def test_adversarial_10k_lines(ex) -> None:  # type: ignore[no-untyped-def]
    lines = [(i, clean(t)) for i, t in enumerate(corpus(10_000), 1)]
    t0 = time.perf_counter()
    out = ex(1, lines)
    assert time.perf_counter() - t0 < 2.0
    assert all(isinstance(c, Candidate) for c in out)


@pytest.mark.slow
@pytest.mark.parametrize("ex", EXTRACTORS, ids=lambda f: f.__module__.rsplit(".", 1)[-1] + "." + f.__name__)
def test_50mb_under_2s(ex) -> None:  # type: ignore[no-untyped-def]
    base = [clean(t) for t in corpus(2000, seed=1)]
    lines: list[tuple[int, str]] = []
    size = 0
    while size < 50 * 1024 * 1024:
        for t in base:
            lines.append((len(lines) + 1, t))
            size += len(t) + 1
    t0 = time.perf_counter()
    ex(1, lines)
    assert time.perf_counter() - t0 < 2.0
