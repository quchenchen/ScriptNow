from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCRIPTNOW_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./data/scriptnow.db"
    environment: str = "development"
    access_token_secret: str = Field(default="development-only-change-me", min_length=24)
    access_token_issuer: str = "scriptnow"
    creator_audience: str = "scriptnow-creator"
    admin_audience: str = "scriptnow-admin"
    access_token_minutes: int = Field(default=60, ge=1, le=1440)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    cookie_secure: bool = False
    credential_master_key: str = Field(
        default="development-credential-key-change-me",
        min_length=32,
    )
    credential_key_version: int = Field(default=1, ge=1)
    login_max_failures: int = Field(default=5, ge=2, le=20)
    login_block_minutes: int = Field(default=15, ge=1, le=1440)
    workspace_root: str = "./data/workspaces"
    upload_max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    upload_max_project_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    upload_max_project_files: int = Field(default=100, ge=1, le=10_000)
    agent_studio_url: str | None = None
    agent_runtime_timeout_seconds: float = Field(default=600, ge=0.01, le=3_600)
    agent_runtime_default_max_iters: int = Field(default=12, ge=1, le=100)
    agent_runtime_hard_max_iters: int = Field(default=32, ge=1, le=100)
    skill_plan_optional_limit: int = Field(default=2, ge=0, le=10)
    skill_prompt_max_chars: int = Field(default=6_000, ge=500, le=40_000)
    agent_budget_mode: Literal["observe", "enforce"] = "observe"
    dock_reserved_tokens: int = Field(default=8_192, ge=1)
    novel_ideation_reserved_tokens: int = Field(default=24_000, ge=1)
    novel_blueprint_reserved_tokens: int = Field(default=24_000, ge=1)
    novel_story_map_min_reserved_tokens: int = Field(default=12_000, ge=1)
    novel_story_map_max_reserved_tokens: int = Field(default=48_000, ge=1)
    novel_story_map_tokens_per_chapter: int = Field(default=1_200, ge=1)
    work_package_reserved_tokens: int = Field(default=16_000, ge=1)
    translation_min_reserved_tokens: int = Field(default=4_000, ge=1)
    translation_max_reserved_tokens: int = Field(default=200_000, ge=1)
    translation_token_reserve_ratio: float = Field(default=1.5, ge=0.1, le=10)
    novel_writer_min_reserved_tokens: int = Field(default=6_000, ge=1)
    novel_writer_max_reserved_tokens: int = Field(default=24_000, ge=1)
    novel_writer_token_reserve_ratio: float = Field(default=3, ge=0.1, le=20)
    context_retrieval_token_limit: int = Field(default=12_000, ge=1)
    context_retrieval_timeout_seconds: float = Field(default=20, ge=0.1, le=300)
    context_retrieval_max_iterations: int = Field(default=2, ge=1, le=10)
    context_retrieval_lexical_result_limit: int = Field(default=8, ge=1, le=100)
    context_retrieval_graph_result_limit: int = Field(default=8, ge=1, le=100)
    context_retrieval_conflict_policy: Literal["surface", "block"] = "surface"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.agent_runtime_default_max_iters > self.agent_runtime_hard_max_iters:
            raise ValueError("default Agent iterations cannot exceed the safety maximum")
        if self.translation_min_reserved_tokens > self.translation_max_reserved_tokens:
            raise ValueError("translation token reservation range is invalid")
        if self.novel_writer_min_reserved_tokens > self.novel_writer_max_reserved_tokens:
            raise ValueError("novel writer token reservation range is invalid")
        if (
            self.novel_story_map_min_reserved_tokens
            > self.novel_story_map_max_reserved_tokens
        ):
            raise ValueError("novel story map token reservation range is invalid")
        if self.environment == "production":
            if self.access_token_secret == "development-only-change-me":
                raise ValueError("production access token secret must be configured")
            if self.credential_master_key == "development-credential-key-change-me":
                raise ValueError("production credential master key must be configured")
            if not self.cookie_secure:
                raise ValueError("production cookies must be secure")
        return self

    @property
    def enforce_agent_budget(self) -> bool:
        return self.agent_budget_mode == "enforce"


@lru_cache
def get_settings() -> Settings:
    return Settings()
