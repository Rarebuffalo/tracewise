"""Phase 46E: independent boundary audit of the P-3 storage cap (`repositories.stored_snippet`).

The approved rule: the persisted source snippet is redacted first, then at most 2000 UTF-8 bytes, never split
inside a character. These checks sweep sizes and character widths around the limit, put secrets exactly at the
cut, and include redaction that makes the text longer. The database round trip is covered in
tests/db/test_schema_repositories.py::test_p3_*. Synthetic secrets only.
"""

from __future__ import annotations

import pytest

from tracewise.db.repositories import SNIPPET_MAX_BYTES, SNIPPET_TRUNCATED, stored_snippet
from tracewise.prepass.sanitize import redact

CHARS = {"ascii": "a", "2-byte": "é", "3-byte": "€", "4-byte": "😀"}
SECRET = "ghp_" + "Bd4" * 12  # 40 characters, matched by the gh[pousr]_ pattern
NEEDLE = "Bd4Bd4Bd4"


def check(snippet: str) -> str:
    out = stored_snippet(snippet)
    raw = out.encode("utf-8")  # would raise if a surrogate or split character survived
    assert len(raw) <= SNIPPET_MAX_BYTES
    assert raw.decode("utf-8") == out
    assert NEEDLE not in out
    if len(redact(snippet).encode("utf-8")) <= SNIPPET_MAX_BYTES:
        assert out == redact(snippet)  # within the cap: stored as redacted, nothing cut
    else:
        assert out.endswith(SNIPPET_TRUNCATED)
        assert redact(snippet).startswith(out[: -len(SNIPPET_TRUNCATED)].rstrip("\n"))  # a prefix, never invented
    return out


@pytest.mark.parametrize("kind", list(CHARS))
@pytest.mark.parametrize("lines", [1, 15], ids=["one-line", "15-lines"])
def test_sizes_around_the_limit_never_exceed_2000_bytes(kind: str, lines: int) -> None:
    ch = CHARS[kind]
    width = len(ch.encode("utf-8"))
    for total in range(SNIPPET_MAX_BYTES - 12, SNIPPET_MAX_BYTES + 13):
        per_line = max(1, total // width // lines)
        check("".join(ch * per_line + "\n" for _ in range(lines)))
        check(ch * (total // width))  # no newline at all


@pytest.mark.parametrize("offset", range(-45, 6))
def test_a_secret_straddling_the_cut_is_redacted_not_half_kept(offset: int) -> None:
    # Place the secret so that it starts `offset` bytes from where a naive 2000-byte cut would land.
    pad = "x" * (SNIPPET_MAX_BYTES - len(SNIPPET_TRUNCATED) - 1 + offset)
    out = check(pad + " " + SECRET + " tail " + "y" * 200)
    assert "ghp_Bd4" not in out


def test_redaction_that_lengthens_the_text_is_capped_after_redaction() -> None:
    short_secret = "AKIA" + "BDEXPANDZZZZZZZZ"  # 20 characters → "[REDACTED…]" marker may be longer
    snippet = (" " + short_secret) * 120  # under 2000 bytes before redaction, possibly over after
    assert len(snippet.encode("utf-8")) < SNIPPET_MAX_BYTES + 600
    out = check(snippet)
    assert "BDEXPAND" not in out


def test_one_line_exactly_at_the_budget_and_one_byte_over() -> None:
    budget = SNIPPET_MAX_BYTES - len(SNIPPET_TRUNCATED) - 1
    assert check("a" * SNIPPET_MAX_BYTES) == "a" * SNIPPET_MAX_BYTES  # exactly the limit: unchanged
    cut = check("a" * (SNIPPET_MAX_BYTES + 1))
    assert cut == "a" * budget + "\n" + SNIPPET_TRUNCATED and len(cut.encode()) == SNIPPET_MAX_BYTES
