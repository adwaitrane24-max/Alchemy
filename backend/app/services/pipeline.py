"""Pipeline orchestrator.

Coordinates the end-to-end request flow:

    fast detector → security → task analyzer → routing → (mock) response

Each stage communicates exclusively through the shared models. Stages that are
out of scope for the first working version (cache, real models, budget
tracking) are either skipped or supplied with static stand-ins.
"""

from __future__ import annotations

import time

from loguru import logger

from backend.app.config.settings import Settings, get_settings
from backend.app.constants.enums import RoutingAction
from backend.app.constants.models import ModelID
from backend.app.gateway.mock import MockResponseEngine
from backend.app.models.analysis import (
    FastDetectorResult,
    PromptAnalysis,
    SecurityResult,
)
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.request import PromptRequest
from backend.app.models.response import PromptResponse
from backend.app.models.routing import RoutingDecision
from backend.app.modules.fast_detector import FastRequestDetector
from backend.app.modules.task_analyzer import TaskAnalyzer
from backend.app.routing import RoutingEngine
from backend.app.security import SecurityScanner

# Rough token estimate (~4 chars/token) used for routing cost projection.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Estimate token count for routing decisions."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


class AlchemyPipeline:
    """Runs a :class:`PromptRequest` through every gateway stage.

    Dependencies are injected so each can be swapped (e.g. real gateway in place
    of the mock) without changing the orchestration logic.
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
    ) -> None:
        self._settings = settings or get_settings()
        self._fast_detector = fast_detector or FastRequestDetector()
        self._security = security or SecurityScanner(
            log_blocked=self._settings.security_log_blocked
        )
        self._task_analyzer = task_analyzer or TaskAnalyzer()
        self._router = router or RoutingEngine()
        self._responder = responder or MockResponseEngine()

    def _budget_snapshot(self) -> BudgetSnapshot:
        """Build a static budget snapshot from settings.

        Real spend tracking is a later milestone; for now spend is zero so the
        budget state is HEALTHY.
        """
        return BudgetSnapshot(
            daily_limit_usd=self._settings.budget_daily_limit_usd,
            spent_usd=0.0,
            warning_threshold=self._settings.budget_warning_threshold,
            critical_threshold=self._settings.budget_critical_threshold,
        )

    def process(self, request: PromptRequest) -> PromptResponse:
        """Process a request end-to-end and return a populated response.

        Args:
            request: The inbound prompt request.

        Returns:
            A :class:`PromptResponse` carrying the answer plus the full decision
            trace (detector, security, analysis, routing) and live metrics.
        """
        start = time.perf_counter()
        logger.info("Processing request_id={} words={}", request.request_id, request.word_count)

        prompt_tokens = _estimate_tokens(request.prompt)
        budget = self._budget_snapshot()

        # ── Stage 1: Security (highest priority gate) ──
        security = self._security.scan(request)
        if security.is_blocked:
            routing = self._router.decide(security=security, analysis=None, budget=budget)
            return self._finalize(
                request,
                text=f"⛔ Request blocked: {security.reason}",
                start=start,
                blocked=True,
                security=security,
                routing=routing,
            )

        # ── Stage 2: Fast request detector ──
        fast = self._fast_detector.detect(request)
        if fast.is_fast_path:
            routing = self._router.decide(
                security=security,
                analysis=None,
                budget=budget,
                fast_detector=fast,
                prompt_tokens=prompt_tokens,
            )
            text = fast.canned_response or "OK."
            return self._finalize(
                request,
                text=text,
                start=start,
                security=security,
                fast=fast,
                routing=routing,
                model=routing.model,
            )

        # ── Stage 3: Task analyzer ──
        analysis = self._task_analyzer.analyze(request)

        # ── Stage 4: Routing ──
        routing = self._router.decide(
            security=security,
            analysis=analysis,
            budget=budget,
            fast_detector=fast,
            prompt_tokens=prompt_tokens,
            model_override=request.model_override,
        )

        # ── Stage 5: Response generation (mock) ──
        if routing.action is RoutingAction.MODEL_CALL and routing.model is not None:
            result = self._responder.generate(request, routing.model, analysis)
            return self._finalize(
                request,
                text=result.text,
                start=start,
                security=security,
                fast=fast,
                analysis=analysis,
                routing=routing,
                model=routing.model,
                cost_usd=result.cost_usd,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )

        # Defensive fallback (should not occur for a CLEAR request).
        return self._finalize(
            request,
            text="No model was available to serve this request.",
            start=start,
            security=security,
            fast=fast,
            analysis=analysis,
            routing=routing,
        )

    def _finalize(
        self,
        request: PromptRequest,
        *,
        text: str,
        start: float,
        blocked: bool = False,
        cached: bool = False,
        security: SecurityResult | None = None,
        fast: FastDetectorResult | None = None,
        analysis: PromptAnalysis | None = None,
        routing: RoutingDecision | None = None,
        model: ModelID | None = None,
        cost_usd: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> PromptResponse:
        """Assemble the final response and stamp the measured latency."""
        latency_ms = (time.perf_counter() - start) * 1000.0
        response = PromptResponse(
            request_id=request.request_id,
            text=text,
            model=model,
            blocked=blocked,
            cached=cached,
            latency_ms=round(latency_ms, 3),
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            fast_detector=fast,
            security=security,
            analysis=analysis,
            routing=routing,
        )
        logger.info(
            "Completed request_id={} blocked={} model={} latency={}ms cost=${:.5f}",
            request.request_id,
            blocked,
            model.value if model is not None else None,
            response.latency_ms,
            cost_usd,
        )
        return response
