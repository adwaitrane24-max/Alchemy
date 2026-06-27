"""Response model — the final pipeline output returned to the caller/CLI."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.constants.models import ModelID
from backend.app.models.analysis import (
    FastDetectorResult,
    PromptAnalysis,
    SecurityResult,
)
from backend.app.models.routing import RoutingDecision


class PromptResponse(BaseModel):
    """The end-to-end result of processing a single :class:`PromptRequest`.

    Aggregates the generated text together with the full decision trace
    (detector, security, analysis, routing) so the CLI dashboard can render
    a transparent, explainable view of how the answer was produced.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    text: str = Field(description="The answer returned to the user (mock for now).")
    model: ModelID | None = Field(default=None, description="Model that served the request.")
    blocked: bool = Field(default=False, description="True if security blocked the request.")
    cached: bool = Field(default=False, description="True if served from cache.")

    latency_ms: float = Field(ge=0.0, default=0.0)
    cost_usd: float = Field(ge=0.0, default=0.0)
    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)

    # Decision trace — any stage may be None if short-circuited earlier.
    fast_detector: FastDetectorResult | None = None
    security: SecurityResult | None = None
    analysis: PromptAnalysis | None = None
    routing: RoutingDecision | None = None

    @property
    def total_tokens(self) -> int:
        """Sum of prompt and completion tokens."""
        return self.prompt_tokens + self.completion_tokens
