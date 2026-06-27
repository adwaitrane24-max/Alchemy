"""Rule-based routing engine.

Combines the security verdict, fast-detector result, task analysis, and budget
state into an explainable :class:`RoutingDecision`. It selects a model and a
fallback chain but never calls a model itself.
"""

from __future__ import annotations

from loguru import logger

from backend.app.constants.enums import BudgetState, RoutingAction
from backend.app.constants.models import MODEL_COSTS, MODEL_FALLBACK_CHAIN, ModelID
from backend.app.constants.thresholds import (
    COMPLEXITY_HIGH_THRESHOLD,
    COMPLEXITY_LOW_THRESHOLD,
)
from backend.app.models.analysis import (
    FastDetectorResult,
    PromptAnalysis,
    SecurityResult,
)
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.routing import RoutingDecision

# Rough token estimate for cost projection in the absence of real tokenization.
_ESTIMATED_COMPLETION_TOKENS = 256


class RoutingEngine:
    """Selects the most appropriate model for a request via deterministic rules."""

    def decide(
        self,
        *,
        security: SecurityResult,
        analysis: PromptAnalysis | None,
        budget: BudgetSnapshot,
        fast_detector: FastDetectorResult | None = None,
        prompt_tokens: int = 0,
        model_override: str | None = None,
    ) -> RoutingDecision:
        """Produce a routing decision from the upstream pipeline signals.

        Precedence: security block → explicit override → fast-path local →
        budget-constrained selection → complexity/capability-based selection.

        Args:
            security: Output of the security scanner.
            analysis: Output of the task analyzer (None on the fast path).
            budget: Current budget snapshot.
            fast_detector: Output of the fast detector, if it ran.
            prompt_tokens: Estimated prompt token count for cost projection.
            model_override: Optional caller-forced model id.

        Returns:
            An explainable :class:`RoutingDecision`.
        """
        # 1. Security always wins.
        if security.is_blocked:
            return RoutingDecision(
                action=RoutingAction.BLOCK,
                model=None,
                reason=f"Blocked by security: {security.reason}",
            )

        # 2. Explicit override (validated against known models).
        if model_override:
            model = self._coerce_model(model_override)
            if model is not None:
                return self._model_call(model, prompt_tokens, f"Caller override → {model.value}")
            logger.warning("Unknown model_override '{}', ignoring", model_override)

        # 3. Fast path → cheapest local model.
        if fast_detector is not None and fast_detector.is_fast_path:
            return self._model_call(
                ModelID.LOCAL_2B,
                prompt_tokens,
                f"Fast path ({fast_detector.reason}) → local 2B",
            )

        # 4. Budget exhausted → force local.
        if budget.state is BudgetState.CRITICAL or budget.remaining_usd <= 0.0:
            return self._model_call(
                ModelID.LOCAL_2B,
                prompt_tokens,
                f"Budget {budget.state.value} → force local 2B",
            )

        # 5. Capability/complexity-based selection.
        model, reason = self._select_by_analysis(analysis, budget)
        return self._model_call(model, prompt_tokens, reason)

    def _select_by_analysis(
        self, analysis: PromptAnalysis | None, budget: BudgetSnapshot
    ) -> tuple[ModelID, str]:
        """Choose a model from task analysis and budget pressure."""
        if analysis is None:
            return ModelID.GPT4O_MINI, "No analysis available → balanced mini"

        # Vision is only supported by the flagship model.
        if analysis.needs_vision:
            return ModelID.GPT4O, "Vision required → GPT-4o"

        high = analysis.complexity >= COMPLEXITY_HIGH_THRESHOLD
        low = analysis.complexity < COMPLEXITY_LOW_THRESHOLD
        heavy_capability = (
            analysis.needs_reasoning or analysis.needs_coding or analysis.needs_planning
        )

        # Under budget pressure (LOW), avoid the flagship model.
        budget_pressured = budget.state is BudgetState.LOW

        if high and heavy_capability and not budget_pressured:
            return ModelID.GPT4O, (
                f"High complexity ({analysis.complexity:.2f}) + heavy capability → GPT-4o"
            )
        if low and not heavy_capability:
            return ModelID.LOCAL_2B, (f"Low complexity ({analysis.complexity:.2f}) → local 2B")
        return ModelID.GPT4O_MINI, (
            f"Medium complexity ({analysis.complexity:.2f})"
            + (" under budget pressure" if budget_pressured else "")
            + " → GPT-4o-mini"
        )

    def _model_call(self, model: ModelID, prompt_tokens: int, reason: str) -> RoutingDecision:
        """Build a MODEL_CALL decision with cost estimate and fallback chain."""
        cost = self._estimate_cost(model, prompt_tokens)
        chain = tuple(ModelID(m) for m in MODEL_FALLBACK_CHAIN.get(model, []))
        logger.debug("Routing → {} (${:.5f}) :: {}", model.value, cost, reason)
        return RoutingDecision(
            action=RoutingAction.MODEL_CALL,
            model=model,
            reason=reason,
            estimated_cost_usd=cost,
            fallback_chain=chain,
        )

    @staticmethod
    def _estimate_cost(model: ModelID, prompt_tokens: int) -> float:
        """Estimate USD cost for a call using static per-1K-token pricing."""
        costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        prompt_cost = (prompt_tokens / 1000.0) * costs["input"]
        completion_cost = (_ESTIMATED_COMPLETION_TOKENS / 1000.0) * costs["output"]
        return round(prompt_cost + completion_cost, 6)

    @staticmethod
    def _coerce_model(value: str) -> ModelID | None:
        """Map a friendly override alias to a ModelID, or None if unknown."""
        aliases = {
            "local": ModelID.LOCAL_2B,
            "local_2b": ModelID.LOCAL_2B,
            "mini": ModelID.GPT4O_MINI,
            "gpt4o_mini": ModelID.GPT4O_MINI,
            "gpt4o": ModelID.GPT4O,
            "gpt-4o": ModelID.GPT4O,
        }
        return aliases.get(value.strip().lower())
