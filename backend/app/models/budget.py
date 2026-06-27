"""Budget state model — snapshot of spend used by the routing engine.

NOTE: Real budget tracking/persistence is a later milestone. This model only
defines the contract; the first working version supplies a static snapshot.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.app.constants.enums import BudgetState as BudgetStateEnum


class BudgetSnapshot(BaseModel):
    """Immutable view of the daily budget at decision time."""

    model_config = ConfigDict(frozen=True)

    daily_limit_usd: float = Field(gt=0.0)
    spent_usd: float = Field(ge=0.0, default=0.0)
    warning_threshold: float = Field(ge=0.0, le=1.0, default=0.60)
    critical_threshold: float = Field(ge=0.0, le=1.0, default=0.85)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fraction_used(self) -> float:
        """Fraction of the daily limit consumed, clamped to [0, 1]."""
        return min(self.spent_usd / self.daily_limit_usd, 1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining_usd(self) -> float:
        """Remaining spend available today (never negative)."""
        return max(self.daily_limit_usd - self.spent_usd, 0.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state(self) -> BudgetStateEnum:
        """Derive the budget state machine value from current spend."""
        used = self.fraction_used
        if used >= self.critical_threshold:
            return BudgetStateEnum.CRITICAL
        if used >= self.warning_threshold:
            return BudgetStateEnum.LOW
        return BudgetStateEnum.HEALTHY
