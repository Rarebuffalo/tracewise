"""Connection-URL helpers. URLs are secrets (they may embed passwords) and are never logged."""

from __future__ import annotations


def sqlalchemy_url(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise ValueError("unsupported database URL scheme")


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)
