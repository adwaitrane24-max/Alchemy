"""Unit tests for application settings and the cached settings accessor."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Ensure every test sees a fresh settings cache."""
    get_settings.cache_clear()


def test_defaults_load_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should populate sensible defaults when no env vars are set."""
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})
    settings = Settings()

    assert settings.alchemy_env == "development"
    assert settings.alchemy_log_level == "INFO"
    assert settings.ollama_model == "gemma:2b"
    assert settings.budget_daily_limit_usd == 5.00


def test_get_settings_is_cached() -> None:
    """get_settings returns the same instance on repeated calls."""
    first = get_settings()
    second = get_settings()

    assert first is second


def test_get_settings_cache_clear_yields_new_instance() -> None:
    """Clearing the cache forces a fresh Settings instance."""
    first = get_settings()
    get_settings.cache_clear()
    second = get_settings()

    assert first is not second


def test_log_level_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowercase log levels are uppercased by the validator."""
    monkeypatch.setenv("ALCHEMY_LOG_LEVEL", "debug")
    get_settings.cache_clear()

    assert get_settings().alchemy_log_level == "DEBUG"


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown log level fails validation at construction time."""
    monkeypatch.setenv("ALCHEMY_LOG_LEVEL", "VERBOSE")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_threshold_must_be_ratio(monkeypatch: pytest.MonkeyPatch, value: float) -> None:
    """Ratio fields reject values outside the inclusive [0, 1] range."""
    monkeypatch.setenv("BUDGET_WARNING_THRESHOLD", str(value))
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_daily_limit_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily budget limit must be strictly positive."""
    monkeypatch.setenv("BUDGET_DAILY_LIMIT_USD", "0")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_environment_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """The is_production / is_debug helpers reflect configured values."""
    monkeypatch.setenv("ALCHEMY_ENV", "Production")
    monkeypatch.setenv("ALCHEMY_DEBUG", "true")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.alchemy_env == "production"
    assert settings.is_production is True
    assert settings.is_debug is True
