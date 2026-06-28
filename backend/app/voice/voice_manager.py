"""Voice manager — coordinates recording and transcription."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from backend.app.config.settings import Settings, get_settings
from backend.app.voice.audio_recorder import AudioRecorder, RecordingResult
from backend.app.voice.exceptions import (
    MicrophoneUnavailableError,
    TranscriptionError,
    VoiceError,
)
from backend.app.voice.speech_to_text import SmallestSTTClient, TranscriptionResult


class VoiceManager:
    """Orchestrates microphone recording and Smallest.ai transcription."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._recorder = AudioRecorder()
        self._stt = SmallestSTTClient(settings=self._settings)

    @property
    def is_available(self) -> bool:
        """True when both microphone and STT API are usable."""
        return self._recorder.check_microphone() and self._stt.is_configured

    def check_readiness(self) -> tuple[bool, str]:
        """Return (ready, reason) for the voice subsystem."""
        if not self._stt.is_configured:
            return False, "Smallest.ai not configured (set SMALLEST_AI_API_KEY in .env)"
        if not self._recorder.check_microphone():
            return False, "No microphone detected"
        return True, "Voice input ready"

    def record_and_transcribe(
        self, on_listening: callable | None = None
    ) -> TranscriptionResult:
        """Record audio and return the transcript.

        Args:
            on_listening: Callback invoked when recording starts.

        Returns:
            TranscriptionResult with the text and timing.

        Raises:
            VoiceError: Any voice subsystem failure.
        """
        recording: RecordingResult | None = None
        try:
            recording = self._recorder.record(on_listening=on_listening)
            result = self._stt.transcribe(
                recording.file_path,
                audio_duration=recording.duration_seconds,
            )
            return result
        finally:
            if recording is not None:
                self._cleanup(recording.file_path)

    @staticmethod
    def _cleanup(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
            logger.debug("Temporary audio deleted path={}", path)
        except OSError:
            logger.warning("Failed to delete temporary audio path={}", path)
