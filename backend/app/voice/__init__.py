"""Voice input — Smallest.ai STT integration.

Heavy dependencies (numpy, sounddevice) are imported lazily so the CLI
starts even when they are not installed.
"""

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


def __getattr__(name: str):
    if name == "VoiceManager":
        from backend.app.voice.voice_manager import VoiceManager
        return VoiceManager
    if name == "AudioRecorder":
        from backend.app.voice.audio_recorder import AudioRecorder
        return AudioRecorder
    if name == "RecordingResult":
        from backend.app.voice.audio_recorder import RecordingResult
        return RecordingResult
    if name == "SmallestSTTClient":
        from backend.app.voice.speech_to_text import SmallestSTTClient
        return SmallestSTTClient
    if name == "TranscriptionResult":
        from backend.app.voice.speech_to_text import TranscriptionResult
        return TranscriptionResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
