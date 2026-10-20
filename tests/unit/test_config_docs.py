"""Every setting in tracewise.config.Settings is listed in .env.example and documented in docs/CONFIGURATION.md,
so a new setting cannot ship undocumented (and a removed one cannot linger in the docs)."""

from __future__ import annotations

import re
from pathlib import Path

from tracewise.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def env_names() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def test_every_setting_is_in_env_example() -> None:
    example = (ROOT / ".env.example").read_text()
    listed = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, flags=re.M))
    assert env_names() - listed == set()


def test_every_setting_is_documented_and_no_stale_ones_remain() -> None:
    doc = (ROOT / "docs" / "CONFIGURATION.md").read_text()
    table = doc.split("## Settings", 1)[1].split("##", 1)[0]
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", table))
    assert env_names() - documented == set()
    assert documented - env_names() == set()
