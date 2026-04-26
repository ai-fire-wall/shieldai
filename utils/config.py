"""
Configuration — loaded from environment variables with safe defaults.
Copy .env.example to .env and fill in your values.
"""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "ShieldAI"
    app_version: str = "0.2.0"
    debug: bool = False

    # ── LLM API Keys ──────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://shieldai:shieldai@localhost:5432/shieldai"
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth ──────────────────────────────────────────────────────────────────
    api_key_header: str = "X-ShieldAI-Key"
    # Comma-separated list of valid API keys; empty = no auth (dev mode)
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
