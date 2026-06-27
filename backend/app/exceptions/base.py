"""Base exception hierarchy for the Alchemy gateway pipeline."""

from __future__ import annotations


class AlchemyError(Exception):
    """Base exception for all Alchemy errors."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)


class SecurityBlockError(AlchemyError):
    """Raised when a prompt is blocked by the security module."""

    def __init__(self, threat_type: str, rule_id: str | None = None) -> None:
        self.threat_type = threat_type
        self.rule_id = rule_id
        super().__init__(
            f"Security block: {threat_type}",
            error_code="E001",
        )


class BudgetExhaustedError(AlchemyError):
    """Raised when the budget is exhausted and no model can serve the request."""

    def __init__(self) -> None:
        super().__init__(
            "Daily budget exhausted",
            error_code="E002",
        )


class ModelUnavailableError(AlchemyError):
    """Raised when the target model and all fallbacks are unavailable."""

    def __init__(self, model: str, reason: str = "") -> None:
        self.model = model
        super().__init__(
            f"Model unavailable: {model}. {reason}".strip(),
            error_code="E003",
        )


class VoiceCaptureError(AlchemyError):
    """Raised when voice capture fails after all retries."""

    def __init__(self) -> None:
        super().__init__(
            "Voice capture failed after retries",
            error_code="E004",
        )


class ContextOverflowError(AlchemyError):
    """Raised when context exceeds model limits after all compression attempts."""

    def __init__(self, token_count: int, limit: int) -> None:
        self.token_count = token_count
        self.limit = limit
        super().__init__(
            f"Context overflow: {token_count} tokens exceeds {limit} limit",
            error_code="E006",
        )
