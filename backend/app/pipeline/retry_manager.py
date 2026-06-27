"""Retry manager — configurable retry logic per stage."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

from loguru import logger

from backend.app.pipeline.stage_status import StageName


class RetryStrategy(StrEnum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 2
    delay_seconds: float = 0.1
    strategy: RetryStrategy = RetryStrategy.FIXED


# Default per-stage retry configs — stages with external I/O get more retries.
DEFAULT_RETRY_CONFIGS: dict[StageName, RetryConfig] = {
    StageName.FAST_DETECTOR: RetryConfig(max_retries=0),
    StageName.SECURITY: RetryConfig(max_retries=0),
    StageName.TASK_ANALYZER: RetryConfig(max_retries=0),
    StageName.DECISION_ENGINE: RetryConfig(max_retries=0),
    StageName.BUDGET: RetryConfig(max_retries=0),
    StageName.SEMANTIC_CACHE: RetryConfig(max_retries=1, delay_seconds=0.05),
    StageName.CONTEXT_MANAGER: RetryConfig(max_retries=1, delay_seconds=0.1),
    StageName.RESPONSE_GENERATION: RetryConfig(
        max_retries=2, delay_seconds=0.5, strategy=RetryStrategy.EXPONENTIAL
    ),
    StageName.CACHE_STORE: RetryConfig(max_retries=1, delay_seconds=0.05),
}


@dataclass
class RetryState:
    attempt: int = 0
    last_error: str | None = None


class RetryManager:
    """Manages retry state and delay logic for pipeline stages."""

    def __init__(
        self, configs: dict[StageName, RetryConfig] | None = None
    ) -> None:
        self._configs = configs or dict(DEFAULT_RETRY_CONFIGS)
        self._states: dict[StageName, RetryState] = {}

    def get_config(self, stage: StageName) -> RetryConfig:
        return self._configs.get(stage, RetryConfig())

    def can_retry(self, stage: StageName) -> bool:
        config = self.get_config(stage)
        state = self._states.get(stage, RetryState())
        return state.attempt < config.max_retries

    def record_attempt(self, stage: StageName, error: str) -> int:
        if stage not in self._states:
            self._states[stage] = RetryState()
        self._states[stage].attempt += 1
        self._states[stage].last_error = error
        return self._states[stage].attempt

    def wait_before_retry(self, stage: StageName) -> None:
        config = self.get_config(stage)
        state = self._states.get(stage, RetryState())
        if config.strategy == RetryStrategy.EXPONENTIAL:
            delay = config.delay_seconds * (2 ** (state.attempt - 1))
        else:
            delay = config.delay_seconds
        if delay > 0:
            logger.debug("Retry delay {:.3f}s for stage {}", delay, stage.value)
            time.sleep(delay)

    def get_attempt_count(self, stage: StageName) -> int:
        return self._states.get(stage, RetryState()).attempt

    def reset(self, stage: StageName) -> None:
        self._states.pop(stage, None)

    def reset_all(self) -> None:
        self._states.clear()
