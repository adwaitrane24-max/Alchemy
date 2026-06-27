"""Pipeline summary — generates a structured execution report from PipelineContext."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from backend.app.pipeline.pipeline_context import PipelineContext, PipelineStatus
from backend.app.pipeline.stage_status import StageName, StageStatus

_STATUS_ICONS: dict[str, str] = {
    StageStatus.COMPLETED: "✓",
    StageStatus.SKIPPED: "○",
    StageStatus.FAILED: "✗",
}

_STAGE_DISPLAY_NAMES: dict[StageName, str] = {
    StageName.FAST_DETECTOR: "Fast Detector",
    StageName.SECURITY: "Security Scanner",
    StageName.TASK_ANALYZER: "Task Analyzer",
    StageName.DECISION_ENGINE: "Decision Engine",
    StageName.BUDGET: "Budget Manager",
    StageName.SEMANTIC_CACHE: "Semantic Cache",
    StageName.CONTEXT_MANAGER: "Context Manager",
    StageName.RESPONSE_GENERATION: "Response Generation",
    StageName.CACHE_STORE: "Cache Store",
}

_TERMINATION_REASONS: dict[str, str] = {
    "fast_response": "Fast Detector Response",
    "security_blocked": "Security Blocked",
    "cache_hit": "Semantic Cache HIT",
}


@dataclass(frozen=True)
class PipelineSummary:
    """Structured summary of a completed pipeline execution."""

    status: str
    termination_reason: str | None
    total_latency_ms: float
    executed_count: int
    skipped_count: int
    failed_count: int
    checkpoints_created: int
    stage_lines: list[str]

    def format(self) -> str:
        separator = "━" * 40
        thin_sep = "─" * 40
        lines = [
            "",
            separator,
            "  Pipeline Summary",
            separator,
        ]
        for line in self.stage_lines:
            lines.append(f"  {line}")

        lines.append(f"  {thin_sep}")

        pipeline_status = "SUCCESS" if self.status in (
            PipelineStatus.COMPLETED, PipelineStatus.TERMINATED_EARLY
        ) else self.status
        lines.append(f"  Pipeline Status       {pipeline_status}")

        if self.termination_reason:
            display_reason = _TERMINATION_REASONS.get(
                self.termination_reason, self.termination_reason
            )
            lines.append(f"  Termination Reason    {display_reason}")

        lines.append(f"  Total Latency         {self.total_latency_ms:.2f} ms")
        lines.append(f"  Executed Stages       {self.executed_count}")
        lines.append(f"  Skipped Stages        {self.skipped_count}")
        lines.append(f"  Checkpoints Created   {self.checkpoints_created}")
        lines.append(separator)
        lines.append("")
        return "\n".join(lines)


def build_summary(context: PipelineContext) -> PipelineSummary:
    """Build a PipelineSummary from a completed PipelineContext."""
    stage_lines: list[str] = []
    executed = 0
    skipped = 0
    failed = 0

    for record in context.execution_trace.records:
        icon = _STATUS_ICONS.get(record.status, "?")
        display_name = _STAGE_DISPLAY_NAMES.get(record.name, record.name.value)

        if record.status == StageStatus.COMPLETED:
            detail = "Completed"
            if record.name == StageName.SEMANTIC_CACHE and context.cache_hit:
                detail = "Cache HIT"
            stage_lines.append(
                f"{icon} {display_name:<22} {detail:<14} {record.latency_ms:.2f} ms"
            )
            executed += 1
        elif record.status == StageStatus.SKIPPED:
            stage_lines.append(f"{icon} {display_name:<22} SKIPPED")
            skipped += 1
        elif record.status == StageStatus.FAILED:
            stage_lines.append(
                f"{icon} {display_name:<22} FAILED         {record.latency_ms:.2f} ms"
            )
            failed += 1

    return PipelineSummary(
        status=context.status,
        termination_reason=context.termination_reason,
        total_latency_ms=context.total_latency_ms,
        executed_count=executed,
        skipped_count=skipped,
        failed_count=failed,
        checkpoints_created=context.checkpoints_created,
        stage_lines=stage_lines,
    )


def log_summary(context: PipelineContext) -> PipelineSummary:
    """Build and log the pipeline summary."""
    summary = build_summary(context)
    logger.info(summary.format())
    return summary
