"""Unit tests for the OtariGateway and create_gateway factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.config.settings import Settings, get_settings
from backend.app.constants.models import ModelID
from backend.app.gateway.mock import MockResponseEngine
from backend.app.gateway.otari_client import OtariGateway, create_gateway
from backend.app.models.request import PromptRequest

# ── Factory Tests ──────────────────────────


def test_create_gateway_returns_mock_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without OTARI_API_KEY, the factory returns MockResponseEngine."""
    get_settings.cache_clear()
    monkeypatch.setenv("OTARI_API_KEY", "")
    monkeypatch.setenv("OTARI_BASE_URL", "")
    get_settings.cache_clear()
    gateway = create_gateway()
    assert isinstance(gateway, MockResponseEngine)
    get_settings.cache_clear()


def test_create_gateway_returns_otari_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """With both OTARI_API_KEY and OTARI_BASE_URL set, returns OtariGateway."""
    get_settings.cache_clear()
    monkeypatch.setenv("OTARI_API_KEY", "test-key-123")
    monkeypatch.setenv("OTARI_BASE_URL", "https://api.otari.test")
    get_settings.cache_clear()
    gateway = create_gateway()
    assert isinstance(gateway, OtariGateway)
    get_settings.cache_clear()


# ── OtariGateway Interface Tests ──────────────────────────


class TestOtariGateway:
    @pytest.fixture
    def settings(self, monkeypatch: pytest.MonkeyPatch) -> Settings:
        get_settings.cache_clear()
        monkeypatch.setenv("OTARI_API_KEY", "test-key")
        monkeypatch.setenv("OTARI_BASE_URL", "https://api.otari.test")
        monkeypatch.setenv("OTARI_TIMEOUT_MS", "5000")
        get_settings.cache_clear()
        s = get_settings()
        yield s
        get_settings.cache_clear()

    @pytest.fixture
    def gateway(self, settings: Settings) -> OtariGateway:
        return OtariGateway(settings=settings)

    @pytest.fixture
    def prompt_request(self) -> PromptRequest:
        return PromptRequest(prompt="Explain binary search in Python")

    def test_successful_api_call(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """Mocked successful Otari API response returns a valid MockResult."""
        api_response = {
            "choices": [
                {"message": {"content": "Binary search is a divide-and-conquer algorithm."}}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 25},
        }

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_response = mock_client_cls.return_value.__enter__.return_value.post.return_value
            mock_response.status_code = 200
            mock_response.json.return_value = api_response
            mock_response.raise_for_status.return_value = None

            result = gateway.generate(prompt_request, ModelID.LLAMA_3_1_8B)

        assert result.text == "Binary search is a divide-and-conquer algorithm."
        assert result.model is ModelID.LLAMA_3_1_8B
        assert result.prompt_tokens == 12
        assert result.completion_tokens == 25
        assert result.latency_ms > 0

    def test_api_timeout_falls_back_to_mock(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """On timeout, falls back to MockResponseEngine."""
        import httpx

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.post.side_effect = (
                httpx.TimeoutException("timed out")
            )

            result = gateway.generate(prompt_request, ModelID.LLAMA_3_1_8B)

        assert result.text  # mock produces text
        assert result.model is ModelID.LLAMA_3_1_8B

    def test_api_http_error_falls_back_to_mock(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """On HTTP 500, falls back to MockResponseEngine."""
        import httpx

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_response = mock_client_cls.return_value.__enter__.return_value.post.return_value
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("POST", "https://api.test"), response=mock_response
            )

            result = gateway.generate(prompt_request, ModelID.LLAMA_3_3_70B)

        assert result.text  # mock text, not empty
        assert result.model is ModelID.LLAMA_3_3_70B

    def test_context_text_is_prepended(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """When context_text is provided, it's prepended to the user message."""
        captured_payload: dict = {}
        api_response = {
            "choices": [{"message": {"content": "Answer with context."}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }

        def capture_post(url: str, headers: dict, json: dict) -> object:
            captured_payload.update(json)

            class FakeResponse:
                status_code = 200

                def json(self) -> dict:
                    return api_response

                def raise_for_status(self) -> None:
                    pass

            return FakeResponse()

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.post = capture_post

            gateway.generate(
                prompt_request,
                ModelID.QWEN3_32B,
                context_text="Previous: user asked about sorting.",
            )

        user_msg = captured_payload["messages"][1]["content"]
        assert "Previous: user asked about sorting." in user_msg
        assert "Explain binary search" in user_msg

    def test_no_context_text_sends_plain_prompt(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """Without context_text, the user message is the raw prompt."""
        captured_payload: dict = {}
        api_response = {
            "choices": [{"message": {"content": "Plain answer."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        def capture_post(url: str, headers: dict, json: dict) -> object:
            captured_payload.update(json)

            class FakeResponse:
                status_code = 200

                def json(self) -> dict:
                    return api_response

                def raise_for_status(self) -> None:
                    pass

            return FakeResponse()

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.post = capture_post

            gateway.generate(prompt_request, ModelID.LLAMA_3_1_8B)

        user_msg = captured_payload["messages"][1]["content"]
        assert user_msg == "Explain binary search in Python"

    def test_cost_computed_from_model_costs(
        self, gateway: OtariGateway, prompt_request: PromptRequest
    ) -> None:
        """Cost is calculated from MODEL_COSTS, not hardcoded."""
        api_response = {
            "choices": [{"message": {"content": "Response."}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        }

        with patch("backend.app.gateway.otari_client.httpx.Client") as mock_client_cls:
            mock_response = mock_client_cls.return_value.__enter__.return_value.post.return_value
            mock_response.status_code = 200
            mock_response.json.return_value = api_response
            mock_response.raise_for_status.return_value = None

            result = gateway.generate(prompt_request, ModelID.LLAMA_3_1_8B)

        # LLAMA_3_1_8B is free through Groq/Otari (cost=0.0)
        assert result.cost_usd == 0.0


# ── Mock Engine Interface Parity ──────────────────────────


def test_mock_engine_accepts_context_text() -> None:
    """MockResponseEngine.generate() accepts context_text without error."""
    engine = MockResponseEngine(seed=42)
    request = PromptRequest(prompt="Hello world")
    result = engine.generate(request, ModelID.LLAMA_3_1_8B, context_text="some context")
    assert result.text
    assert result.model is ModelID.LLAMA_3_1_8B
