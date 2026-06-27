"""Unit tests for the mock response engine."""

from __future__ import annotations

from backend.app.constants.models import ModelID
from backend.app.gateway import MockResponseEngine
from backend.app.models.request import PromptRequest


def test_generate_returns_text_and_metrics() -> None:
    engine = MockResponseEngine(seed=42)
    result = engine.generate(PromptRequest(prompt="Explain binary search."), ModelID.GPT4O_MINI)
    assert result.text
    assert result.model is ModelID.GPT4O_MINI
    assert result.latency_ms > 0
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0


def test_local_model_is_free() -> None:
    engine = MockResponseEngine(seed=1)
    result = engine.generate(PromptRequest(prompt="hi there"), ModelID.LOCAL_2B)
    assert result.cost_usd == 0.0


def test_paid_model_has_cost() -> None:
    engine = MockResponseEngine(seed=1)
    result = engine.generate(PromptRequest(prompt="hello world example"), ModelID.GPT4O)
    assert result.cost_usd > 0.0


def test_latency_is_deterministic_with_seed() -> None:
    request = PromptRequest(prompt="same prompt")
    a = MockResponseEngine(seed=7).generate(request, ModelID.GPT4O_MINI)
    b = MockResponseEngine(seed=7).generate(request, ModelID.GPT4O_MINI)
    assert a.latency_ms == b.latency_ms
