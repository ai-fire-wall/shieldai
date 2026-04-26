"""
Configuration — loaded from environment variables.
Render injects DATABASE_URL, REDIS_URL, and PORT automatically.
Copy .env.example to .env for local development.
"""

import os
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings


def _fix_db_url(url: str) -> str:
    """
    Render (and Heroku) provide postgres:// URLs.
    asyncpg requires postgresql+asyncpg://.
    This fixes it automatically regardless of what Render injects.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "ShieldAI"
    app_version: str = "0.2.0"
    debug: bool = False

    # ── LLM API Keys ──────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    # Render injects DATABASE_URL automatically when you attach a Postgres DB
    database_url: str = "postgresql+asyncpg://shieldai:shieldai@localhost:5432/shieldai"

    @property
    def async_database_url(self) -> str:
        return _fix_db_url(self.database_url)

    # ── Cache ─────────────────────────────────────────────────────────────────
    # Render injects REDIS_URL automatically when you attach a Redis instance
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth ──────────────────────────────────────────────────────────────────
    api_key_header: str = "X-ShieldAI-Key"
    # Comma-separated list of valid caller API keys; empty = no auth (dev mode)
    api_keys_raw: str = ""

    @property
    def api_keys(self) -> List[str]:
        if not self.api_keys_raw.strip():
            return []
        return [k.strip() for k in self.api_keys_raw.split(",") if k.strip()]

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 60

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_to_db: bool = True

    # ── Filter behaviour ──────────────────────────────────────────────────────
    block_on_high_threat: bool = True
    redact_pii_default: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
