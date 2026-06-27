"""Pipeline orchestrator — thin compatibility wrapper.

Delegates all execution to the stateful :class:`PipelineOrchestrator` while
preserving the original ``AlchemyPipeline`` API so existing CLI code,
integration tests, and session imports continue to work unchanged.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from backend.app.budget.budget_manager import BudgetManager
from backend.app.config.settings import Settings, get_settings
from backend.app.gateway.mock import MockResponseEngine
from backend.app.models.request import PromptRequest
from backend.app.models.response import PromptResponse
from backend.app.modules.cache import SemanticCache
from backend.app.modules.fast_detector import FastRequestDetector
from backend.app.modules.task_analyzer import TaskAnalyzer
from backend.app.pipeline.checkpoint_manager import CheckpointManager
from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.orchestrator import PipelineOrchestrator
from backend.app.pipeline.retry_manager import RetryManager
from backend.app.routing import RoutingEngine
from backend.app.security import SecurityScanner


def _make_debug_logger() -> EventDispatcher:
    """Create an EventDispatcher that logs every event at DEBUG level."""
    dispatcher = EventDispatcher()

    def _log_event(event: PipelineEvent, data: dict[str, Any]) -> None:
        logger.debug("[pipeline-event] {} {}", event.value, data)

    for evt in PipelineEvent:
        dispatcher.subscribe(evt, _log_event)

    return dispatcher


class AlchemyPipeline:
    """Backward-compatible wrapper around :class:`PipelineOrchestrator`.

    Accepts the same constructor arguments as the original implementation.
    Callers (CLI, tests) see no API change.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fast_detector: FastRequestDetector | None = None,
        security: SecurityScanner | None = None,
        task_analyzer: TaskAnalyzer | None = None,
        router: RoutingEngine | None = None,
        responder: MockResponseEngine | None = None,
        cache: SemanticCache | None = None,
        budget_manager: BudgetManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        retry_manager: RetryManager | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        resolved_dispatcher = dispatcher or _make_debug_logger()

        self._orchestrator = PipelineOrchestrator(
            settings=resolved_settings,
            fast_detector=fast_detector,
            security=security,
            task_analyzer=task_analyzer,
            router=router,
            responder=responder,
            cache=cache,
            budget_manager=budget_manager,
            checkpoint_manager=checkpoint_manager or CheckpointManager(
                dispatcher=resolved_dispatcher
            ),
            retry_manager=retry_manager,
            dispatcher=resolved_dispatcher,
        )

    def process(self, request: PromptRequest) -> PromptResponse:
        """Process a request end-to-end through the stateful pipeline."""
        return self._orchestrator.process(request)

    def resume(self, request_id: str, request: PromptRequest) -> PromptResponse:
        """Resume a previously failed request from its last checkpoint."""
        return self._orchestrator.resume(request_id, request)
