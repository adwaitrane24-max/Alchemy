"""Unit tests for the shared pipeline data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.constants.enums import (
    BudgetState,
    RoutingAction,
    SecurityStatus,
    TaskType,
    ThreatType,
)
from backend.app.constants.models import ModelID
from backend.app.models import (
    BudgetSnapshot,
    PromptAnalysis,
    PromptRequest,
    PromptResponse,
    RoutingDecision,
    SecurityResult,
)


def test_prompt_request_generates_id_and_word_count() -> None:
    req = PromptRequest(prompt="hello there friend")
    assert req.request_id
    assert req.word_count == 3


def test_prompt_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="")


def test_prompt_request_is_frozen() -> None:
    req = PromptRequest(prompt="hi")
    with pytest.raises(ValidationError):
        req.prompt = "changed"


def test_security_result_is_blocked_helper() -> None:
    blocked = SecurityResult(
        status=SecurityStatus.BLOCK,
        threats=(ThreatType.INJECTION,),
        reason="injection detected",
    )
    clear = SecurityResult(status=SecurityStatus.CLEAR, reason="clean")
    assert blocked.is_blocked is True
    assert clear.is_blocked is False


def test_prompt_analysis_complexity_bounds() -> None:
    with pytest.raises(ValidationError):
        PromptAnalysis(task_type=TaskType.GENERAL, complexity=1.5, reason="x")


@pytest.mark.parametrize(
    ("spent", "expected"),
    [
        (0.0, BudgetState.HEALTHY),
        (3.5, BudgetState.LOW),
        (4.5, BudgetState.CRITICAL),
    ],
)
def test_budget_snapshot_state_transitions(spent: float, expected: BudgetState) -> None:
    snap = BudgetSnapshot(
        daily_limit_usd=5.0,
        spent_usd=spent,
        warning_threshold=0.60,
        critical_threshold=0.85,
    )
    assert snap.state is expected


def test_budget_snapshot_fraction_and_remaining_clamped() -> None:
    snap = BudgetSnapshot(daily_limit_usd=5.0, spent_usd=10.0)
    assert snap.fraction_used == 1.0
    assert snap.remaining_usd == 0.0


def test_routing_decision_defaults() -> None:
    decision = RoutingDecision(action=RoutingAction.BLOCK, reason="blocked")
    assert decision.model is None
    assert decision.estimated_cost_usd == 0.0
    assert decision.fallback_chain == ()


def test_prompt_response_total_tokens() -> None:
    resp = PromptResponse(
        request_id="abc",
        text="hi",
        model=ModelID.LOCAL_2B,
        prompt_tokens=10,
        completion_tokens=5,
    )
    assert resp.total_tokens == 15
