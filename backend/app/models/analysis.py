"""Analysis models — outputs of the fast detector, security, and task analyzer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.constants.enums import (
    FastRequestCategory,
    SecurityStatus,
    TaskType,
    ThreatType,
)


class FastDetectorResult(BaseModel):
    """Result of the rule-based fast request detector.

    When ``is_fast_path`` is True the request is trivial (greeting, thanks,
    simple arithmetic, very short) and may bypass the full pipeline.
    """

    model_config = ConfigDict(frozen=True)

    is_fast_path: bool
    category: FastRequestCategory | None = None
    reason: str = Field(description="Human-readable explanation of the decision.")
    canned_response: str | None = Field(
        default=None, description="Pre-computed reply for trivial prompts, if any."
    )


class SecurityResult(BaseModel):
    """Result of the rule-based security screen."""

    model_config = ConfigDict(frozen=True)

    status: SecurityStatus
    threats: tuple[ThreatType, ...] = Field(default_factory=tuple)
    matched_rules: tuple[str, ...] = Field(default_factory=tuple)
    reason: str = Field(description="Human-readable explanation of the decision.")

    @property
    def is_blocked(self) -> bool:
        """True when the request must not proceed."""
        return self.status is SecurityStatus.BLOCK


class PromptAnalysis(BaseModel):
    """Structured classification of a prompt produced by the task analyzer."""

    model_config = ConfigDict(frozen=True)

    task_type: TaskType
    complexity: float = Field(ge=0.0, le=1.0, description="Normalized difficulty score.")
    needs_reasoning: bool = False
    needs_coding: bool = False
    needs_planning: bool = False
    needs_context: bool = False
    needs_vision: bool = False
    reason: str = Field(description="Human-readable explanation of the classification.")
