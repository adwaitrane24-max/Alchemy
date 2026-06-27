"""Error codes as defined in the PRD Section 8.2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    """Structured error code with recovery guidance."""

    code: str
    meaning: str
    recovery: str


SECURITY_BLOCK = ErrorCode(
    code="E001",
    meaning="Security block",
    recovery="Return error message to user",
)

BUDGET_EXHAUSTED = ErrorCode(
    code="E002",
    meaning="Budget exhausted",
    recovery="Force local model or reject",
)

MODEL_UNAVAILABLE = ErrorCode(
    code="E003",
    meaning="Model unavailable",
    recovery="Fallback chain",
)

VOICE_CAPTURE_FAILURE = ErrorCode(
    code="E004",
    meaning="Voice capture failure",
    recovery="Retry 3x, then fallback to text",
)

PROMPT_STRUCTURER_FAILURE = ErrorCode(
    code="E005",
    meaning="Prompt structurer failure",
    recovery="Use original prompt",
)

CONTEXT_OVERFLOW = ErrorCode(
    code="E006",
    meaning="Context overflow",
    recovery="Truncate and warn user",
)

CACHE_LOOKUP_ERROR = ErrorCode(
    code="E007",
    meaning="Cache lookup error",
    recovery="Skip cache, proceed",
)

LEARNING_LAYER_FAILURE = ErrorCode(
    code="E008",
    meaning="Learning layer write failure",
    recovery="Log warning, continue (non-blocking)",
)
