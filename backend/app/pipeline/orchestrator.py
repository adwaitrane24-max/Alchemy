"""Pipeline orchestrator — coordinates module execution without business logic.

The orchestrator drives the request through stages, reacts to events,
manages checkpoints, and supports resumption. It never performs routing,
caching, budget, or model-selection logic itself.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from backend.app.budget.budget_manager import BudgetManager
from backend.app.config.settings import Settings, get_settings
from backend.app.constants.enums import RoutingAction
from backend.app.constants.models import ModelID
from backend.app.gateway.mock import MockResponseEngine
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.request import PromptRequest
from backend.app.models.response import PromptResponse
from backend.app.models.routing import RoutingDecision
from backend.app.modules.cache import SemanticCache
from backend.app.modules.fast_detector import FastRequestDetector
from backend.app.modules.task_analyzer import TaskAnalyzer
from backend.app.routing import RoutingEngine
from backend.app.security import SecurityScanner

from backend.app.pipeline.checkpoint_manager import CheckpointManager
from backend.app.pipeline.event_dispatcher import EventDispatcher, PipelineEvent
from backend.app.pipeline.exceptions import PipelineError, StageExecutionError
from backend.app.pipeline.pipeline_context import PipelineContext, PipelineStatus
from backend.app.pipeline.retry_manager import RetryManager
from backend.app.pipeline.pipeline_summary import log_summary
from backend.app.pipeline.stage_executor import StageExecutor
from backend.app.pipeline.stage_status import StageName, StageStatus

_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class PipelineOrchestrator:
    """Stateful, event-driven pipeline that coordinates all Alchemy modules.

    Responsibilities:
    - Execute modules in defined order
    - Maintain PipelineContext throughout the request
    - Save checkpoints after every completed stage
    - Resume execution after failures
    - Handle retries and terminal stages
    - Build execution traces
    """

    STAGE_ORDER: list[StageName] = [
        StageName.FAST_DETECTOR,
        StageName.SECURITY,
        StageName.TASK_ANALYZER,
        StageName.DECISION_ENGINE,
        StageName.BUDGET,
        StageName.SEMANTIC_CACHE,
        StageName.CONTEXT_MANAGER,
        StageName.RESPONSE_GENERATION,
        StageName.CACHE_STORE,
    ]

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
        self._settings = settings or get_settings()

        self._fast_detector = fast_detector or FastRequestDetector()
        self._security = security or SecurityScanner(
            log_blocked=self._settings.security_log_blocked
        )
        self._task_analyzer = task_analyzer or TaskAnalyzer()
        self._router = router or RoutingEngine()
        self._responder = responder or MockResponseEngine()
        self._cache = cache or SemanticCache(settings=self._settings)
        self._budget_manager = budget_manager or BudgetManager(
            self._settings.budget_daily_limit_usd
        )

        self._dispatcher = dispatcher or EventDispatcher()
        self._retry_manager = retry_manager or RetryManager()
        self._checkpoint_manager = checkpoint_manager or CheckpointManager(
            dispatcher=self._dispatcher
        )
        self._executor = StageExecutor(
            self._retry_manager, self._checkpoint_manager, self._dispatcher
        )

        self._stage_handlers: dict[StageName, Any] = {
            StageName.FAST_DETECTOR: self._run_fast_detector,
            StageName.SECURITY: self._run_security,
            StageName.TASK_ANALYZER: self._run_task_analyzer,
            StageName.DECISION_ENGINE: self._run_decision_engine,
            StageName.BUDGET: self._run_budget,
            StageName.SEMANTIC_CACHE: self._run_semantic_cache,
            StageName.CONTEXT_MANAGER: self._run_context_manager,
            StageName.RESPONSE_GENERATION: self._run_response_generation,
            StageName.CACHE_STORE: self._run_cache_store,
        }

    def process(self, request: PromptRequest) -> PromptResponse:
        context = PipelineContext(
            request_id=request.request_id,
            session_id=request.session_id,
            user_query=request.prompt,
            model_override=request.model_override,
            economic_mode=self._budget_manager.economic_mode,
        )
        context.start_timer()
        self._dispatcher.emit(
            PipelineEvent.PIPELINE_STARTED,
            {"request_id": context.request_id},
        )
        logger.info("Pipeline started request_id={}", context.request_id)
        return self._execute_pipeline(context, request)

    def resume(self, request_id: str, request: PromptRequest) -> PromptResponse:
        context = self._checkpoint_manager.load_checkpoint(request_id)
        if context is None:
            logger.warning(
                "No checkpoint found for request_id={}, starting fresh", request_id
            )
            return self.process(request)

        logger.info(
            "Resuming pipeline request_id={} from stage={}",
            request_id,
            context.current_stage,
        )
        return self._execute_pipeline(context, request)

    def _execute_pipeline(
        self, context: PipelineContext, request: PromptRequest
    ) -> PromptResponse:
        context.status = PipelineStatus.RUNNING

        completed = set(context.execution_trace.completed_stages)
        stages_to_run = [s for s in self.STAGE_ORDER if s not in completed]

        try:
            for stage_name in stages_to_run:
                if self._should_skip(stage_name, context):
                    self._executor.skip(stage_name, context)
                    continue

                self._executor.execute(
                    stage_name, self._stage_handlers[stage_name], context
                )

                terminal_event = self._check_terminal(stage_name, context)
                if terminal_event is not None:
                    self._handle_terminal(stage_name, terminal_event, context)
                    break

            if context.status == PipelineStatus.RUNNING:
                context.mark_completed()

            self._dispatcher.emit(
                PipelineEvent.PIPELINE_COMPLETED,
                {"request_id": context.request_id, "total_latency_ms": context.total_latency_ms},
            )
            logger.info(
                "Pipeline completed request_id={} total_latency={:.2f}ms",
                context.request_id,
                context.total_latency_ms,
            )
            log_summary(context)
            self._checkpoint_manager.delete_checkpoint(context.request_id)

        except StageExecutionError as exc:
            context.mark_failed(str(exc))
            self._dispatcher.emit(
                PipelineEvent.PIPELINE_FAILED,
                {"request_id": context.request_id, "error": str(exc), "stage": exc.stage},
            )
            logger.error("Pipeline failed request_id={}: {}", context.request_id, exc)

        except Exception as exc:
            context.mark_failed(str(exc))
            self._dispatcher.emit(
                PipelineEvent.PIPELINE_FAILED,
                {"request_id": context.request_id, "error": str(exc)},
            )
            logger.opt(exception=True).error(
                "Pipeline unexpected failure request_id={}", context.request_id
            )

        return self._build_response(context, request)

    def _stage_index(self, stage: StageName) -> int:
        return self.STAGE_ORDER.index(stage)

    def _should_skip(self, stage_name: StageName, context: PipelineContext) -> bool:
        """Determine if a stage should be skipped based on prior terminal results."""
        idx = self._stage_index(stage_name)

        # Fast path fired → skip everything after security
        if (
            context.fast_detector_result is not None
            and context.fast_detector_result.is_fast_path
            and idx > self._stage_index(StageName.SECURITY)
        ):
            return True

        # Security blocked → skip everything after security
        if (
            context.security_result is not None
            and context.security_result.is_blocked
            and idx > self._stage_index(StageName.SECURITY)
        ):
            return True

        # Cache hit → skip context_manager, response_generation, cache_store
        if context.cache_hit is True and stage_name in (
            StageName.CONTEXT_MANAGER,
            StageName.RESPONSE_GENERATION,
            StageName.CACHE_STORE,
        ):
            return True

        return False

    def _check_terminal(
        self, just_ran: StageName, context: PipelineContext
    ) -> PipelineEvent | None:
        """After a stage completes, check if it produced a terminal result."""
        if (
            just_ran == StageName.FAST_DETECTOR
            and context.fast_detector_result is not None
            and context.fast_detector_result.is_fast_path
        ):
            return PipelineEvent.FAST_RESPONSE

        if (
            just_ran == StageName.SECURITY
            and context.security_result is not None
            and context.security_result.is_blocked
        ):
            return PipelineEvent.SECURITY_BLOCKED

        if just_ran == StageName.SEMANTIC_CACHE and context.cache_hit is True:
            return PipelineEvent.CACHE_HIT

        return None

    def _handle_terminal(
        self,
        triggered_by: StageName,
        event: PipelineEvent,
        context: PipelineContext,
    ) -> None:
        """Skip remaining stages and set the terminal response."""
        # Mark all subsequent un-recorded stages as SKIPPED
        idx = self._stage_index(triggered_by)
        recorded = {r.name for r in context.execution_trace.records}
        for stage in self.STAGE_ORDER[idx + 1 :]:
            if stage not in recorded:
                # Fast-path terminal: still run security before skipping the rest
                if (
                    event == PipelineEvent.FAST_RESPONSE
                    and stage == StageName.SECURITY
                ):
                    self._executor.execute(
                        stage, self._stage_handlers[stage], context
                    )
                    if (
                        context.security_result is not None
                        and context.security_result.is_blocked
                    ):
                        event = PipelineEvent.SECURITY_BLOCKED
                        break
                    continue
                self._executor.skip(stage, context)

        # Set response based on terminal reason
        if event == PipelineEvent.FAST_RESPONSE:
            context.response_text = (
                context.fast_detector_result.canned_response or "OK."
                if context.fast_detector_result
                else "OK."
            )
            self._run_decision_engine(context)
            context.response_model = (
                context.routing_decision.model if context.routing_decision else None
            )
            context.mark_terminated_early("fast_response")
        elif event == PipelineEvent.SECURITY_BLOCKED:
            reason = (
                context.security_result.reason if context.security_result else "blocked"
            )
            context.response_text = f"⛔ Request blocked: {reason}"
            self._run_decision_engine(context)
            context.mark_terminated_early("security_blocked")
        elif event == PipelineEvent.CACHE_HIT:
            context.response_text = context.cache_response_text
            context.routing_decision = RoutingDecision(
                action=RoutingAction.CACHE_RETURN,
                model=context.cache_model_used,
                reason="Cache HIT",
            )
            context.mark_terminated_early("cache_hit")

        self._dispatcher.emit(event, {"request_id": context.request_id})

    # ── Stage handlers ──────────────────────────────────────────

    def _run_fast_detector(self, context: PipelineContext) -> None:
        request = self._build_request(context)
        context.fast_detector_result = self._fast_detector.detect(request)

    def _run_security(self, context: PipelineContext) -> None:
        request = self._build_request(context)
        context.security_result = self._security.scan(request)

    def _run_task_analyzer(self, context: PipelineContext) -> None:
        request = self._build_request(context)
        context.analysis_result = self._task_analyzer.analyze(request)

    def _run_decision_engine(self, context: PipelineContext) -> None:
        prompt_tokens = _estimate_tokens(context.user_query)
        budget = self._build_budget_snapshot()
        context.budget_snapshot = budget
        context.routing_decision = self._router.decide(
            security=context.security_result,
            analysis=context.analysis_result,
            budget=budget,
            fast_detector=context.fast_detector_result,
            prompt_tokens=prompt_tokens,
            model_override=context.model_override,
            economic_mode=context.economic_mode,
        )

    def _run_budget(self, context: PipelineContext) -> None:
        context.budget_snapshot = self._build_budget_snapshot()

    def _run_semantic_cache(self, context: PipelineContext) -> None:
        decision = self._cache.lookup(context.user_query)
        if decision.is_hit and decision.entry is not None:
            context.cache_hit = True
            context.cache_response_text = decision.entry.response_text
            context.cache_model_used = decision.entry.model_used
            context.response_text = decision.entry.response_text
            context.response_model = decision.entry.model_used
            context.response_cost_usd = 0.0
        else:
            context.cache_hit = False
            self._dispatcher.emit(
                PipelineEvent.CACHE_MISS, {"request_id": context.request_id}
            )

    def _run_context_manager(self, context: PipelineContext) -> None:
        self._dispatcher.emit(
            PipelineEvent.CONTEXT_READY, {"request_id": context.request_id}
        )

    def _run_response_generation(self, context: PipelineContext) -> None:
        if context.routing_decision is None or context.routing_decision.model is None:
            context.response_text = "No model was available to serve this request."
            return

        request = self._build_request(context)
        result = self._responder.generate(
            request, context.routing_decision.model, context.analysis_result
        )
        context.response_text = result.text
        context.response_model = context.routing_decision.model
        context.response_cost_usd = result.cost_usd
        context.response_prompt_tokens = result.prompt_tokens
        context.response_completion_tokens = result.completion_tokens
        context.response_latency_ms = result.latency_ms

        self._budget_manager.update(result.cost_usd)

        self._dispatcher.emit(
            PipelineEvent.RESPONSE_SUCCESS,
            {"request_id": context.request_id, "model": context.response_model},
        )

    def _run_cache_store(self, context: PipelineContext) -> None:
        if context.response_text and context.response_model and not context.cache_hit:
            self._cache.store(
                query=context.user_query,
                response_text=context.response_text,
                model_used=context.response_model,
                cost_usd=context.response_cost_usd,
                latency_ms=context.response_latency_ms,
            )

    # ── Helpers ──────────────────────────────────────────────────

    def _build_request(self, context: PipelineContext) -> PromptRequest:
        return PromptRequest(
            request_id=context.request_id,
            prompt=context.user_query,
            session_id=context.session_id,
            model_override=context.model_override,
        )

    def _build_budget_snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            daily_limit_usd=self._settings.budget_daily_limit_usd,
            spent_usd=self._budget_manager.used_budget_usd,
            warning_threshold=self._settings.budget_warning_threshold,
            critical_threshold=self._settings.budget_critical_threshold,
        )

    def _build_response(
        self, context: PipelineContext, request: PromptRequest
    ) -> PromptResponse:
        blocked = (
            context.security_result is not None and context.security_result.is_blocked
        )
        cached = context.cache_hit is True

        return PromptResponse(
            request_id=context.request_id,
            text=context.response_text or "No response generated.",
            model=context.response_model,
            blocked=blocked,
            cached=cached,
            latency_ms=context.total_latency_ms,
            cost_usd=context.response_cost_usd,
            prompt_tokens=context.response_prompt_tokens,
            completion_tokens=context.response_completion_tokens,
            fast_detector=context.fast_detector_result,
            security=context.security_result,
            analysis=context.analysis_result,
            routing=context.routing_decision,
        )
