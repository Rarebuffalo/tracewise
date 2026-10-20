"""Phase 57 (F1): read_file cut its output at max_output_chars but recorded the whole requested range as examined, so a
location the model never saw passed rule 2. Found by an offline audit, reproduced first."""

from __future__ import annotations

import re

from tests.investigate.factory import B02_ANSWER, B02_FILES, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.fake import ScriptedProvider

# ------------------------------------------------------------------ F1


BIG = "".join(f"x_{i} = {'1' * 90}\n" for i in range(1, 251))  # 250 lines of ~100 characters


def test_f1_read_file_reports_and_records_only_the_lines_it_returned() -> None:
    ev = evidence(files={**B02_FILES, "coffee_shop/big.py": BIG})
    res = ev.tools.call("read_file", {"path": "coffee_shop/big.py", "start": 1, "end": 250})
    numbered = [int(m.group(1)) for m in re.finditer(r"^(\d+): ", res.content, flags=re.M)]
    header = res.content.splitlines()[0]
    last = numbered[-1]
    assert last < 250 and f"lines 1-{last} of 250" in header  # the header states what was really returned
    assert "output truncated" not in res.content  # nothing is cut mid-way any more
    assert res.content.count("\n") == len(numbered)  # every returned line is whole


def test_f1_a_location_beyond_the_returned_lines_is_not_examined() -> None:
    ev = evidence(files={**B02_FILES, "coffee_shop/big.py": BIG})
    ans = {
        **B02_ANSWER,
        "problem_location": {"path": "coffee_shop/big.py", "line_start": 240, "line_end": 240},
        "fix": None,
        "why": "x",
        "file_verdicts": [],
    }
    script = [tool("read_file", path="coffee_shop/big.py", start=1, end=250), answer(**ans)]
    d = diagnose(ev, ScriptedProvider(script)).diagnosis
    assert d.problem_location is None or d.problem_location.line_start != 240
    big = [f for f in d.files_examined if f.path == "coffee_shop/big.py"]
    assert big and big[0].end < 240
