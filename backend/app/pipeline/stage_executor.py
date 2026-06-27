"""Stage executor — runs a single stage with timing, retry, and checkpoint."""

from __future__ import annotations

import time
from typing import Any, Callable

from loguru import logger

from backend.app.pipeline.checkpoint_manager import CheckpointManager
from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.exceptions import StageExecutionError
from backend.app.pipeline.execution_trace import ExecutionTrace
from backend.app.pipeline.pipeline_context import PipelineContext
from backend.app.pipeline.retry_manager import RetryManager
from backend.app.pipeline.stage_status import StageName, StageRecord, StageStatus

StageCallable = Callable[[PipelineContext], None]


class StageExecutor:
    """Executes a pipeline stage with retry, checkpoint, and trace recording."""

    def __init__(
        self,
        retry_manager: RetryManager,
        checkpoint_manager: CheckpointManager,
        dispatcher: EventDispatcher,
    ) -> None:
        self._retry = retry_manager
        self._checkpoint = checkpoint_manager
        self._dispatcher = dispatcher

    def execute(
        self,
        stage_name: StageName,
        fn: StageCallable,
        context: PipelineContext,
    ) -> StageRecord:
        """Run *fn* for the given stage, handling retries and checkpointing.

        Returns the completed StageRecord (also appended to the execution trace).
        Raises StageExecutionError if retries are exhausted.
        """
        context.mark_running(stage_name)
        logger.info("Stage started: {}", stage_name.value)

        last_error: str | None = None
        attempt = 0

        while True:
            start = time.perf_counter()
            try:
                fn(context)
                latency = self._elapsed_ms(start)

                record = StageRecord(
                    name=stage_name,
                    status=StageStatus.COMPLETED,
                    latency_ms=latency,
                    retry_count=attempt,
                    checkpoint_time=time.time(),
                )
                context.execution_trace.add(record)
                self._checkpoint.save_checkpoint(context)
                self._dispatcher.emit(
                    PipelineEvent.STAGE_COMPLETED,
                    {"stage": stage_name.value, "latency_ms": latency},
                )
                logger.info(
                    "Stage completed: {} latency={:.2f}ms", stage_name.value, latency
                )
                return record

            except Exception as exc:
                latency = self._elapsed_ms(start)
                last_error = str(exc)
                attempt_num = self._retry.record_attempt(stage_name, last_error)
                attempt = attempt_num

                logger.warning(
                    "Stage failed: {} attempt={} error={}",
                    stage_name.value,
                    attempt_num,
                    last_error,
                )
                self._dispatcher.emit(
                    PipelineEvent.STAGE_FAILED,
                    {"stage": stage_name.value, "error": last_error, "attempt": attempt_num},
                )

                if self._retry.can_retry(stage_name):
                    self._dispatcher.emit(
                        PipelineEvent.RETRY_ATTEMPT,
                        {"stage": stage_name.value, "attempt": attempt_num + 1},
                    )
                    self._retry.wait_before_retry(stage_name)
                    continue

                record = StageRecord(
                    name=stage_name,
                    status=StageStatus.FAILED,
                    latency_ms=latency,
                    retry_count=attempt,
                    error=last_error,
                )
                context.execution_trace.add(record)
                raise StageExecutionError(
                    f"Stage {stage_name.value} failed after {attempt} attempt(s): {last_error}",
                    stage=stage_name.value,
                ) from exc

    def skip(
        self,
        stage_name: StageName,
        context: PipelineContext,
    ) -> StageRecord:
        """Record a stage as skipped in the execution trace."""
        record = StageRecord(name=stage_name, status=StageStatus.SKIPPED)
        context.execution_trace.add(record)
        logger.info("Stage skipped: {}", stage_name.value)
        return record

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 3)
