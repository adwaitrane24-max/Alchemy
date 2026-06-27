"""Mock response engine.

Produces realistic but fabricated model responses so the full pipeline can be
exercised end-to-end before any real LLM (Ollama/Otari) is integrated. It
simulates per-model latency and token usage and computes cost from static
pricing. This module MUST be replaced by the real gateway in a later milestone.
"""

from __future__ import annotations

import random
import time

from loguru import logger

from backend.app.constants.models import MODEL_COSTS, ModelID
from backend.app.models.analysis import PromptAnalysis
from backend.app.models.request import PromptRequest

# Simulated latency band (milliseconds) per model — cheaper/local is faster.
_LATENCY_BANDS_MS: dict[ModelID, tuple[int, int]] = {
    ModelID.LOCAL_2B: (40, 120),
    ModelID.GPT4O_MINI: (250, 600),
    ModelID.GPT4O: (600, 1400),
}

_MODEL_LABELS: dict[ModelID, str] = {
    ModelID.LOCAL_2B: "Local Gemma 2B",
    ModelID.GPT4O_MINI: "GPT-4o-mini",
    ModelID.GPT4O: "GPT-4o",
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), with a floor of 1."""
    return max(1, len(text) // 4)


class MockResult:
    """Lightweight container for a simulated model call result."""

    __slots__ = ("completion_tokens", "cost_usd", "latency_ms", "model", "prompt_tokens", "text")

    def __init__(
        self,
        *,
        text: str,
        model: ModelID,
        latency_ms: float,
        cost_usd: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.text = text
        self.model = model
        self.latency_ms = latency_ms
        self.cost_usd = cost_usd
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class MockResponseEngine:
    """Generates deterministic-shape, randomized-content mock responses."""

    def __init__(self, *, simulate_latency: bool = False, seed: int | None = None) -> None:
        """Create the engine.

        Args:
            simulate_latency: When True, actually sleeps for the simulated
                latency (useful for demos). Defaults to False so tests are fast.
            seed: Optional RNG seed for reproducible latency/content.
        """
        self._simulate_latency = simulate_latency
        self._rng = random.Random(seed)

    def generate(
        self,
        request: PromptRequest,
        model: ModelID,
        analysis: PromptAnalysis | None = None,
    ) -> MockResult:
        """Generate a mock response for a request on a given model.

        Args:
            request: The original prompt request.
            model: The model selected by the routing engine.
            analysis: Optional task analysis used to tailor the mock text.

        Returns:
            A :class:`MockResult` with text, latency, cost, and token usage.
        """
        low, high = _LATENCY_BANDS_MS.get(model, (50, 200))
        latency_ms = float(self._rng.randint(low, high))
        if self._simulate_latency:
            time.sleep(latency_ms / 1000.0)

        text = self._compose_text(request, model, analysis)
        prompt_tokens = _estimate_tokens(request.prompt)
        completion_tokens = _estimate_tokens(text)
        cost_usd = self._cost(model, prompt_tokens, completion_tokens)

        logger.debug(
            "Mock response model={} latency={}ms tokens={}+{} cost=${:.5f}",
            model.value,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            cost_usd,
        )
        return MockResult(
            text=text,
            model=model,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _compose_text(
        self, request: PromptRequest, model: ModelID, analysis: PromptAnalysis | None
    ) -> str:
        """Build a plausible mock answer referencing the routing context."""
        label = _MODEL_LABELS.get(model, model.value)
        task = analysis.task_type.value if analysis else "general"
        snippet = request.prompt.strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        return (
            f"[mock · {label}] Here is a simulated {task} response to: "
            f"“{snippet}”. Real model output will appear once the "
            f"Ollama/Otari gateway is integrated."
        )

    @staticmethod
    def _cost(model: ModelID, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute USD cost from static per-1K-token pricing."""
        costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        total = (prompt_tokens / 1000.0) * costs["input"] + (completion_tokens / 1000.0) * costs[
            "output"
        ]
        return round(total, 6)
