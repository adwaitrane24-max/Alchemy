"""Stage status and stage metadata for the pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StageName(StrEnum):
    FAST_DETECTOR = "fast_detector"
    SECURITY = "security"
    TASK_ANALYZER = "task_analyzer"
    DECISION_ENGINE = "decision_engine"
    BUDGET = "budget"
    SEMANTIC_CACHE = "semantic_cache"
    CONTEXT_MANAGER = "context_manager"
    RESPONSE_GENERATION = "response_generation"
    CACHE_STORE = "cache_store"


class StageRecord(BaseModel):
    """Immutable record of a single stage execution."""

    model_config = ConfigDict(frozen=True)

    name: StageName
    status: StageStatus
    latency_ms: float = Field(ge=0.0, default=0.0)
    retry_count: int = Field(ge=0, default=0)
    error: str | None = None
    checkpoint_time: float | None = None
