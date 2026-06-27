"""Event dispatcher for pipeline stage transitions."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Any, Callable

from loguru import logger


class PipelineEvent(StrEnum):
    FAST_RESPONSE = "FAST_RESPONSE"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"
    CONTEXT_READY = "CONTEXT_READY"
    RESPONSE_SUCCESS = "RESPONSE_SUCCESS"
    RESPONSE_FAILED = "RESPONSE_FAILED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    STAGE_COMPLETED = "STAGE_COMPLETED"
    STAGE_FAILED = "STAGE_FAILED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    CHECKPOINT_RESTORED = "CHECKPOINT_RESTORED"
    RETRY_ATTEMPT = "RETRY_ATTEMPT"


EventHandler = Callable[[PipelineEvent, dict[str, Any]], None]


class EventDispatcher:
    """Simple synchronous event bus for pipeline lifecycle events."""

    def __init__(self) -> None:
        self._handlers: dict[PipelineEvent, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: PipelineEvent, handler: EventHandler) -> None:
        self._handlers[event].append(handler)

    def emit(self, event: PipelineEvent, data: dict[str, Any] | None = None) -> None:
        payload = data or {}
        logger.debug("Pipeline event: {} data={}", event.value, payload)
        for handler in self._handlers.get(event, []):
            try:
                handler(event, payload)
            except Exception:
                logger.opt(exception=True).warning(
                    "Event handler failed for {}", event.value
                )
