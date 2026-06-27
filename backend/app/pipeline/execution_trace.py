"""Execution trace — ordered record of all stage executions for a request."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.pipeline.stage_status import StageRecord, StageName, StageStatus


class ExecutionTrace(BaseModel):
    """Ordered trace of all pipeline stage results."""

    model_config = ConfigDict()

    records: list[StageRecord] = Field(default_factory=list)

    def add(self, record: StageRecord) -> None:
        self.records.append(record)

    def get(self, name: StageName) -> StageRecord | None:
        for r in self.records:
            if r.name == name:
                return r
        return None

    @property
    def completed_stages(self) -> list[StageName]:
        return [r.name for r in self.records if r.status == StageStatus.COMPLETED]

    @property
    def failed_stages(self) -> list[StageName]:
        return [r.name for r in self.records if r.status == StageStatus.FAILED]

    @property
    def skipped_stages(self) -> list[StageName]:
        return [r.name for r in self.records if r.status == StageStatus.SKIPPED]

    @property
    def total_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self.records)

    def summary(self) -> list[dict[str, str | float | int | None]]:
        return [
            {
                "stage": r.name.value,
                "status": r.status.value,
                "latency_ms": r.latency_ms,
                "retry_count": r.retry_count,
                "error": r.error,
            }
            for r in self.records
        ]
