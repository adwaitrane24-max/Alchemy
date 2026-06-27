"""Checkpoint manager — saves and restores pipeline state for fault tolerance."""

from __future__ import annotations

import abc
import itertools
import time
from datetime import UTC, datetime

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

    _id_counter = itertools.count(1)

    def __init__(
        self,
        backend: CheckpointBackend | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self._backend = backend or InMemoryCheckpointBackend()
        self._dispatcher = dispatcher

    def save_checkpoint(self, context: PipelineContext) -> str:
        """Save a checkpoint and return its ID.

        Returns:
            The generated checkpoint ID (e.g. ``CHK-0012``).
        """
        checkpoint_id = f"CHK-{next(self._id_counter):04d}"
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")

        try:
            context.checkpoints_created += 1
            data = context.serialize()
            self._backend.save(context.request_id, data)

            logger.info(
                "Checkpoint created id={} stage={} timestamp={}",
                checkpoint_id,
                context.current_stage.value if context.current_stage else "unknown",
                timestamp,
            )
            if self._dispatcher:
                self._dispatcher.emit(
                    PipelineEvent.CHECKPOINT_CREATED,
                    {
                        "checkpoint_id": checkpoint_id,
                        "request_id": context.request_id,
                        "stage": context.current_stage.value if context.current_stage else None,
                        "timestamp": timestamp,
                        "completed_stages": [s.value for s in context.completed_stages],
                    },
                )
            return checkpoint_id

        except Exception as exc:
            raise CheckpointError(
                f"Failed to save checkpoint: {exc}",
                stage=context.current_stage.value if context.current_stage else None,
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
