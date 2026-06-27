"""Custom exception classes — structured error hierarchy for the gateway pipeline."""

from __future__ import annotations

from backend.app.exceptions.base import (
    AlchemyError,
    BudgetExhaustedError,
    ContextOverflowError,
    ModelUnavailableError,
    SecurityBlockError,
    VoiceCaptureError,
)

__all__ = [
    "AlchemyError",
    "BudgetExhaustedError",
    "ContextOverflowError",
    "ModelUnavailableError",
    "SecurityBlockError",
    "VoiceCaptureError",
]
