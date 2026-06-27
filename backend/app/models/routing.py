"""Routing decision model — the routing engine's verdict for a request."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.constants.enums import RoutingAction
from backend.app.constants.models import ModelID


class RoutingDecision(BaseModel):
    """The routing engine's decision about how to serve a request.

    Carries the chosen action (call a model, return from cache, or block),
    the selected model, an explanation, and the estimated cost — everything
    the dashboard needs to render an explainable routing trace.
    """

    model_config = ConfigDict(frozen=True)

    action: RoutingAction
    model: ModelID | None = Field(
        default=None, description="Selected model when action is MODEL_CALL."
    )
    reason: str = Field(description="Human-readable justification for the decision.")
    estimated_cost_usd: float = Field(ge=0.0, default=0.0)
    fallback_chain: tuple[ModelID, ...] = Field(default_factory=tuple)
