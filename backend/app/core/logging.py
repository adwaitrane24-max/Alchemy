"""Loguru logging configuration for the Alchemy gateway."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(log_level: str = "INFO", is_production: bool = False) -> None:
    """Configure Loguru with appropriate format and sink.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        is_production: If True, uses JSON format for structured log aggregation.
    """
    logger.remove()

    if is_production:
        logger.add(
            sys.stderr,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}",
            serialize=True,
        )
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | "
                "<level>{level:<8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    logger.info("Logging initialized", level=log_level, production=is_production)
