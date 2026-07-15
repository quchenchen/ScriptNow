"""Application settings (pydantic-settings).

Loaded from environment variables (and ``.env`` if present). Required fields
without a default raise on startup, so the app refuses to boot in an unsafe
configuration.

Not to be confused with ``app.core.config`` (legacy, kept for backward
compat with a small number of imports). This module is the single source
of truth for new code.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings, read from env / .env.

    Required fields (no default) will raise ``ValidationError`` at
    construction time if missing — this is intentional. Never fall back
    to a random secret; that would silently invalidate every issued
    token on every restart.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Auth ──
    JWT_SECRET: str = Field(min_length=16, description="Signing secret for access tokens.")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    # ── App ──
    APP_NAME: str = "ScriptFlow"

    # ── LLM providers (all optional; at least one required for real Agent calls) ──
    DASHSCOPE_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Memoized Settings accessor. First call parses env; later calls reuse."""
    return Settings()  # type: ignore[call-arg]
