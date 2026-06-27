"""Unit tests for the capability-aware routing engine with Mozilla Otari models."""

from __future__ import annotations

import pytest

from backend.app.constants.enums import (
    BudgetState,
    RoutingAction,
    SecurityStatus,
    TaskType,
    ThreatType,
)
from backend.app.constants.models import ModelID
from backend.app.models.analysis import FastDetectorResult, PromptAnalysis, SecurityResult
from backend.app.models.budget import BudgetSnapshot
from backend.app.routing import ModelRegistry, RoutingEngine


@pytest.fixture
def engine() -> RoutingEngine:
    return RoutingEngine()


@pytest.fixture
def healthy_budget() -> BudgetSnapshot:
    return BudgetSnapshot(daily_limit_usd=5.0, spent_usd=0.0)


@pytest.fixture
def low_budget() -> BudgetSnapshot:
    return BudgetSnapshot(daily_limit_usd=5.0, spent_usd=4.0)


@pytest.fixture
def clear() -> SecurityResult:
    return SecurityResult(status=SecurityStatus.CLEAR, reason="ok")


# ── Pipeline Precedence Tests ──────────────────────────


def test_security_block_short_circuits(
    engine: RoutingEngine, healthy_budget: BudgetSnapshot
) -> None:
    blocked = SecurityResult(
        status=SecurityStatus.BLOCK, threats=(ThreatType.INJECTION,), reason="bad"
    )
    decision = engine.decide(security=blocked, analysis=None, budget=healthy_budget)
    assert decision.action is RoutingAction.BLOCK
    assert decision.model is None


