"""Smallest.ai Speech-to-Text client."""

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
    """Sends audio to Smallest.ai and returns the transcript."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        base = self._settings.smallest_ai_base_url.rstrip("/")
        self._endpoint = f"{base}/api/v1/transcribe" if base else ""
        self._api_key = self._settings.smallest_ai_api_key
        self._timeout = _DEFAULT_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._endpoint)

    def transcribe(self, audio_path: Path, audio_duration: float = 0.0) -> TranscriptionResult:
        """Upload an audio file and return the transcript.

        Args:
            audio_path: Path to the WAV file.
            audio_duration: Duration of the audio in seconds (for logging).

        Returns:
            A TranscriptionResult with the transcript text.

        Raises:
            TranscriptionError: API returned an error or empty transcript.
            TranscriptionTimeoutError: API did not respond in time.
        """
        if not self.is_configured:
            raise TranscriptionError(
                "Smallest.ai is not configured — set SMALLEST_AI_API_KEY and SMALLEST_AI_BASE_URL"
            )

        logger.info(
            "Uploading audio path={} duration={:.2f}s",
            audio_path,
            audio_duration,
        )

        headers = {"Authorization": f"Bearer {self._api_key}"}
        start = time.perf_counter()

        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path.name, f, "audio/wav")}
                data = {"language": "en", "model": "whisper-v2"}
                logger.debug("STT request sent endpoint={}", self._endpoint)

                response = httpx.post(
                    self._endpoint,
                    headers=headers,
                    files=files,
                    data=data,
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
        logger.info("STT response received status={} latency={:.2f}ms", response.status_code, latency)

        if response.status_code != 200:
            raise TranscriptionError(
                f"Smallest.ai returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
        except Exception as exc:
            raise TranscriptionError(f"Invalid JSON response: {exc}") from exc

        text = ""
        if isinstance(body, dict):
            text = body.get("text", "") or body.get("transcript", "") or ""
        if isinstance(body, str):
            text = body

        text = text.strip()
        if not text:
            raise TranscriptionError("Smallest.ai returned an empty transcript")

        logger.info(
            "Transcription successful length={} latency={:.2f}ms",
            len(text),
            latency,
        )

        return TranscriptionResult(
            text=text,
            latency_ms=latency,
            audio_duration_seconds=audio_duration,
        )
