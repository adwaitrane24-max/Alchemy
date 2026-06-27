"""Application settings loaded from environment variables via Pydantic."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Alchemy gateway.

    All values are loaded from environment variables or .env file.
    Prefix: ALCHEMY_ for application-level settings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────
    alchemy_env: str = "development"
    alchemy_debug: bool = False
    alchemy_log_level: str = "INFO"

    # ── Mozilla Otari Gateway ────────────────────
    otari_api_key: str = ""
    otari_base_url: str = ""
    otari_timeout_ms: int = 5000

    # ── OpenAI (via Otari) ──────────────────────
    openai_api_key: str = ""

    # ── Ollama (Local 2B) ───────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma:2b"

    # ── Smallest.ai (Voice STT) ─────────────────
    smallest_ai_api_key: str = ""
    smallest_ai_base_url: str = ""

    # ── Budget ───────────────────────────────────
    budget_daily_limit_usd: float = 5.00
    budget_warning_threshold: float = 0.60
    budget_critical_threshold: float = 0.85

    # ── Semantic Cache ───────────────────────────
    cache_similarity_threshold: float = 0.85
    cache_default_ttl_hours: int = 168
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Database ─────────────────────────────────
    database_path: Path = Path("data/alchemy.db")

    # ── Security ─────────────────────────────────
    security_fail_open: bool = False
    security_log_blocked: bool = True

    # ── Context Manager ─────────────────────────
    context_max_chunks_healthy: int = 5
    context_max_chunks_low: int = 3
    context_summary_max_tokens: int = 200

    @property
    def is_production(self) -> bool:
        return self.alchemy_env == "production"

    @property
    def is_debug(self) -> bool:
        return self.alchemy_debug
