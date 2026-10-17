#!/usr/bin/env python3
"""Consistency checks for the canonical Tracewise documentation (T-002).

Checks:
  1. Relative markdown links and backticked research/ paths in active docs resolve.
  2. SPEC <-> TASKS <-> ACCEPTANCE-TESTS traceability.
  3. No obsolete or forbidden instructions in active docs.
  4. Benchmark cases B-01..B-16 from doc 04 are consolidated in docs/BENCHMARK.md.

Exit code 0 when all checks pass, 1 otherwise. Read-only; no network.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

ACTIVE = sorted(DOCS.glob("*.md")) + [
    p for p in [ROOT / "research" / "README.md", *sorted((ROOT / "research" / "archive").glob("*/README.md"))]
    if p.exists()
]
# Change records describe removed instructions on purpose; they are exempt from check 3.
CHANGE_RECORDS = {"DOC-CHANGE-PLAN.md", "CHANGELOG.md"}

DOC04_CANDIDATES = [
    ROOT / "research" / "04-failure-benchmark.md",
    ROOT / "research" / "archive" / "2026-10-15-s1-research" / "04-failure-benchmark.md",
]

BANNED = [
    (r"gh auth login", "CLI login (no-credentials rule)"),
    (r"gh run list", "gh CLI usage (no-credentials rule)"),
    (r"GITHUB_TOKEN_LAB", "personal lab token"),
    (r"fine-grained PAT", "personal access token"),
    (r"ksingh", "unintended account"),
    (r"REAL-SET", "withdrawn real-log benchmark"),
    (r"60 seconds|under a minute|in under two minutes", "unmeasured latency claim"),
]
NEGATION = re.compile(r"(?i)\b(removed|replaced|no `?gh|not carried|never|withdrawn|forbidden|excluded)\b")

errors: list[str] = []
notes: list[str] = []


def check_links() -> None:
    link_re = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
    tick_re = re.compile(r"`(research/[^`\s*{}…]+)`")
    n = 0
    for doc in ACTIVE:
        text = doc.read_text(encoding="utf-8")
        if doc.name in CHANGE_RECORDS:
            # Change records cite pre-move paths on purpose; only their markdown links are checked.
            text = re.sub(r"`research/[^`]*`", "", text)
        for target in link_re.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            n += 1
            if not (doc.parent / target).resolve().exists():
                errors.append(f"[links] {doc.relative_to(ROOT)} -> {target} (missing)")
        for target in tick_re.findall(text):
            target = target.rstrip(".,;:")
            n += 1
            if not (ROOT / target).exists():
                errors.append(f"[paths] {doc.relative_to(ROOT)} -> {target} (missing)")
    notes.append(f"links/paths checked: {n}")


def ids(pattern: str, text: str) -> set[str]:
    return set(re.findall(pattern, text))


def expand_ranges(text: str, prefix: str) -> set[str]:
    """Expand 'AT-DX-08..11' style ranges into individual IDs."""
    out: set[str] = set()
    for m in re.finditer(rf"({prefix}-[A-Z]+)-(\d+)\.\.(\d+)", text):
        base, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        out |= {f"{base}-{i:02d}" for i in range(a, b + 1)}
    return out


def check_traceability() -> None:
    spec = (DOCS / "SPEC.md").read_text(encoding="utf-8")
    tasks = (DOCS / "TASKS.md").read_text(encoding="utf-8")
    tests = (DOCS / "ACCEPTANCE-TESTS.md").read_text(encoding="utf-8")

    fs_defined = set(re.findall(r"^\| (FS-[A-Z]+-\d+) \|", spec, re.M))
    task_defined = set(re.findall(r"^\| (T-\d+) \|", tasks, re.M))
    at_defined = set(re.findall(r"^\| (AT-[A-Z]+-\d+) \|", tests, re.M))

    # Spec rows: each FS must reference >=1 AT and >=1 T.
    for row in re.findall(r"^\| (FS-[A-Z]+-\d+) \|(.*)$", spec, re.M):
        fs, rest = row
        ats = ids(r"AT-[A-Z]+-\d+", rest) | expand_ranges(rest, "AT")
        ts = ids(r"(?<![A-Za-z-])T-\d+", rest)
        if not ats:
            errors.append(f"[trace] {fs} has no acceptance test")
        if not ts:
            errors.append(f"[trace] {fs} has no task")
        for t in ts - task_defined:
            errors.append(f"[trace] {fs} references undefined task {t}")
        for a in ats - at_defined:
            errors.append(f"[trace] {fs} references undefined test {a}")

    # Task rows: referenced FS and AT must exist.
    for row in re.findall(r"^\| (T-\d+) \|(.*)$", tasks, re.M):
        t, rest = row
        for fs in ids(r"FS-[A-Z]+-\d+", rest) - fs_defined:
            errors.append(f"[trace] {t} references undefined requirement {fs}")
        for a in (ids(r"AT-[A-Z]+-\d+", rest) | expand_ranges(rest, "AT")) - at_defined:
            errors.append(f"[trace] {t} references undefined test {a}")

    # Test rows: referenced FS (short form like INS-1) must exist.
    for row in re.findall(r"^\| (AT-[A-Z]+-\d+) \| ([^|]+) \|", tests, re.M):
        at, fs_col = row
        for short in re.findall(r"\b([A-Z]{2,4}-\d+)\b", fs_col):
            if f"FS-{short}" not in fs_defined:
                errors.append(f"[trace] {at} references undefined requirement FS-{short}")

    # Every test should be referenced somewhere in SPEC or TASKS.
    referenced = (ids(r"AT-[A-Z]+-\d+", spec + tasks) | expand_ranges(spec + tasks, "AT"))
    unref = sorted(at_defined - referenced - {"AT-CMP-01", "AT-RPT-10"})
    for a in unref:
        errors.append(f"[trace] test {a} is not referenced by any requirement or task")

    # Every P0 requirement must map to at least one task (checked above); count for the report.
    p0 = re.findall(r"^\| (FS-[A-Z]+-\d+) \|.*\| P0 \|$", spec, re.M)
    notes.append(f"requirements: {len(fs_defined)} ({len(p0)} P0); tasks: {len(task_defined)}; tests: {len(at_defined)}")


def check_banned() -> None:
    hits = 0
    for doc in ACTIVE:
        if doc.name in CHANGE_RECORDS:
            continue
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for pat, why in BANNED:
                if re.search(pat, line) and not NEGATION.search(line):
                    hits += 1
                    errors.append(f"[banned] {doc.relative_to(ROOT)}:{i}: {why}: {line.strip()[:120]}")
    notes.append(f"banned-instruction hits: {hits} (change records exempt: {', '.join(sorted(CHANGE_RECORDS))})")


KEY_PHRASES = {
    "B-01": ["TS2305"], "B-02": ["subtotal * TAX_RATE", "0.21 == 2.71"], "B-03": ["snapshot"],
    "B-04": ["GITHUB_RUN_ATTEMPT", "random"], "B-05": ["foo", "no attribute 'bar'"],
    "B-06": ["ResolutionImpossible", "ERESOLVE"], "B-07": ["DB_URL"], "B-08": ["connection refused"],
    "B-09": ["ReadTimeout"], "B-10": ["F401"], "B-11": ["utcnow"], "B-12": ["40"],
    "B-13": ["maximum execution time"], "B-14": ["137"], "B-15": ["B-04"], "B-16": ["C4"],
}


def check_benchmark() -> None:
    doc04 = next((p for p in DOC04_CANDIDATES if p.exists()), None)
    bench = (DOCS / "BENCHMARK.md").read_text(encoding="utf-8")
    if doc04 is None:
        errors.append("[bench] doc 04 not found in research/ or archive")
        return
    src = doc04.read_text(encoding="utf-8")
    src_ids = set(re.findall(r"^\| (B-\d\d) \|", src, re.M))
    rows: dict[str, str] = {}
    for m in re.finditer(r"^\| (B-\d\d) \|.*$", bench, re.M):
        rows.setdefault(m.group(1), m.group(0))  # first occurrence = case catalogue row
    for cid in sorted(src_ids):
        row = rows.get(cid)
        if row is None:
            errors.append(f"[bench] {cid} from doc 04 missing in docs/BENCHMARK.md")
            continue
        for phrase in KEY_PHRASES.get(cid, []):
            if phrase not in row:
                errors.append(f"[bench] {cid}: ground-truth phrase '{phrase}' not in consolidated row")
    notes.append(f"doc 04 cases verified: {len(src_ids)} (source: {doc04.relative_to(ROOT)})")


def main() -> int:
    check_links()
    check_traceability()
    check_banned()
    check_benchmark()
    for n in notes:
        print("note:", n)
    for e in errors:
        print("FAIL:", e)
    print("RESULT:", "PASS" if not errors else f"FAIL ({len(errors)} issues)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
