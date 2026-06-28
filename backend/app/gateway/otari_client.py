"""Mozilla Otari Gateway — real LLM calls via OpenAI-compatible API.

Sends prompts to Mozilla Otari's hosted models through its OpenAI-compatible
chat completions endpoint. Falls back to the mock engine on API errors so the
pipeline never crashes due to a transient upstream failure.
"""

from __future__ import annotations

import time

import httpx
from loguru import logger

from backend.app.config.settings import Settings, get_settings
from backend.app.constants.models import MODEL_COSTS, ModelID
from backend.app.gateway.mock import MockResponseEngine, MockResult
from backend.app.models.analysis import PromptAnalysis
from backend.app.models.request import PromptRequest

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Provide clear, accurate, and concise responses."
)


class OtariGateway:
    """Calls Mozilla Otari's OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fallback: MockResponseEngine | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._fallback = fallback or MockResponseEngine()

        base = self._settings.otari_base_url.rstrip("/")
        if base.endswith("/v1"):
            self._endpoint = f"{base}/chat/completions"
        else:
            self._endpoint = f"{base}/v1/chat/completions"
        self._timeout = self._settings.otari_timeout_ms / 1000.0
        self._headers = {
            "Authorization": f"Bearer {self._settings.otari_api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "OtariGateway initialized endpoint={} timeout={}s",
            self._endpoint,
            self._timeout,
        )

    def generate(
        self,
        request: PromptRequest,
        model: ModelID,
        analysis: PromptAnalysis | None = None,
        context_text: str = "",
    ) -> MockResult:
        """Call Mozilla Otari and return a result compatible with the pipeline.

        Args:
            request: The inbound prompt request.
            model: The model selected by the routing engine.
            analysis: Optional task analysis (unused by the API, logged).
            context_text: Conversation context from unified memory to prepend.

        Returns:
            A :class:`MockResult` populated from the real API response.
            Falls back to the mock engine on any failure.
        """
        user_content = request.prompt
        if context_text:
            user_content = f"{context_text}\n\n---\n\n{user_content}"

        messages = [
            {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        payload = {
            "model": model.value,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048,
        }

        logger.info(
            "Otari API call model={} prompt_len={} context_len={}",
            model.value,
            len(request.prompt),
            len(context_text),
        )

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    self._endpoint,
                    headers=self._headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            latency_ms = (time.perf_counter() - start) * 1000.0

            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", len(user_content) // 4)
            completion_tokens = usage.get("completion_tokens", len(text) // 4)
            cost_usd = self._compute_cost(model, prompt_tokens, completion_tokens)

            logger.info(
                "Otari API success model={} latency={:.0f}ms tokens={}+{} cost=${:.6f}",
                model.value,
                latency_ms,
                prompt_tokens,
                completion_tokens,
                cost_usd,
            )

            return MockResult(
                text=text,
                model=model,
                latency_ms=round(latency_ms, 3),
                cost_usd=cost_usd,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except httpx.HTTPStatusError as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.error(
                "Otari API HTTP error model={} status={} latency={:.0f}ms: {}",
                model.value,
                exc.response.status_code,
                latency_ms,
                exc.response.text[:200],
            )
            return self._fallback.generate(request, model, analysis)

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.error(
                "Otari API timeout model={} after {:.0f}ms (limit={}s)",
                model.value,
                latency_ms,
                self._timeout,
            )
            return self._fallback.generate(request, model, analysis)

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.opt(exception=True).error(
                "Otari API unexpected error model={} latency={:.0f}ms: {}",
                model.value,
                latency_ms,
                exc,
            )
            return self._fallback.generate(request, model, analysis)

    @staticmethod
    def _compute_cost(model: ModelID, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute USD cost from static per-1K-token pricing."""
        costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        total = (prompt_tokens / 1000.0) * costs["input"] + (completion_tokens / 1000.0) * costs[
            "output"
        ]
        return round(total, 6)


def create_gateway(
    settings: Settings | None = None,
) -> OtariGateway | MockResponseEngine:
    """Factory: return OtariGateway if API key is configured, else MockResponseEngine.

    This is the single entry point for gateway construction. The pipeline
    orchestrator and the compatibility wrapper both call this.
    """
    resolved = settings or get_settings()

    if resolved.otari_api_key and resolved.otari_base_url:
        logger.info("Gateway: OtariGateway (live API)")
        return OtariGateway(settings=resolved)

    logger.info("Gateway: MockResponseEngine (no OTARI_API_KEY configured)")
    return MockResponseEngine()