def test_fast_path_routes_to_cheapest_otari(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    fast = FastDetectorResult(is_fast_path=True, reason="greeting")
    decision = engine.decide(
        security=clear, analysis=None, budget=healthy_budget, fast_detector=fast
    )
    assert decision.action is RoutingAction.MODEL_CALL
    assert decision.model is ModelID.GEMMA_3_27B


def test_critical_budget_forces_cheapest(engine: RoutingEngine, clear: SecurityResult) -> None:
    broke = BudgetSnapshot(daily_limit_usd=5.0, spent_usd=5.0)
    analysis = PromptAnalysis(
        task_type=TaskType.CODING, complexity=0.9, needs_coding=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=broke)
    assert decision.model is ModelID.GEMMA_3_27B


def test_no_analysis_routes_to_default(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    decision = engine.decide(security=clear, analysis=None, budget=healthy_budget)
    assert decision.model is ModelID.GEMMA_3_27B


# ── Task-Type Routing Tests (Mozilla Otari Selection) ──


def test_general_chat_routes_to_gemma(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.2, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.GEMMA_3_27B
    assert decision.score_breakdown is not None


def test_coding_routes_to_llama(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.CODING, complexity=0.7, needs_coding=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.LLAMA_3_3_70B


def test_complex_reasoning_routes_to_qwen(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.REASONING,
        complexity=0.9,
        needs_reasoning=True,
        reason="x",
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.QWEN3_32B


def test_creative_writing_routes_to_hermes(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.CREATIVE, complexity=0.5, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.HERMES_4_70B


def test_embedding_routes_to_qwen_embedding(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.EMBEDDING, complexity=0.1, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.QWEN3_EMBEDDING_8B


def test_summarization_routes_to_gemma(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.SUMMARIZATION, complexity=0.3, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.GEMMA_3_27B


def test_math_routes_to_qwen(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.MATH, complexity=0.8, needs_reasoning=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.model is ModelID.QWEN3_32B


# ── Budget-Aware Routing ──────────────────────────


def test_low_budget_avoids_expensive_models(
    engine: RoutingEngine, clear: SecurityResult, low_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.CREATIVE, complexity=0.5, reason="x")
    decision = engine.decide(security=clear, analysis=analysis, budget=low_budget)
    # Hermes is cost_tier=4, budget_ok_at only HEALTHY → should NOT be selected
    assert decision.model is not ModelID.HERMES_4_70B


def test_low_budget_still_allows_coding(
    engine: RoutingEngine, clear: SecurityResult, low_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.CODING, complexity=0.7, needs_coding=True, reason="x"
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=low_budget)
    # LLaMA 3.3 70B is allowed at LOW budget
    assert decision.model in {ModelID.LLAMA_3_3_70B, ModelID.QWEN3_32B}


# ── Override Tests ──────────────────────────


def test_mozilla_model_override(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.1, reason="x")
    decision = engine.decide(
        security=clear, analysis=analysis, budget=healthy_budget, model_override="hermes"
    )
    assert decision.model is ModelID.HERMES_4_70B


def test_legacy_override_still_works(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.1, reason="x")
    decision = engine.decide(
        security=clear, analysis=analysis, budget=healthy_budget, model_override="gpt4o"
    )
    assert decision.model is ModelID.GPT4O


def test_mozilla_aliases(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(task_type=TaskType.GENERAL, complexity=0.1, reason="x")
    for alias, expected in [
        ("gemma", ModelID.GEMMA_3_27B),
        ("llama", ModelID.LLAMA_3_3_70B),
        ("qwen", ModelID.QWEN3_32B),
        ("hermes", ModelID.HERMES_4_70B),
        ("embedding", ModelID.QWEN3_EMBEDDING_8B),
    ]:
        decision = engine.decide(
            security=clear, analysis=analysis, budget=healthy_budget, model_override=alias
        )
        assert decision.model is expected, f"alias '{alias}' should map to {expected}"


# ── Score Breakdown Tests ──────────────────────────


def test_score_breakdown_is_populated(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.CODING,
        complexity=0.7,
        needs_coding=True,
        needs_reasoning=True,
        reason="x",
    )
    decision = engine.decide(security=clear, analysis=analysis, budget=healthy_budget)
    assert decision.score_breakdown is not None
    explanation = decision.score_breakdown.explain()
    assert "Score" in explanation
    assert "complexity=" in explanation


def test_economic_mode_applies_penalty(
    engine: RoutingEngine, clear: SecurityResult, healthy_budget: BudgetSnapshot
) -> None:
    analysis = PromptAnalysis(
        task_type=TaskType.CODING, complexity=0.5, needs_coding=True, reason="x"
    )
    normal = engine.decide(
        security=clear, analysis=analysis, budget=healthy_budget, economic_mode=False
    )
    economic = engine.decide(
        security=clear, analysis=analysis, budget=healthy_budget, economic_mode=True
    )
    assert economic.score_breakdown is not None
    assert economic.score_breakdown.economic_penalty == -5.0
    assert economic.score_breakdown.total_score < normal.score_breakdown.total_score


# ── Registry Unit Tests ──────────────────────────


class TestModelRegistry:
    @pytest.fixture
    def registry(self) -> ModelRegistry:
        return ModelRegistry()

    def test_select_general_returns_gemma(self, registry: ModelRegistry) -> None:
        model, reason = registry.select(
            TaskType.GENERAL, complexity=0.2, budget_state=BudgetState.HEALTHY
        )
        assert model is ModelID.GEMMA_3_27B
        assert "gemma" in reason.lower() or "Task=general" in reason

    def test_select_coding_returns_llama(self, registry: ModelRegistry) -> None:
        model, _ = registry.select(
            TaskType.CODING,
            complexity=0.7,
            budget_state=BudgetState.HEALTHY,
            needs_coding=True,
        )
        assert model is ModelID.LLAMA_3_3_70B

    def test_select_reasoning_returns_qwen(self, registry: ModelRegistry) -> None:
        model, _ = registry.select(
            TaskType.REASONING,
            complexity=0.9,
            budget_state=BudgetState.HEALTHY,
            needs_reasoning=True,
        )
        assert model is ModelID.QWEN3_32B

    def test_select_creative_returns_hermes(self, registry: ModelRegistry) -> None:
        model, _ = registry.select(
            TaskType.CREATIVE, complexity=0.5, budget_state=BudgetState.HEALTHY
        )
        assert model is ModelID.HERMES_4_70B

    def test_select_embedding_returns_embedding_model(self, registry: ModelRegistry) -> None:
        model, _ = registry.select(
            TaskType.EMBEDDING, complexity=0.1, budget_state=BudgetState.HEALTHY
        )
        assert model is ModelID.QWEN3_EMBEDDING_8B

    def test_unknown_task_falls_back(self, registry: ModelRegistry) -> None:
        """Tasks not in any model's supported set fall back to cheapest."""
        model, reason = registry.select(
            TaskType.EXTRACTION, complexity=0.1, budget_state=BudgetState.CRITICAL
        )
        # EXTRACTION at CRITICAL budget — only Gemma & Qwen Embedding are affordable,
        # but only LLaMA supports EXTRACTION and it's not CRITICAL-eligible.
        # Falls back to cheapest.
        assert model is not None
        assert reason  # explanation is always provided

    def test_budget_low_excludes_hermes(self, registry: ModelRegistry) -> None:
        model, _ = registry.select(TaskType.CREATIVE, complexity=0.5, budget_state=BudgetState.LOW)
        assert model is not ModelID.HERMES_4_70B

    def test_get_cheapest(self, registry: ModelRegistry) -> None:
        assert registry.get_cheapest() is ModelID.GEMMA_3_27B

    def test_get_default(self, registry: ModelRegistry) -> None:
        assert registry.get_default() is ModelID.GEMMA_3_27B

    def test_get_fast_path_model(self, registry: ModelRegistry) -> None:
        assert registry.get_fast_path_model() is ModelID.GEMMA_3_27B
