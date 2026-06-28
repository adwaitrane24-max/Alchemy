"""Voice input — Smallest.ai STT integration."""

from backend.app.voice.voice_manager import VoiceManager
from backend.app.voice.audio_recorder import AudioRecorder, RecordingResult
from backend.app.voice.speech_to_text import SmallestSTTClient, TranscriptionResult
from backend.app.voice.exceptions import (
    VoiceError,
    MicrophoneUnavailableError,
    RecordingTimeoutError,
    TranscriptionError,
    TranscriptionTimeoutError,
)

__all__ = [
    "VoiceManager",
    "AudioRecorder",
    "RecordingResult",
    "SmallestSTTClient",
    "TranscriptionResult",
    "VoiceError",
    "MicrophoneUnavailableError",
    "RecordingTimeoutError",
    "TranscriptionError",
    "TranscriptionTimeoutError",
]
