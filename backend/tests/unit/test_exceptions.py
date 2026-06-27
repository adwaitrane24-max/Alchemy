"""Unit tests for the Alchemy exception hierarchy."""

from __future__ import annotations

import pytest

from backend.app.exceptions import (
    AlchemyError,
    BudgetExhaustedError,
    ContextOverflowError,
    ModelUnavailableError,
    SecurityBlockError,
    VoiceCaptureError,
)


def test_all_errors_inherit_alchemy_error() -> None:
    """Every domain exception derives from the common base."""
    for exc_type in (
        SecurityBlockError,
        BudgetExhaustedError,
        ModelUnavailableError,
        VoiceCaptureError,
        ContextOverflowError,
    ):
        assert issubclass(exc_type, AlchemyError)


def test_security_block_carries_threat_metadata() -> None:
    """SecurityBlockError exposes threat type, rule id, and error code."""
    err = SecurityBlockError(threat_type="injection", rule_id="R-101")

    assert err.threat_type == "injection"
    assert err.rule_id == "R-101"
    assert err.error_code == "E001"
    assert "injection" in str(err)


def test_budget_exhausted_error_code() -> None:
    """BudgetExhaustedError reports the E002 error code."""
    assert BudgetExhaustedError().error_code == "E002"


def test_model_unavailable_includes_model_and_reason() -> None:
    """ModelUnavailableError surfaces the model and reason in its message."""
    err = ModelUnavailableError(model="gpt4o", reason="timeout")

    assert err.model == "gpt4o"
    assert err.error_code == "E003"
    assert "gpt4o" in str(err)
    assert "timeout" in str(err)


def test_context_overflow_reports_counts() -> None:
    """ContextOverflowError captures token count and limit."""
    err = ContextOverflowError(token_count=9000, limit=8192)

    assert err.token_count == 9000
    assert err.limit == 8192
    assert err.error_code == "E006"


def test_base_error_is_catchable_as_exception() -> None:
    """AlchemyError behaves as a standard Exception."""
    with pytest.raises(Exception, match="boom"):
        raise AlchemyError("boom")
