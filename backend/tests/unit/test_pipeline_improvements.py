"""Unit tests for the three pipeline improvements:
1. Total pipeline latency (perf_counter-based)
2. Checkpoint creation & logging
3. Pipeline summary
"""

from __future__ import annotations

import time

import pytest

from backend.app.constants.enums import FastRequestCategory, SecurityStatus
from backend.app.constants.models import ModelID
from backend.app.models.analysis import FastDetectorResult, SecurityResult
from backend.app.pipeline.checkpoint_manager import CheckpointManager, InMemoryCheckpointBackend
from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.execution_trace import ExecutionTrace
from backend.app.pipeline.pipeline_context import PipelineContext, PipelineStatus
from backend.app.pipeline.pipeline_summary import PipelineSummary, build_summary
from backend.app.pipeline.stage_status import StageName, StageRecord, StageStatus


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPROVEMENT 1: Total Pipeline Latency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTotalPipelineLatency:
    def test_perf_timer_produces_positive_latency(self) -> None:
        ctx = PipelineContext(request_id="lat-1", user_query="test")
        ctx.start_timer()
        time.sleep(0.005)
        ctx.mark_completed()
        assert ctx.total_latency_ms > 0

    def test_perf_timer_more_accurate_than_wall_clock(self) -> None:
        ctx = PipelineContext(request_id="lat-2", user_query="test")
        ctx.start_timer()
        time.sleep(0.01)
        ctx.mark_completed()
        assert ctx.total_latency_ms >= 5.0

    def test_total_latency_stored_in_metadata(self) -> None:
        ctx = PipelineContext(request_id="lat-3", user_query="test")
        ctx.start_timer()
        ctx.mark_completed()
        assert "total_latency_ms" in ctx.metadata
        assert ctx.metadata["total_latency_ms"] == ctx.total_latency_ms

    def test_total_latency_on_terminated_early(self) -> None:
        ctx = PipelineContext(request_id="lat-4", user_query="test")
        ctx.start_timer()
        ctx.mark_terminated_early("cache_hit")
        assert ctx.total_latency_ms > 0
        assert ctx.status == PipelineStatus.TERMINATED_EARLY

    def test_total_latency_on_failed(self) -> None:
        ctx = PipelineContext(request_id="lat-5", user_query="test")
        ctx.start_timer()
        ctx.mark_failed("boom")
        assert ctx.total_latency_ms > 0
        assert ctx.status == PipelineStatus.FAILED

    def test_total_latency_without_perf_timer_falls_back(self) -> None:
        ctx = PipelineContext(request_id="lat-6", user_query="test")
        assert ctx.total_latency_ms >= 0

    def test_elapsed_ms_still_works(self) -> None:
        ctx = PipelineContext(
            request_id="lat-7", user_query="test", started_at=100.0
        )
        ctx.completed_at = 100.05
        assert ctx.elapsed_ms == 50.0

    def test_latency_not_negative(self) -> None:
        ctx = PipelineContext(request_id="lat-8", user_query="test")
        ctx.start_timer()
        ctx.mark_completed()
        assert ctx.total_latency_ms >= 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPROVEMENT 2: Checkpoint Creation & Logging
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCheckpointCreation:
    def test_checkpoint_returns_id_with_chk_prefix(self) -> None:
        mgr = CheckpointManager()
        ctx = PipelineContext(request_id="cp-1", user_query="test")
        ctx.current_stage = StageName.FAST_DETECTOR
        checkpoint_id = mgr.save_checkpoint(ctx)
        assert checkpoint_id.startswith("CHK-")

    def test_checkpoint_ids_are_sequential(self) -> None:
        mgr = CheckpointManager()
        ctx = PipelineContext(request_id="cp-2", user_query="test")
        ctx.current_stage = StageName.FAST_DETECTOR
        id1 = mgr.save_checkpoint(ctx)
        id2 = mgr.save_checkpoint(ctx)
        num1 = int(id1.split("-")[1])
        num2 = int(id2.split("-")[1])
        assert num2 == num1 + 1

    def test_checkpoint_increments_context_counter(self) -> None:
        mgr = CheckpointManager()
        ctx = PipelineContext(request_id="cp-3", user_query="test")
        ctx.current_stage = StageName.SECURITY
        assert ctx.checkpoints_created == 0
        mgr.save_checkpoint(ctx)
        assert ctx.checkpoints_created == 1
        mgr.save_checkpoint(ctx)
        assert ctx.checkpoints_created == 2

    def test_checkpoint_event_includes_id_and_stage(self) -> None:
        dispatcher = EventDispatcher()
        events: list[dict] = []
        dispatcher.subscribe(
            PipelineEvent.CHECKPOINT_CREATED, lambda e, d: events.append(d)
        )

        mgr = CheckpointManager(dispatcher=dispatcher)
        ctx = PipelineContext(request_id="cp-4", user_query="test")
        ctx.current_stage = StageName.SEMANTIC_CACHE
        mgr.save_checkpoint(ctx)

        assert len(events) == 1
        assert events[0]["checkpoint_id"].startswith("CHK-")
        assert events[0]["stage"] == "semantic_cache"
        assert events[0]["request_id"] == "cp-4"
        assert "timestamp" in events[0]
        assert "completed_stages" in events[0]

    def test_checkpoint_event_includes_completed_stages(self) -> None:
        dispatcher = EventDispatcher()
        events: list[dict] = []
        dispatcher.subscribe(
            PipelineEvent.CHECKPOINT_CREATED, lambda e, d: events.append(d)
        )

        mgr = CheckpointManager(dispatcher=dispatcher)
        ctx = PipelineContext(request_id="cp-5", user_query="test")
        ctx.execution_trace.add(
            StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=1.0)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.SECURITY, status=StageStatus.COMPLETED, latency_ms=2.0)
        )
        ctx.current_stage = StageName.SECURITY
        mgr.save_checkpoint(ctx)

        assert events[0]["completed_stages"] == ["fast_detector", "security"]

    def test_skipped_stage_does_not_create_checkpoint(self) -> None:
        from backend.app.pipeline.stage_executor import StageExecutor
        from backend.app.pipeline.retry_manager import RetryManager

        dispatcher = EventDispatcher()
        events: list[PipelineEvent] = []
        dispatcher.subscribe(
            PipelineEvent.CHECKPOINT_CREATED, lambda e, d: events.append(e)
        )

        mgr = CheckpointManager(dispatcher=dispatcher)
        retry = RetryManager()
        executor = StageExecutor(retry, mgr, dispatcher)
        ctx = PipelineContext(request_id="cp-6", user_query="test")
        executor.skip(StageName.CONTEXT_MANAGER, ctx)

        checkpoint_events = [e for e in events if e == PipelineEvent.CHECKPOINT_CREATED]
        assert len(checkpoint_events) == 0
        assert ctx.checkpoints_created == 0

    def test_checkpoint_data_is_restorable(self) -> None:
        backend = InMemoryCheckpointBackend()
        mgr = CheckpointManager(backend=backend)
        ctx = PipelineContext(request_id="cp-7", user_query="test query")
        ctx.current_stage = StageName.BUDGET
        ctx.security_result = SecurityResult(status=SecurityStatus.CLEAR, reason="ok")
        mgr.save_checkpoint(ctx)

        restored = mgr.load_checkpoint("cp-7")
        assert restored is not None
        assert restored.request_id == "cp-7"
        assert restored.checkpoints_created == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPROVEMENT 3: Pipeline Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPipelineSummary:
    def _make_full_context(self) -> PipelineContext:
        ctx = PipelineContext(request_id="sum-1", user_query="test")
        ctx.start_timer()
        ctx.execution_trace.add(
            StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=0.05)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.SECURITY, status=StageStatus.COMPLETED, latency_ms=0.03)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.TASK_ANALYZER, status=StageStatus.COMPLETED, latency_ms=0.11)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.DECISION_ENGINE, status=StageStatus.COMPLETED, latency_ms=0.10)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.BUDGET, status=StageStatus.COMPLETED, latency_ms=0.02)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.SEMANTIC_CACHE, status=StageStatus.COMPLETED, latency_ms=0.54)
        )
        ctx.cache_hit = True
        ctx.execution_trace.add(
            StageRecord(name=StageName.CONTEXT_MANAGER, status=StageStatus.SKIPPED)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.RESPONSE_GENERATION, status=StageStatus.SKIPPED)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.CACHE_STORE, status=StageStatus.SKIPPED)
        )
        ctx.checkpoints_created = 6
        ctx.mark_terminated_early("cache_hit")
        return ctx

    def test_build_summary_counts(self) -> None:
        ctx = self._make_full_context()
        summary = build_summary(ctx)
        assert summary.executed_count == 6
        assert summary.skipped_count == 3
        assert summary.failed_count == 0
        assert summary.checkpoints_created == 6

    def test_build_summary_status(self) -> None:
        ctx = self._make_full_context()
        summary = build_summary(ctx)
        assert summary.status == PipelineStatus.TERMINATED_EARLY
        assert summary.termination_reason == "cache_hit"

    def test_build_summary_latency(self) -> None:
        ctx = self._make_full_context()
        summary = build_summary(ctx)
        assert summary.total_latency_ms > 0

    def test_format_contains_stage_names(self) -> None:
        ctx = self._make_full_context()
        summary = build_summary(ctx)
        text = summary.format()
        assert "Fast Detector" in text
        assert "Security Scanner" in text
        assert "Semantic Cache" in text
        assert "Context Manager" in text

    def test_format_contains_status_icons(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "✓" in text
        assert "○" in text

    def test_format_contains_pipeline_status(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "SUCCESS" in text

    def test_format_contains_termination_reason(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "Semantic Cache HIT" in text

    def test_format_contains_counts(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "Executed Stages       6" in text
        assert "Skipped Stages        3" in text
        assert "Checkpoints Created   6" in text

    def test_format_shows_cache_hit_for_semantic_cache(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "Cache HIT" in text

    def test_format_shows_skipped_stages(self) -> None:
        ctx = self._make_full_context()
        text = build_summary(ctx).format()
        assert "SKIPPED" in text

    def test_summary_with_failed_stage(self) -> None:
        ctx = PipelineContext(request_id="sum-2", user_query="test")
        ctx.start_timer()
        ctx.execution_trace.add(
            StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=1.0)
        )
        ctx.execution_trace.add(
            StageRecord(
                name=StageName.SECURITY,
                status=StageStatus.FAILED,
                latency_ms=2.0,
                error="timeout",
            )
        )
        ctx.mark_failed("stage failed")
        summary = build_summary(ctx)
        assert summary.executed_count == 1
        assert summary.failed_count == 1
        text = summary.format()
        assert "✗" in text
        assert "FAILED" in text

    def test_summary_for_full_pipeline_no_cache_hit(self) -> None:
        ctx = PipelineContext(request_id="sum-3", user_query="test")
        ctx.start_timer()
        for stage in StageName:
            ctx.execution_trace.add(
                StageRecord(name=stage, status=StageStatus.COMPLETED, latency_ms=1.0)
            )
        ctx.checkpoints_created = 9
        ctx.mark_completed()
        summary = build_summary(ctx)
        assert summary.executed_count == 9
        assert summary.skipped_count == 0
        assert summary.termination_reason is None
        text = summary.format()
        assert "SUCCESS" in text
        assert "Termination Reason" not in text

    def test_summary_fast_response_termination(self) -> None:
        ctx = PipelineContext(request_id="sum-4", user_query="hello")
        ctx.start_timer()
        ctx.execution_trace.add(
            StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=0.5)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.SECURITY, status=StageStatus.COMPLETED, latency_ms=0.3)
        )
        for stage in [StageName.TASK_ANALYZER, StageName.DECISION_ENGINE, StageName.BUDGET,
                       StageName.SEMANTIC_CACHE, StageName.CONTEXT_MANAGER,
                       StageName.RESPONSE_GENERATION, StageName.CACHE_STORE]:
            ctx.execution_trace.add(StageRecord(name=stage, status=StageStatus.SKIPPED))
        ctx.checkpoints_created = 2
        ctx.mark_terminated_early("fast_response")
        summary = build_summary(ctx)
        assert summary.executed_count == 2
        assert summary.skipped_count == 7
        text = summary.format()
        assert "Fast Detector Response" in text

    def test_summary_security_blocked_termination(self) -> None:
        ctx = PipelineContext(request_id="sum-5", user_query="bad")
        ctx.start_timer()
        ctx.execution_trace.add(
            StageRecord(name=StageName.FAST_DETECTOR, status=StageStatus.COMPLETED, latency_ms=0.5)
        )
        ctx.execution_trace.add(
            StageRecord(name=StageName.SECURITY, status=StageStatus.COMPLETED, latency_ms=0.3)
        )
        ctx.checkpoints_created = 2
        ctx.mark_terminated_early("security_blocked")
        summary = build_summary(ctx)
        text = summary.format()
        assert "Security Blocked" in text
