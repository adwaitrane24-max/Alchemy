"""Model Capability Registry — data-driven model selection for Mozilla Otari.

Each model is described by a :class:`ModelCapability` entry that encodes its
supported task types, complexity ceiling, strengths, estimated latency, and
cost tier. The :class:`ModelRegistry` selects the best model for a given task
and budget state by filtering, scoring, and ranking candidates.

Adding a new Mozilla model requires only a new entry in ``_OTARI_MODELS``.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from backend.app.constants.enums import BudgetState, TaskType
from backend.app.constants.models import ModelID


@dataclass(frozen=True)
class ModelCapability:
    """Describes what a single model can do and how expensive it is."""

    model_id: ModelID
    supported_tasks: frozenset[TaskType]
    max_complexity: float
    strengths: tuple[str, ...]
    estimated_latency_ms: int
    cost_tier: int  # 1=cheapest, 5=most expensive
    budget_ok_at: frozenset[BudgetState]


# ── Mozilla Otari Model Registry ────────────────────────
# Adding a new Mozilla model? Just add an entry here.

_OTARI_MODELS: tuple[ModelCapability, ...] = (
    ModelCapability(
        model_id=ModelID.GEMMA_3_27B,
        supported_tasks=frozenset(
            {
                TaskType.GENERAL,
                TaskType.CONVERSATION,
                TaskType.SUMMARIZATION,
                TaskType.QA,
                TaskType.CLASSIFICATION,
                TaskType.PLANNING,
            }
        ),
        max_complexity=0.55,
        strengths=("general chat", "summarization", "classification", "lightweight"),
        estimated_latency_ms=200,
        cost_tier=1,
        budget_ok_at=frozenset({BudgetState.HEALTHY, BudgetState.LOW, BudgetState.CRITICAL}),
    ),
    ModelCapability(
        model_id=ModelID.LLAMA_3_3_70B,
        supported_tasks=frozenset(
            {
                TaskType.CODING,
                TaskType.REASONING,
                TaskType.PLANNING,
                TaskType.MATH,
                TaskType.QA,
                TaskType.GENERAL,
                TaskType.EXTRACTION,
                TaskType.CLASSIFICATION,
            }
        ),
        max_complexity=0.90,
        strengths=("coding", "instruction following", "structured output", "math"),
        estimated_latency_ms=600,
        cost_tier=3,
        budget_ok_at=frozenset({BudgetState.HEALTHY, BudgetState.LOW}),
    ),
    ModelCapability(
        model_id=ModelID.QWEN3_32B,
        supported_tasks=frozenset(
            {
                TaskType.REASONING,
                TaskType.MATH,
                TaskType.PLANNING,
                TaskType.CODING,
                TaskType.QA,
                TaskType.GENERAL,
                TaskType.EXTRACTION,
            }
        ),
        max_complexity=1.0,
        strengths=("complex reasoning", "multi-step logic", "math proofs", "chain of thought"),
        estimated_latency_ms=800,
        cost_tier=3,
        budget_ok_at=frozenset({BudgetState.HEALTHY, BudgetState.LOW}),
    ),
    ModelCapability(
        model_id=ModelID.HERMES_4_70B,
        supported_tasks=frozenset(
            {
                TaskType.CREATIVE,
                TaskType.CONVERSATION,
                TaskType.GENERAL,
                TaskType.SUMMARIZATION,
                TaskType.QA,
            }
        ),
        max_complexity=0.85,
        strengths=("creative writing", "narrative", "roleplay", "long-form"),
        estimated_latency_ms=700,
        cost_tier=4,
        budget_ok_at=frozenset({BudgetState.HEALTHY}),
    ),
    ModelCapability(
        model_id=ModelID.QWEN3_EMBEDDING_8B,
        supported_tasks=frozenset({TaskType.EMBEDDING}),
        max_complexity=0.3,
        strengths=("embedding generation", "semantic search", "vector representation"),
        estimated_latency_ms=100,
        cost_tier=1,
        budget_ok_at=frozenset({BudgetState.HEALTHY, BudgetState.LOW, BudgetState.CRITICAL}),
    ),
)

# The cheapest Otari model, used as the absolute fallback.
_CHEAPEST_OTARI = ModelID.GEMMA_3_27B

# Default model when no analysis is available.
_DEFAULT_MODEL = ModelID.GEMMA_3_27B


class ModelRegistry:
    """Registry-driven capability-aware model selector.

    Given a task type, complexity, and budget state, the registry filters
    eligible models, scores them by capability fit, and returns the best match.
    """

    def __init__(self, models: tuple[ModelCapability, ...] = _OTARI_MODELS) -> None:
        self._models = models
        self._by_id: dict[ModelID, ModelCapability] = {m.model_id: m for m in models}

    def select(
        self,
        task_type: TaskType,
        complexity: float,
        budget_state: BudgetState,
        *,
        needs_coding: bool = False,
        needs_reasoning: bool = False,
        prefer_low_latency: bool = False,
    ) -> tuple[ModelID, str]:
        """Select the best Mozilla Otari model for a request.

        Args:
            task_type: Classified task type from the analyzer.
            complexity: Normalized complexity score (0.0-1.0).
            budget_state: Current budget state.
            needs_coding: True if the task requires code generation.
            needs_reasoning: True if the task requires complex reasoning.
            prefer_low_latency: When True, lighter models are preferred.

        Returns:
            A tuple of (selected ModelID, human-readable reason string).
        """
        # 1. Filter candidates: must support the task and be affordable.
        candidates = [
            m
            for m in self._models
            if task_type in m.supported_tasks and budget_state in m.budget_ok_at
        ]

        if not candidates:
            reason = (
                f"No model supports task={task_type.value} at budget={budget_state.value} "
                f"→ fallback {_CHEAPEST_OTARI.value}"
            )
            logger.warning(reason)
            return _CHEAPEST_OTARI, reason

        # 2. Score each candidate.
        scored: list[tuple[ModelCapability, float, str]] = []
        for cap in candidates:
            score, detail = self._score_candidate(
                cap,
                task_type,
                complexity,
                needs_coding=needs_coding,
                needs_reasoning=needs_reasoning,
                prefer_low_latency=prefer_low_latency,
            )
            scored.append((cap, score, detail))

        # 3. Pick highest score; break ties by lower cost tier.
        scored.sort(key=lambda t: (-t[1], t[0].cost_tier))
        winner, best_score, detail = scored[0]

        reason = (
            f"Task={task_type.value}, Complexity={complexity:.2f}, "
            f"Budget={budget_state.value} → {winner.model_id.value} "
            f"(fit={best_score:.0f}, {detail})"
        )
        logger.info(
            "Selected Model: {} | Reason: {} | Capability Match: {:.0f}",
            winner.model_id.value,
            reason,
            best_score,
        )
        return winner.model_id, reason

    def get_default(self) -> ModelID:
        """Return the default model when no analysis is available."""
        return _DEFAULT_MODEL

    def get_cheapest(self) -> ModelID:
        """Return the cheapest Otari model for budget-critical fallback."""
        return _CHEAPEST_OTARI

    def get_fast_path_model(self) -> ModelID:
        """Return the model used for fast-path trivial requests."""
        return _CHEAPEST_OTARI

    def _score_candidate(
        self,
        cap: ModelCapability,
        task_type: TaskType,
        complexity: float,
        *,
        needs_coding: bool,
        needs_reasoning: bool,
        prefer_low_latency: bool,
    ) -> tuple[float, str]:
        """Score a candidate model on [0, 100] for the given request."""
        score = 0.0
        parts: list[str] = []

        # Task support (40 points) — all candidates already pass this filter,
        # but award bonus for strength alignment.
        task_points = 40.0
        task_value = task_type.value
        if any(task_value in s for s in cap.strengths):
            task_points += 10.0
            parts.append("strength_match")
        score += task_points

        # Complexity headroom (25 points) — prefer models whose ceiling
        # comfortably exceeds the request complexity.
        if cap.max_complexity >= complexity:
            headroom = cap.max_complexity - complexity
            complexity_points = min(25.0, 15.0 + headroom * 20.0)
        else:
            complexity_points = max(0.0, 10.0 - (complexity - cap.max_complexity) * 50.0)
            parts.append("complexity_stretch")
        score += complexity_points

        # Capability bonus (15 points) — reward coding/reasoning strength.
        cap_points = 0.0
        if needs_coding and "coding" in cap.strengths:
            cap_points += 8.0
        if needs_reasoning and any(s in cap.strengths for s in ("reasoning", "complex reasoning")):
            cap_points += 7.0
        score += min(cap_points, 15.0)

        # Cost efficiency (10 points) — cheaper is better.
        cost_points = max(0.0, 10.0 - (cap.cost_tier - 1) * 2.5)
        score += cost_points

        # Latency preference (10 points).
        if prefer_low_latency:
            latency_points = max(0.0, 10.0 - cap.estimated_latency_ms / 100.0)
        else:
            latency_points = 5.0
        score += latency_points

        score = round(min(100.0, max(0.0, score)), 1)
        return score, ", ".join(parts) if parts else "standard"
