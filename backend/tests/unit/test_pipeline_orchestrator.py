"""Unit tests for the stateful pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.constants.enums import (
    FastRequestCategory,
    RoutingAction,
    SecurityStatus,
    TaskType,
    ThreatType,
)
from backend.app.constants.models import ModelID
from backend.app.models.analysis import FastDetectorResult, PromptAnalysis, SecurityResult
from backend.app.models.request import PromptRequest
from backend.app.pipeline.checkpoint_manager import CheckpointManager, InMemoryCheckpointBackend
from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.exceptions import StageExecutionError
from backend.app.pipeline.execution_trace import ExecutionTrace
from backend.app.pipeline.pipeline_context import PipelineContext, PipelineStatus
from backend.app.pipeline.retry_manager import RetryConfig, RetryManager, RetryStrategy
from backend.app.pipeline.stage_executor import StageExecutor
from backend.app.pipeline.stage_status import StageName, StageRecord, StageStatus


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


@pytest.fixture
def retry_manager() -> RetryManager:
    return RetryManager()


@pytest.fixture
def checkpoint_manager(dispatcher: EventDispatcher) -> CheckpointManager:
    return CheckpointManager(dispatcher=dispatcher)


@pytest.fixture
def stage_executor(
    retry_manager: RetryManager,
    checkpoint_manager: CheckpointManager,
    dispatcher: EventDispatcher,
) -> StageExecutor:
    return StageExecutor(retry_manager, checkpoint_manager, dispatcher)


@pytest.fixture
def context() -> PipelineContext:
    return PipelineContext(
        request_id="test-123",
        user_query="What is Python?",
    )


# ── StageStatus / StageRecord ─────────────────────────


def test_stage_status_values() -> None:
    assert StageStatus.PENDING == "PENDING"
    assert StageStatus.COMPLETED == "COMPLETED"
    assert StageStatus.FAILED == "FAILED"
    assert StageStatus.SKIPPED == "SKIPPED"


def test_stage_record_creation() -> None:
    record = StageRecord(
        name=StageName.FAST_DETECTOR,
        status=StageStatus.COMPLETED,
        latency_ms=1.5,
    )
    assert record.name == StageName.FAST_DETECTOR
    assert record.status == StageStatus.COMPLETED
    assert record.latency_ms == 1.5
    assert record.error is None


# ── ExecutionTrace ────────────────────────────────────


def test_execution_trace_add_and_query() -> None:
    trace = ExecutionTrace()
    trace.add(StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=1.0))
    trace.add(StageRecord(name=StageName.SECURITY, status=StageStatus.SKIPPED))
    trace.add(StageRecord(name=StageName.TASK_ANALYZER, status=StageStatus.FAILED, error="boom"))

    assert trace.completed_stages == [StageName.FAST_DETECTOR]
    assert trace.skipped_stages == [StageName.SECURITY]
    assert trace.failed_stages == [StageName.TASK_ANALYZER]
    assert trace.total_latency_ms == 1.0


def test_execution_trace_summary() -> None:
    trace = ExecutionTrace()
    trace.add(StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=2.0))
    summary = trace.summary()
    assert len(summary) == 1
    assert summary[0]["stage"] == "fast_detector"
    assert summary[0]["status"] == "COMPLETED"


# ── EventDispatcher ───────────────────────────────────


def test_event_dispatcher_emits_to_subscribers(dispatcher: EventDispatcher) -> None:
    received = []
    dispatcher.subscribe(PipelineEvent.STAGE_COMPLETED, lambda e, d: received.append((e, d)))
    dispatcher.emit(PipelineEvent.STAGE_COMPLETED, {"stage": "test"})
    assert len(received) == 1
    assert received[0][1]["stage"] == "test"


def test_event_dispatcher_handler_error_does_not_propagate(dispatcher: EventDispatcher) -> None:
    def bad_handler(e, d):
        raise RuntimeError("handler error")

    dispatcher.subscribe(PipelineEvent.STAGE_COMPLETED, bad_handler)
    dispatcher.emit(PipelineEvent.STAGE_COMPLETED, {})


# ── RetryManager ──────────────────────────────────────


def test_retry_manager_respects_max_retries() -> None:
    mgr = RetryManager({
        StageName.SECURITY: RetryConfig(max_retries=2),
    })
    assert mgr.can_retry(StageName.SECURITY)
    mgr.record_attempt(StageName.SECURITY, "err1")
    assert mgr.can_retry(StageName.SECURITY)
    mgr.record_attempt(StageName.SECURITY, "err2")
    assert not mgr.can_retry(StageName.SECURITY)


def test_retry_manager_reset() -> None:
    mgr = RetryManager({StageName.SECURITY: RetryConfig(max_retries=1)})
    mgr.record_attempt(StageName.SECURITY, "err")
    assert not mgr.can_retry(StageName.SECURITY)
    mgr.reset(StageName.SECURITY)
    assert mgr.can_retry(StageName.SECURITY)


# ── PipelineContext ───────────────────────────────────


def test_pipeline_context_serialization(context: PipelineContext) -> None:
    data = context.serialize()
    restored = PipelineContext.deserialize(data)
    assert restored.request_id == context.request_id
    assert restored.user_query == context.user_query


def test_pipeline_context_mark_completed(context: PipelineContext) -> None:
    context.mark_completed()
    assert context.status == PipelineStatus.COMPLETED
    assert context.completed_at is not None


def test_pipeline_context_mark_failed(context: PipelineContext) -> None:
    context.mark_failed("something broke")
    assert context.status == PipelineStatus.FAILED
    assert context.metadata["terminal_error"] == "something broke"


def test_pipeline_context_mark_terminated_early(context: PipelineContext) -> None:
    context.mark_terminated_early("cache_hit")
    assert context.status == PipelineStatus.TERMINATED_EARLY
    assert context.metadata["early_termination_reason"] == "cache_hit"


# ── CheckpointManager ────────────────────────────────


def test_checkpoint_save_and_load(
    checkpoint_manager: CheckpointManager, context: PipelineContext
) -> None:
    checkpoint_manager.save_checkpoint(context)
    restored = checkpoint_manager.load_checkpoint(context.request_id)
    assert restored is not None
    assert restored.request_id == context.request_id


def test_checkpoint_load_missing_returns_none(checkpoint_manager: CheckpointManager) -> None:
    assert checkpoint_manager.load_checkpoint("nonexistent") is None


def test_checkpoint_delete(checkpoint_manager: CheckpointManager, context: PipelineContext) -> None:
    checkpoint_manager.save_checkpoint(context)
    checkpoint_manager.delete_checkpoint(context.request_id)
    assert checkpoint_manager.load_checkpoint(context.request_id) is None


# ── StageExecutor ─────────────────────────────────────


def test_stage_executor_success(
    stage_executor: StageExecutor, context: PipelineContext
) -> None:
    def noop(ctx: PipelineContext) -> None:
        ctx.metadata["touched"] = True

    record = stage_executor.execute(StageName.FAST_DETECTOR, noop, context)
    assert record.status == StageStatus.COMPLETED
    assert record.latency_ms >= 0
    assert context.metadata["touched"] is True


def test_stage_executor_failure_no_retry(
    dispatcher: EventDispatcher, checkpoint_manager: CheckpointManager
) -> None:
    mgr = RetryManager({StageName.FAST_DETECTOR: RetryConfig(max_retries=0)})
    executor = StageExecutor(mgr, checkpoint_manager, dispatcher)
    ctx = PipelineContext(request_id="fail-1", user_query="test")

    def boom(ctx: PipelineContext) -> None:
        raise ValueError("kaboom")

    with pytest.raises(StageExecutionError, match="kaboom"):
        executor.execute(StageName.FAST_DETECTOR, boom, ctx)


def test_stage_executor_retries_then_succeeds(
    dispatcher: EventDispatcher, checkpoint_manager: CheckpointManager
) -> None:
    mgr = RetryManager({StageName.SECURITY: RetryConfig(max_retries=2, delay_seconds=0)})
    executor = StageExecutor(mgr, checkpoint_manager, dispatcher)
    ctx = PipelineContext(request_id="retry-1", user_query="test")

    call_count = 0

    def flaky(ctx: PipelineContext) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("transient")

    record = executor.execute(StageName.SECURITY, flaky, ctx)
    assert record.status == StageStatus.COMPLETED
    assert call_count == 2


def test_stage_executor_skip(stage_executor: StageExecutor, context: PipelineContext) -> None:
    record = stage_executor.skip(StageName.CONTEXT_MANAGER, context)
    assert record.status == StageStatus.SKIPPED
    assert StageName.CONTEXT_MANAGER in context.execution_trace.skipped_stages


# ── Pipeline Exceptions ──────────────────────────────


def test_stage_execution_error_carries_stage() -> None:
    err = StageExecutionError("failed", stage="security")
    assert err.stage == "security"
    assert "failed" in str(err)
