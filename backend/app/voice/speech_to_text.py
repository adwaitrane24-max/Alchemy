"""Smallest.ai Pulse Speech-to-Text client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger

from backend.app.config.settings import Settings, get_settings
from backend.app.voice.exceptions import TranscriptionError, TranscriptionTimeoutError

_DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    latency_ms: float
    audio_duration_seconds: float


class SmallestSTTClient:
    """Sends audio to Smallest.ai Pulse for transcription.

    The API expects raw audio bytes with Content-Type: application/octet-stream.
    All configuration (model, language) is passed as query parameters.
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api_key = self._settings.smallest_ai_api_key
        self._endpoint = "https://api.smallest.ai/waves/v1/stt/"
        self._timeout = _DEFAULT_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def transcribe(self, audio_path: Path, audio_duration: float = 0.0) -> TranscriptionResult:
        if not self.is_configured:
            raise TranscriptionError(
                "Smallest.ai not configured — set SMALLEST_AI_API_KEY in .env"
            )

        logger.info("Uploading audio to Smallest.ai Pulse path={} duration={:.2f}s", audio_path, audio_duration)
        start = time.perf_counter()

        try:
            audio_bytes = audio_path.read_bytes()
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/octet-stream",
            }
            params = {"model": "pulse", "language": "en"}
            logger.debug("STT request sent endpoint={} size_bytes={}", self._endpoint, len(audio_bytes))

            response = httpx.post(
                self._endpoint,
                headers=headers,
                params=params,
                content=audio_bytes,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            latency = (time.perf_counter() - start) * 1000
            logger.error("STT request timed out after {:.0f}ms", latency)
            raise TranscriptionTimeoutError(
                f"Smallest.ai did not respond within {self._timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Network error: {exc}") from exc

        latency = round((time.perf_counter() - start) * 1000, 2)
        logger.info("STT response status={} latency={:.2f}ms", response.status_code, latency)

        if response.status_code != 200:
            raise TranscriptionError(
                f"Smallest.ai returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            body = response.json()
        except Exception as exc:
            raise TranscriptionError(f"Invalid JSON response: {exc}") from exc

        logger.debug("STT raw response body={}", body)

        text = ""
        if isinstance(body, str):
            text = body
        elif isinstance(body, dict):
            text = (
                body.get("text")
                or body.get("transcript")
                or body.get("transcription")
                or body.get("result")
                or ""
            )
            if not text and isinstance(body.get("data"), dict):
                text = body["data"].get("text") or body["data"].get("transcript") or ""
            if not text and isinstance(body.get("results"), list) and body["results"]:
                first = body["results"][0]
                if isinstance(first, dict):
                    text = first.get("text") or first.get("transcript") or ""
        if not isinstance(text, str):
            text = str(text)

        text = text.strip()
        if not text:
            raise TranscriptionError(f"Smallest.ai returned an empty transcript (body={body})")

        logger.info("Transcription successful length={} latency={:.2f}ms", len(text), latency)
        return TranscriptionResult(text=text, latency_ms=latency, audio_duration_seconds=audio_duration)
