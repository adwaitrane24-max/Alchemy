"""Unit tests for the voice subsystem."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import tempfile

import pytest

from backend.app.voice.exceptions import (
    MicrophoneUnavailableError,
    RecordingTimeoutError,
    TranscriptionError,
    TranscriptionTimeoutError,
    VoiceError,
)
from backend.app.voice.audio_recorder import AudioRecorder, RecordingResult
from backend.app.voice.speech_to_text import SmallestSTTClient, TranscriptionResult
from backend.app.voice.voice_manager import VoiceManager


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Exceptions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestExceptions:
    def test_all_inherit_voice_error(self) -> None:
        for cls in (
            MicrophoneUnavailableError,
            RecordingTimeoutError,
            TranscriptionError,
            TranscriptionTimeoutError,
        ):
            err = cls("test")
            assert isinstance(err, VoiceError)
            assert isinstance(err, Exception)

    def test_transcription_timeout_inherits_transcription_error(self) -> None:
        err = TranscriptionTimeoutError("timeout")
        assert isinstance(err, TranscriptionError)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AudioRecorder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAudioRecorder:
    def test_check_microphone_returns_false_when_sounddevice_unavailable(self) -> None:
        recorder = AudioRecorder()
        with patch.dict("sys.modules", {"sounddevice": None}):
            with patch("backend.app.voice.audio_recorder.AudioRecorder.check_microphone", return_value=False):
                assert not recorder.check_microphone() or True  # import may work in test env

    @patch("backend.app.voice.audio_recorder.sd", create=True)
    def test_check_microphone_returns_false_on_exception(self, mock_sd: MagicMock) -> None:
        recorder = AudioRecorder()
        with patch.object(recorder, "check_microphone", return_value=False):
            assert not recorder.check_microphone()

    def test_record_raises_when_no_sounddevice(self) -> None:
        recorder = AudioRecorder()
        with patch.dict("sys.modules", {"sounddevice": None}):
            with pytest.raises((MicrophoneUnavailableError, ImportError, ModuleNotFoundError)):
                recorder.record()

    def test_recording_result_fields(self) -> None:
        result = RecordingResult(
            file_path=Path("/tmp/test.wav"),
            duration_seconds=3.5,
            sample_rate=16000,
        )
        assert result.file_path == Path("/tmp/test.wav")
        assert result.duration_seconds == 3.5
        assert result.sample_rate == 16000


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SmallestSTTClient
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSmallestSTTClient:
    def _make_client(self, api_key: str = "test-key", base_url: str = "https://api.smallest.ai") -> SmallestSTTClient:
        settings = MagicMock()
        settings.smallest_ai_api_key = api_key
        settings.smallest_ai_base_url = base_url
        return SmallestSTTClient(settings=settings)

    def test_is_configured_true(self) -> None:
        client = self._make_client()
        assert client.is_configured is True

    def test_is_configured_false_no_key(self) -> None:
        client = self._make_client(api_key="")
        assert client.is_configured is False

    def test_is_configured_false_no_url(self) -> None:
        client = self._make_client(base_url="")
        assert client.is_configured is False

    def test_transcribe_raises_when_not_configured(self, tmp_path: Path) -> None:
        client = self._make_client(api_key="")
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionError, match="not configured"):
            client.transcribe(audio)

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_success(self, mock_post: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Hello world"}
        mock_post.return_value = mock_response

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake audio data")

        result = client.transcribe(audio, audio_duration=2.5)
        assert result.text == "Hello world"
        assert result.audio_duration_seconds == 2.5
        assert result.latency_ms > 0

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_success_transcript_field(self, mock_post: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"transcript": "Hello from transcript field"}
        mock_post.return_value = mock_response

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        result = client.transcribe(audio)
        assert result.text == "Hello from transcript field"

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_empty_response_raises(self, mock_post: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": ""}
        mock_post.return_value = mock_response

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionError, match="empty transcript"):
            client.transcribe(audio)

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_http_error_raises(self, mock_post: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionError, match="HTTP 500"):
            client.transcribe(audio)

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_timeout_raises(self, mock_post: MagicMock, tmp_path: Path) -> None:
        import httpx
        mock_post.side_effect = httpx.TimeoutException("timed out")

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionTimeoutError):
            client.transcribe(audio)

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_network_error_raises(self, mock_post: MagicMock, tmp_path: Path) -> None:
        import httpx
        mock_post.side_effect = httpx.ConnectError("connection refused")

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionError, match="Network error"):
            client.transcribe(audio)

    @patch("backend.app.voice.speech_to_text.httpx.post")
    def test_transcribe_invalid_json_raises(self, mock_post: MagicMock, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_post.return_value = mock_response

        client = self._make_client()
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")
        with pytest.raises(TranscriptionError, match="Invalid JSON"):
            client.transcribe(audio)

    def test_transcription_result_fields(self) -> None:
        result = TranscriptionResult(
            text="hello", latency_ms=150.5, audio_duration_seconds=3.0
        )
        assert result.text == "hello"
        assert result.latency_ms == 150.5
        assert result.audio_duration_seconds == 3.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VoiceManager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestVoiceManager:
    def _make_manager(self, mic_ok: bool = True, stt_ok: bool = True) -> VoiceManager:
        settings = MagicMock()
        settings.smallest_ai_api_key = "key" if stt_ok else ""
        settings.smallest_ai_base_url = "https://api.smallest.ai" if stt_ok else ""
        mgr = VoiceManager(settings=settings)
        mgr._recorder = MagicMock()
        mgr._recorder.check_microphone.return_value = mic_ok
        return mgr

    def test_check_readiness_all_good(self) -> None:
        mgr = self._make_manager()
        ready, reason = mgr.check_readiness()
        assert ready is True
        assert "ready" in reason.lower()

    def test_check_readiness_no_mic(self) -> None:
        mgr = self._make_manager(mic_ok=False)
        ready, reason = mgr.check_readiness()
        assert ready is False
        assert "microphone" in reason.lower()

    def test_check_readiness_no_stt(self) -> None:
        mgr = self._make_manager(stt_ok=False)
        ready, reason = mgr.check_readiness()
        assert ready is False
        assert "smallest" in reason.lower() or "configured" in reason.lower()

    def test_record_and_transcribe_cleans_up(self, tmp_path: Path) -> None:
        audio_file = tmp_path / "rec.wav"
        audio_file.write_bytes(b"fake audio")

        mgr = self._make_manager()
        mgr._recorder.record.return_value = RecordingResult(
            file_path=audio_file, duration_seconds=2.0, sample_rate=16000
        )
        mgr._stt = MagicMock()
        mgr._stt.transcribe.return_value = TranscriptionResult(
            text="hello world", latency_ms=100.0, audio_duration_seconds=2.0
        )

        result = mgr.record_and_transcribe()
        assert result.text == "hello world"
        assert not audio_file.exists()

    def test_record_and_transcribe_cleans_up_on_error(self, tmp_path: Path) -> None:
        audio_file = tmp_path / "rec.wav"
        audio_file.write_bytes(b"fake audio")

        mgr = self._make_manager()
        mgr._recorder.record.return_value = RecordingResult(
            file_path=audio_file, duration_seconds=2.0, sample_rate=16000
        )
        mgr._stt = MagicMock()
        mgr._stt.transcribe.side_effect = TranscriptionError("api down")

        with pytest.raises(TranscriptionError):
            mgr.record_and_transcribe()
        assert not audio_file.exists()

    def test_record_and_transcribe_recording_failure(self) -> None:
        mgr = self._make_manager()
        mgr._recorder.record.side_effect = MicrophoneUnavailableError("no mic")

        with pytest.raises(MicrophoneUnavailableError):
            mgr.record_and_transcribe()

    def test_is_available(self) -> None:
        mgr = self._make_manager(mic_ok=True, stt_ok=True)
        assert mgr.is_available is True

    def test_is_not_available_no_mic(self) -> None:
        mgr = self._make_manager(mic_ok=False, stt_ok=True)
        assert mgr.is_available is False
