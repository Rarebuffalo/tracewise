"""AT-LOG-06 (control sequences) and the redaction half of AT-SEC-04."""

from tracewise.prepass.sanitize import MAX_LINE_CHARS, REDACTED, clean, redact, strip_controls


def test_strips_sgr_osc8_c1_and_resolves_cr() -> None:
    raw = "\x1b[1m\x1b[31mE   assert 0.21 == 2.71\x1b[0m"
    assert strip_controls(raw) == "E   assert 0.21 == 2.71"
    osc8 = "see \x1b]8;;https://example.invalid/x\x1b\\docs\x1b]8;;\x1b\\ here"
    assert strip_controls(osc8) == "see docs here"
    osc8_bel = "\x1b]8;;http://x\x07link\x1b]8;;\x07"
    assert strip_controls(osc8_bel) == "link"
    assert strip_controls("a\x9bb\x85c\x00d\x07e") == "abcde"
    assert strip_controls("progress 10%\rprogress 55%\rdone 100%\r\n") == "done 100%"
    assert strip_controls("tab\tkept") == "tab\tkept"


def test_line_cap() -> None:
    assert len(strip_controls("x" * 100_000)) == MAX_LINE_CHARS


def test_redacts_secret_shapes() -> None:
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    ghp = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    jwt = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    pg = "postgresql://app:" + "s3cr3t-pa55" + "@db.internal:5432/app"
    line = f"key={aws} tok {ghp} jwt {jwt} url {pg}"
    out = redact(line)
    for secret in (aws, ghp, jwt, "s3cr3t-pa55"):
        assert secret not in out
    assert "db.internal:5432/app" in out
    assert out.count(REDACTED) >= 4


def test_keeps_diagnostic_content() -> None:
    sha = "d73fa1cdcb0e5f4a7b9c1d2e3f405162738495a6"
    for line in (
        f"HEAD is now at {sha}",
        "E   assert 0.21 == 2.71",
        "src/app.ts(3,10): error TS2305: Module '\"./lib\"' has no exported member 'formatPrice'.",
        "ERROR: Cannot install foo==1.9.3 and bar==2.0 because these package versions have conflicting dependencies.",
        '  File "/home/runner/work/coffee/coffee/coffee_shop/pricing.py", line 41, in total',
        "KeyError: 'DB_URL'",
    ):
        assert clean(line) == line


def test_github_masking_preserved() -> None:
    assert redact("token: ***") == "token: ***"


def test_entropy_redaction() -> None:
    tok = "Zx9Qm2Lp7Vt4Rb8Nc1Kd6Hs3Jf5Wg0Ya"
    assert REDACTED in redact(f"export X={tok}")
