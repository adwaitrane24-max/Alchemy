"""Microphone audio recorder with silence detection."""

from __future__ import annotations

import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loguru import logger

from backend.app.voice.exceptions import MicrophoneUnavailableError, RecordingTimeoutError

SAMPLE_RATE = 16000
CHANNELS = 1
MAX_DURATION_SECONDS = 60
SILENCE_THRESHOLD = 0.01
SILENCE_DURATION_SECONDS = 2.0
DTYPE = "float32"


@dataclass(frozen=True)
class RecordingResult:
    file_path: Path
    duration_seconds: float
    sample_rate: int


class AudioRecorder:
    """Records microphone audio to a temporary WAV file."""

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        max_duration: int = MAX_DURATION_SECONDS,
        silence_threshold: float = SILENCE_THRESHOLD,
        silence_duration: float = SILENCE_DURATION_SECONDS,
    ) -> None:
        self._sample_rate = sample_rate
        self._max_duration = max_duration
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration

    def check_microphone(self) -> bool:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_input = sd.query_devices(kind="input")
            return default_input is not None
        except Exception:
            return False

    def record(self, on_listening: callable | None = None) -> RecordingResult:
        """Record audio from the microphone until silence or max duration.

        Args:
            on_listening: Optional callback invoked when recording starts.

        Returns:
            A RecordingResult with the path to the WAV file.

        Raises:
            MicrophoneUnavailableError: No microphone or permission denied.
            RecordingTimeoutError: Maximum duration exceeded.
        """
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise MicrophoneUnavailableError(
                f"Audio system unavailable: {exc}"
            ) from exc

        try:
            sd.query_devices(kind="input")
        except sd.PortAudioError as exc:
            raise MicrophoneUnavailableError(
                f"No microphone found: {exc}"
            ) from exc

        frames: list[np.ndarray] = []
        silence_start: float | None = None
        stopped = threading.Event()

        def callback(indata: np.ndarray, frame_count: int, time_info: dict, status: object) -> None:
            if status:
                logger.warning("Audio stream status: {}", status)
            frames.append(indata.copy())
            amplitude = np.abs(indata).mean()
            nonlocal silence_start
            if amplitude < self._silence_threshold:
                if silence_start is None:
                    silence_start = time.monotonic()
                elif time.monotonic() - silence_start >= self._silence_duration:
                    stopped.set()
            else:
                silence_start = None

        logger.info("Recording started sample_rate={} max_duration={}s", self._sample_rate, self._max_duration)
        if on_listening:
            on_listening()

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=callback,
            ):
                stopped.wait(timeout=self._max_duration)
        except sd.PortAudioError as exc:
            raise MicrophoneUnavailableError(f"Recording failed: {exc}") from exc

        if not frames:
            raise MicrophoneUnavailableError("No audio data captured")

        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / self._sample_rate
        logger.info("Recording finished duration={:.2f}s samples={}", duration, len(audio))

        if duration >= self._max_duration:
            raise RecordingTimeoutError(
                f"Recording exceeded maximum duration of {self._max_duration}s"
            )

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        try:
            import soundfile as sf
            sf.write(str(tmp_path), audio, self._sample_rate, subtype="PCM_16")
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise MicrophoneUnavailableError(f"Failed to write audio file: {exc}") from exc

        logger.info("Audio saved path={} size_bytes={}", tmp_path, tmp_path.stat().st_size)
        return RecordingResult(
            file_path=tmp_path,
            duration_seconds=round(duration, 2),
            sample_rate=self._sample_rate,
        )
