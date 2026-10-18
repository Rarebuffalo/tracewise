"""Settings from the environment (docs/IMPLEMENTATION-PLAN.md section 4).

Secrets are `SecretStr` so they never appear in repr, logs or exceptions.
No personal, global or CLI GitHub credentials are read (FS-SEC-5, ADR-16).
"""

from __future__ import annotations

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

    # LIVE only: the project-scoped dev App in the approved test org.
    github_app_id: int | None = None
    github_app_private_key_path: Path | None = None
    github_webhook_secret: SecretStr | None = None

    llm_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr | None = None
    llm_model: str | None = None

    investigation_max_tool_calls: int = Field(12, ge=1, le=12)
    investigation_timeout_s: int = Field(120, ge=1, le=120)
    log_max_bytes_per_job: int = Field(2 * 1024 * 1024, ge=1024)
    report_max_chars: int = Field(60_000, ge=1000)

    @model_validator(mode="after")
    def _provider_needs_key(self) -> Settings:
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY in the local environment")
        return self

    def secret_values(self) -> list[str]:
        """Configured secret values, for the log redaction filter."""
        out = []
        for s in (
            self.database_url,
            self.database_url_system,
            self.database_url_migrations,
            self.github_webhook_secret,
            self.openai_api_key,
        ):
            if s is not None and s.get_secret_value():
                out.append(s.get_secret_value())
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
