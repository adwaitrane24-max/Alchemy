"""Application settings loaded from environment variables via Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
)

# A normalized ratio in the inclusive range [0, 1] (e.g. budget/cache thresholds).
Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


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

    # ── Groq (Whisper STT for voice) ──────────────
    groq_api_key: str = ""

    # ── Smallest.ai (Voice STT, legacy) ─────────
    smallest_ai_api_key: str = ""
    smallest_ai_base_url: str = ""

    # ── Budget ───────────────────────────────────
    budget_daily_limit_usd: Annotated[float, Field(gt=0.0)] = 5.00
    budget_warning_threshold: Ratio = 0.75
    budget_critical_threshold: Ratio = 0.90
    budget_session_limit_usd: Annotated[float, Field(gt=0.0)] = 2.00
    pricing_cache_ttl_seconds: Annotated[int, Field(gt=0)] = 3600
    economic_mode_default: bool = False

    # ── Semantic Cache ───────────────────────────
    cache_similarity_threshold: Ratio = 0.85
    cache_default_ttl_hours: Annotated[int, Field(gt=0)] = 168
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Pinecone Vector DB ───────────────────────
    pinecone_api_key: str = ""
    pinecone_index_name: str = ""
    pinecone_namespace: str = "alchemy"

    # ── Database ─────────────────────────────────
    database_path: Path = Path("data/alchemy.db")

    # ── Security ─────────────────────────────────
    security_fail_open: bool = False
    security_log_blocked: bool = True

    # ── Context Manager ─────────────────────────
    context_max_chunks_healthy: int = 10
    context_max_chunks_low: int = 5
    context_summary_max_tokens: int = 200
    context_top_k: int = 10
    context_max_context_tokens: int = 2000
    context_working_memory_size: int = 50
    context_min_chunk_tokens: int = 200
    context_max_chunk_tokens: int = 300
    context_similarity_weight: float = 0.4
    context_recency_weight: float = 0.25
    context_continuity_weight: float = 0.2
    context_importance_weight: float = 0.15
    context_min_relevance_score: float = 0.1

    @field_validator("alchemy_log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """Uppercase and validate the log level against Loguru's known levels."""
        normalized = str(value).strip().upper()
        if normalized not in _VALID_LOG_LEVELS:
            valid = ", ".join(sorted(_VALID_LOG_LEVELS))
            raise ValueError(f"Invalid log level {value!r}. Must be one of: {valid}")
        return normalized

    @field_validator("alchemy_env", mode="before")
    @classmethod
    def _normalize_env(cls, value: str) -> str:
        """Lowercase the environment name for stable comparisons."""
        return str(value).strip().lower()

    @property
    def is_production(self) -> bool:
        """True when running under the production environment."""
        return self.alchemy_env == "production"

    @property
    def is_debug(self) -> bool:
        """True when debug mode is enabled."""
        return self.alchemy_debug


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    This is the single dependency-injection entry point for configuration.
    Modules should depend on this accessor rather than constructing
    :class:`Settings` directly, so that the ``.env`` file is read only once.

    In tests, call ``get_settings.cache_clear()`` to force a reload after
    mutating environment variables.

    Returns:
        The cached, validated application settings.
    """
    return Settings()
