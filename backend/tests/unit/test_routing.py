"""Unit tests for the rule-based routing engine."""

from __future__ import annotations

import pytest

from backend.app.constants.enums import (
    RoutingAction,
    SecurityStatus,
    TaskType,
    ThreatType,
)
from backend.app.constants.models import ModelID
from backend.app.models.analysis import FastDetectorResult, PromptAnalysis, SecurityResult
from backend.app.models.budget import BudgetSnapshot
from backend.app.routing import RoutingEngine


@pytest.fixture
def engine() -> RoutingEngine:
    return RoutingEngine()


@pytest.fixture
def healthy_budget() -> BudgetSnapshot:
    return BudgetSnapshot(daily_limit_usd=5.0, spent_usd=0.0)


@pytest.fixture
def clear() -> SecurityResult:
    return SecurityResult(status=SecurityStatus.CLEAR, reason="ok")


def test_security_block_short_circuits(
    engine: RoutingEngine, healthy_budget: BudgetSnapshot
) -> None:
    blocked = SecurityResult(
        status=SecurityStatus.BLOCK, threats=(ThreatType.INJECTION,), reason="bad"
    )
    decision = engine.decide(security=blocked, analysis=None, budget=healthy_budget)
    assert decision.action is RoutingAction.BLOCK
    assert decision.model is None


def test_fast_path_routes_to_local(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    fast = FastDetectorResult(is_fast_path=True, reason="greeting")
    decision = engine.decide(
        security=clear, analysis=None, budget=healthy_budget, fast_detector=fast
    )
    assert decision.action is RoutingAction.MODEL_CALL
    assert decision.model is ModelID.LOCAL_2B


def test_critical_budget_forces_local(engine: RoutingEngine, clear: SecurityResult) -> None:
    broke = BudgetSnapshot(daily_limit_usd=5.0, spent_usd=5.0)
    analysis = PromptAnalysis(
        task_type=TaskType.CODING, complexity=0.9, needs_coding=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=broke)
    assert decision.model is ModelID.LOCAL_2B


def test_high_complexity_routes_to_flagship(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.REASONING, complexity=0.9, needs_reasoning=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.GPT4O


def test_low_complexity_routes_to_local(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.1, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.LOCAL_2B


def test_vision_routes_to_flagship(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.GENERAL, complexity=0.2, needs_vision=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.GPT4O


def test_override_is_respected(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.1, reason="x")
    decision = engine.decide(
        security=clear, analysis=analysis, budget=healthy_budget, model_override="gpt4o"
    )
    assert decision.model is ModelID.GPT4O


def test_medium_complexity_has_fallback_chain(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.QA, complexity=0.5, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.GPT4O_MINI
    assert ModelID.LOCAL_2B in decision.fallback_chain
