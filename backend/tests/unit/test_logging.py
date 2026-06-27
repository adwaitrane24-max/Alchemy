"""Unit tests for Loguru logging configuration."""

from __future__ import annotations

from loguru import logger

from backend.app.core import setup_logging


def test_setup_logging_emits_records_at_level() -> None:
    """After setup, messages at the configured level reach the sink."""
    records: list[str] = []
    setup_logging(log_level="INFO")
    sink_id = logger.add(records.append, level="INFO", format="{message}")
    try:
        logger.info("hello-world")
    finally:
        logger.remove(sink_id)

    assert any("hello-world" in record for record in records)


def test_setup_logging_respects_min_level() -> None:
    """Messages below the configured level are filtered out."""
    records: list[str] = []
    setup_logging(log_level="WARNING")
    sink_id = logger.add(records.append, level="WARNING", format="{message}")
    try:
        logger.debug("should-not-appear")
        logger.warning("should-appear")
    finally:
        logger.remove(sink_id)

    joined = "".join(records)
    assert "should-appear" in joined
    assert "should-not-appear" not in joined


def test_setup_logging_production_is_idempotent() -> None:
    """Calling setup repeatedly (incl. production mode) does not raise."""
    setup_logging(log_level="INFO", is_production=True)
    setup_logging(log_level="DEBUG", is_production=False)
