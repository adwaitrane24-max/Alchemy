"""Pipeline-specific exceptions."""

from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline errors."""

    def __init__(self, message: str, stage: str | None = None) -> None:
        self.stage = stage
        super().__init__(message)


class StageExecutionError(PipelineError):
    """Raised when a stage fails after exhausting retries."""


class CheckpointError(PipelineError):
    """Raised when checkpoint save/load fails."""


class StageTimeoutError(PipelineError):
    """Raised when a stage exceeds its timeout."""


class PipelineTerminated(PipelineError):
    """Raised to signal early pipeline termination (not an error)."""
