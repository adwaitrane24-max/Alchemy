"""Voice subsystem exceptions."""

from __future__ import annotations


class VoiceError(Exception):
    """Base exception for all voice-related errors."""


class MicrophoneUnavailableError(VoiceError):
    """Raised when no microphone is detected or permission is denied."""


class RecordingTimeoutError(VoiceError):
    """Raised when recording exceeds the maximum allowed duration."""


class TranscriptionError(VoiceError):
    """Raised when the STT API fails to produce a transcript."""


class TranscriptionTimeoutError(TranscriptionError):
    """Raised when the STT API does not respond within the timeout."""
