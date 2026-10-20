"""Phase 56: `clean()` cut a line at MAX_LINE_CHARS BEFORE redacting it, so a secret crossing the cut left a
fragment too short for its pattern, kept verbatim. Redaction now runs before the cut, and a token-like run split by
the cut is dropped. Synthetic secrets only.
"""

from __future__ import annotations

import pytest

from tracewise.prepass.sanitize import MAX_LINE_CHARS, REDACTED, clean, strip_controls

# ------------------------------------------------------------------ redaction across the line cut

SECRETS = {
    "github": "ghp_" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z5A",
    "aws-key-id": "AKIA" + "QWERTYUIOPASDFGH",
    "slack": "xoxb-" + "1234567890-abcdefghijklmnop",
    "openai": "sk-proj-" + "Zx9Cv8Bn7Mq6Wr5Ty4Ui3Op2As1Df0Gh",
}


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_no_fragment_of_a_secret_survives_a_cut_inside_it(name: str) -> None:
    secret = SECRETS[name]
    for inside in range(1, len(secret)):  # the cut lands after `inside` characters of the secret
        line = "f" * (MAX_LINE_CHARS - inside - 1) + " " + secret + " trailing text"
        out = clean(line)
        assert len(out) <= MAX_LINE_CHARS
        fragments = {secret[i : i + 4] for i in range(len(secret) - 3)}
        tail = out[-(inside + 1) :]
        assert not any(f in tail for f in fragments), (name, inside)


def test_short_lines_and_secrets_inside_the_limit_behave_as_before() -> None:
    line = "deploy failed: token " + SECRETS["github"] + " rejected"
    assert clean(line) == strip_controls(line).replace(SECRETS["github"], REDACTED)
    assert clean("plain log line") == "plain log line"
    long_plain = "word " * 2000
    # A cut inside any token-like run drops that partial run (a word looks like a secret's remainder at the cut):
    # the result is the cut text back to its last separator, never a fragment.
    assert clean(long_plain) == strip_controls(long_plain).rsplit(" ", 1)[0] + " "
    exact = "a" * (MAX_LINE_CHARS - 1) + " " + "b" * 50
    assert clean(exact) == "a" * (MAX_LINE_CHARS - 1) + " "  # the cut lands on a separator: nothing else dropped
