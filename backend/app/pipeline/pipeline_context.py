"""Pipeline context — shared state for a single request traversing the pipeline."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.constants.models import ModelID
from backend.app.models.analysis import FastDetectorResult, PromptAnalysis, SecurityResult
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.routing import RoutingDecision
from backend.app.pipeline.execution_trace import ExecutionTrace
from backend.app.pipeline.stage_status import StageName, StageStatus


class PipelineStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED_EARLY = "TERMINATED_EARLY"


class PipelineContext(BaseModel):
    """Mutable state bag carried through the entire pipeline for one request."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identity
    request_id: str
    session_id: str | None = None
    user_query: str

    # Pipeline state
    current_stage: StageName | None = None
    status: str = PipelineStatus.PENDING
    retry_count: int = 0

    # Timestamps
    started_at: float = Field(default_factory=time.time)
    completed_at: float | None = None

    # Stage results — each module writes only its own field
    fast_detector_result: FastDetectorResult | None = None
    security_result: SecurityResult | None = None
    analysis_result: PromptAnalysis | None = None
    budget_snapshot: BudgetSnapshot | None = None
    routing_decision: RoutingDecision | None = None
    cache_hit: bool | None = None
    cache_response_text: str | None = None
    cache_model_used: ModelID | None = None
    context_result: Any | None = None
    response_text: str | None = None
    response_model: ModelID | None = None
    response_cost_usd: float = 0.0
    response_prompt_tokens: int = 0
    response_completion_tokens: int = 0
    response_latency_ms: float = 0.0

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_override: str | None = None
    economic_mode: bool = False

    # Execution trace
    execution_trace: ExecutionTrace = Field(default_factory=ExecutionTrace)

    def mark_running(self, stage: StageName) -> None:
        self.current_stage = stage
        self.status = PipelineStatus.RUNNING

    def mark_completed(self) -> None:
        self.status = PipelineStatus.COMPLETED
        self.completed_at = time.time()

    def mark_failed(self, error: str) -> None:
        self.status = PipelineStatus.FAILED
        self.completed_at = time.time()
        self.metadata["terminal_error"] = error

    def mark_terminated_early(self, reason: str) -> None:
        self.status = PipelineStatus.TERMINATED_EARLY
        self.completed_at = time.time()
        self.metadata["early_termination_reason"] = reason

    @property
    def elapsed_ms(self) -> float:
        end = self.completed_at or time.time()
        return round((end - self.started_at) * 1000, 3)

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, data: str) -> PipelineContext:
        return cls.model_validate_json(data)
