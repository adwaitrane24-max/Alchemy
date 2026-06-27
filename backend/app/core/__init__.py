"""Core application infrastructure — configuration, logging, lifecycle management."""

from __future__ import annotations

from backend.app.core.lifecycle import on_shutdown, on_startup
from backend.app.core.logging import setup_logging

__all__ = ["on_shutdown", "on_startup", "setup_logging"]
