"""Application lifecycle management — startup and shutdown hooks."""

from __future__ import annotations

from loguru import logger


async def on_startup() -> None:
    """Initialize application resources on startup.

    Will be connected to FastAPI lifespan events.
    Responsibilities: database connections, FAISS index loading,
    embedding model initialization, Otari client setup.
    """
    logger.info("Alchemy gateway starting up")


async def on_shutdown() -> None:
    """Cleanup application resources on shutdown.

    Responsibilities: close database connections, flush analytics,
    persist FAISS index, close HTTP clients.
    """
    logger.info("Alchemy gateway shutting down")
