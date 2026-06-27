"""Checkpoint manager — saves and restores pipeline state for fault tolerance."""

from __future__ import annotations

import abc
import json
from typing import Any

from loguru import logger

from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.exceptions import CheckpointError
from backend.app.pipeline.pipeline_context import PipelineContext
from backend.app.pipeline.stage_status import StageName


class CheckpointBackend(abc.ABC):
    """Abstract checkpoint storage — swap in SQLite/Redis later."""

    @abc.abstractmethod
    def save(self, request_id: str, data: str) -> None: ...

    @abc.abstractmethod
    def load(self, request_id: str) -> str | None: ...

    @abc.abstractmethod
    def delete(self, request_id: str) -> None: ...


class InMemoryCheckpointBackend(CheckpointBackend):
    """In-memory store for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def save(self, request_id: str, data: str) -> None:
        self._store[request_id] = data

    def load(self, request_id: str) -> str | None:
        return self._store.get(request_id)

    def delete(self, request_id: str) -> None:
        self._store.pop(request_id, None)


class CheckpointManager:
    """Saves pipeline context after each successful stage."""

    def __init__(
        self,
        backend: CheckpointBackend | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self._backend = backend or InMemoryCheckpointBackend()
        self._dispatcher = dispatcher

    def save_checkpoint(self, context: PipelineContext) -> None:
        try:
            data = context.serialize()
            self._backend.save(context.request_id, data)
            logger.debug(
                "Checkpoint saved request_id={} stage={}",
                context.request_id,
                context.current_stage,
            )
            if self._dispatcher:
                self._dispatcher.emit(
                    PipelineEvent.CHECKPOINT_CREATED,
                    {"request_id": context.request_id, "stage": context.current_stage},
                )
        except Exception as exc:
            raise CheckpointError(
                f"Failed to save checkpoint: {exc}", stage=str(context.current_stage)
            ) from exc

    def load_checkpoint(self, request_id: str) -> PipelineContext | None:
        data = self._backend.load(request_id)
        if data is None:
            return None
        try:
            ctx = PipelineContext.deserialize(data)
            logger.info("Checkpoint restored request_id={}", request_id)
            if self._dispatcher:
                self._dispatcher.emit(
                    PipelineEvent.CHECKPOINT_RESTORED,
                    {"request_id": request_id, "stage": ctx.current_stage},
                )
            return ctx
        except Exception as exc:
            raise CheckpointError(
                f"Failed to load checkpoint: {exc}"
            ) from exc

    def delete_checkpoint(self, request_id: str) -> None:
        self._backend.delete(request_id)
