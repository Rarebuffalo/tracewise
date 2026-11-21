"""Settings from the environment (docs/IMPLEMENTATION-PLAN.md section 4).

Secrets are `SecretStr` so they never appear in repr, logs or exceptions.
No personal, global or CLI GitHub credentials are read (FS-SEC-5, ADR-16).
"""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    tw_env: Literal["local", "test", "staging", "prod"] = "local"
    database_url: SecretStr | None = None  # tenant plane (tracewise_app; RLS-restricted)
    database_url_system: SecretStr | None = None  # system plane (tracewise_system; BYPASSRLS): ingress, queue, recovery
    database_url_migrations: SecretStr | None = None
    database_url_operator: SecretStr | None = None  # ops requeue only: the operator's personal login (tracewise_operator)

    # LIVE only: the project-scoped dev App in the approved test org.
    github_app_id: int | None = None
    github_app_private_key_path: Path | None = None
    github_webhook_secret: SecretStr | None = None

    # Bring your own key: the operator's own provider account. `fake` is for tests only (TW_ENV=test).
    llm_provider: Literal["fake", "openai", "gemini"] = "fake"
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    llm_model: str | None = None  # required for openai and gemini; there is no default model
    # T-706: USD per million tokens. Unset → cost_usd stays NULL ("unpriced"); never guessed (prices are T-605).
    llm_price_input_per_mtok: Decimal | None = Field(None, ge=0)
    llm_price_output_per_mtok: Decimal | None = Field(None, ge=0)

    investigation_max_tool_calls: int = Field(12, ge=1, le=12)
    investigation_timeout_s: int = Field(120, ge=1, le=120)
    log_max_bytes_per_job: int = Field(2 * 1024 * 1024, ge=1024)
    # Upper bound: GitHub comment bodies are limited to about 65,536 characters; the Check Run text has its own cap.
    report_max_chars: int = Field(60_000, ge=1000, le=60_000)
    # T-703 / FS-QTA-1: analyses per installation per UTC calendar month. Unset: no quota (the value is an owner decision).
    analysis_quota_monthly: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _provider_needs_key(self) -> Settings:
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY in the local environment")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY in the local environment")
        return self

    def secret_values(self) -> list[str]:
        """Configured secret values, for the log redaction filter."""
        out = []
        for s in (
            self.database_url,
            self.database_url_system,
            self.database_url_migrations,
            self.database_url_operator,
            self.github_webhook_secret,
            self.openai_api_key,
            self.gemini_api_key,
        ):
            if s is not None and s.get_secret_value():
                out.append(s.get_secret_value())
        return out


LLM_KEY_SETTING = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
# The model-id shape both codecs accept (the adapter's rule, with Gemini's 64-character limit).
_LLM_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def llm_config_problem(st: Settings) -> str | None:
    """Why the configured real provider cannot be built, or None. Network-free (preflight uses it); the message names
    settings, never values."""
    name = st.llm_provider
    if name not in LLM_KEY_SETTING:
        return None
    key = st.openai_api_key if name == "openai" else st.gemini_api_key
    value = key.get_secret_value() if key is not None else ""
    if not value:
        return f"LLM_PROVIDER={name} requires {LLM_KEY_SETTING[name]}"
    if len(value) < 8 or any(c.isspace() for c in value):
        return f"{LLM_KEY_SETTING[name]} is malformed"
    if not st.llm_model:
        return f"LLM_PROVIDER={name} requires LLM_MODEL (an explicit model id; there is no default)"
    if not _LLM_MODEL.match(st.llm_model):
        return "LLM_MODEL is malformed"
    return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def invalid_fields(e: Exception) -> str:
    """Names of the settings a validation error is about (upper-case env names), never their values."""
    errors = getattr(e, "errors", None)
    if callable(errors):
        try:
            return ", ".join(sorted({str(err.get("loc", ("?",))[0]).upper() for err in errors()})) or "unknown"
        except Exception:
            return "unreadable"
    return type(e).__name__
