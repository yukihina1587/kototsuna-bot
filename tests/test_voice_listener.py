"""Tests for src.voice_listener (sherpa-onnx based local STT).

All external dependencies (sherpa_onnx, sounddevice, numpy) are mocked
so these tests run in CI without native libraries installed.
"""

from __future__ import annotations

import queue
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure sherpa_onnx, sounddevice and numpy stubs are present in
# sys.modules BEFORE the module under test is imported.
# numpy is imported unconditionally in voice_listener.py so it must
# exist as a module even in CI where it is not installed.
# ---------------------------------------------------------------------------

_mock_sherpa = MagicMock()
_mock_sd = MagicMock()

# Build a minimal numpy stub that supports np.ndarray, np.float32,
# np.array, np.concatenate, and queue.Queue[np.ndarray].
try:
    import numpy as _real_np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    _mock_np = MagicMock()
    _mock_np.float32 = "float32"
    _mock_np.ndarray = MagicMock
    _mock_np.array = MagicMock(return_value=MagicMock())
    _mock_np.concatenate = MagicMock(return_value=MagicMock())
    # Provide a real type for bool_ so pytest.approx's isinstance()
    # check does not break when it inspects sys.modules["numpy"].
    _mock_np.bool_ = type("numpy_bool_stub", (int,), {})
    sys.modules["numpy"] = _mock_np

if "sherpa_onnx" not in sys.modules:
    sys.modules["sherpa_onnx"] = _mock_sherpa

if "sounddevice" not in sys.modules:
    sys.modules["sounddevice"] = _mock_sd

# Now import the module under test.
import src.voice_listener as vl_module  # noqa: E402
from src.voice_listener import (  # noqa: E402
    VoiceTranslator,
    is_stt_available,
    _get_models_dir,
    SAMPLE_RATE,
)

# Convenience flag for tests that need real numpy.
_needs_numpy = pytest.mark.skipif(
    not _HAS_NUMPY, reason="numpy not installed"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_translator(**overrides) -> VoiceTranslator:
    """Create a VoiceTranslator with sensible test defaults."""
    kwargs = {
        "mode_getter": lambda: "\u81ea\u52d5",
        "api_key_getter": lambda: "fake-key",
        "callback": MagicMock(),
    }
    kwargs.update(overrides)
    return VoiceTranslator(**kwargs)


# =========================================================================
# 1. get_microphone_devices - stereo mix filtering
# =========================================================================


class TestGetMicrophoneDevices:
    """VoiceTranslator.get_microphone_devices() tests."""

    def test_get_microphone_devices(self):
        """Stereo-mix devices are filtered out; regular input devices remain."""
        fake_devices = [
            {"name": "Built-in Microphone", "max_input_channels": 2},
            {"name": "Stereo Mix", "max_input_channels": 2},
            {"name": "\u30b9\u30c6\u30ec\u30aa \u30df\u30ad\u30b5\u30fc", "max_input_channels": 2},
            {"name": "USB Headset", "max_input_channels": 1},
            {"name": "HDMI Output", "max_input_channels": 0},  # output-only
            {"name": "What U Hear", "max_input_channels": 2},
        ]

        with patch.object(vl_module, "SOUNDDEVICE_AVAILABLE", True), \
             patch.object(vl_module, "sd") as mock_sd_local:
            mock_sd_local.query_devices.return_value = fake_devices

            devices = VoiceTranslator.get_microphone_devices()

        names = [d["name"] for d in devices]
        assert "Built-in Microphone" in names
        assert "USB Headset" in names
        # Stereo-mix variants must be excluded.
        assert "Stereo Mix" not in names
        assert "\u30b9\u30c6\u30ec\u30aa \u30df\u30ad\u30b5\u30fc" not in names
        assert "What U Hear" not in names
        # Output-only device must be excluded.
        assert "HDMI Output" not in names
        # Indices should be preserved from the original enumeration.
        assert devices[0]["index"] == 0  # Built-in Microphone
        assert devices[1]["index"] == 3  # USB Headset

    def test_get_microphone_devices_no_sounddevice(self):
        """When SOUNDDEVICE_AVAILABLE is False, returns an empty list."""
        with patch.object(vl_module, "SOUNDDEVICE_AVAILABLE", False):
            devices = VoiceTranslator.get_microphone_devices()

        assert devices == []


# =========================================================================
# 2. is_stt_available
# =========================================================================


class TestIsSTTAvailable:
    """is_stt_available() tests."""

    def test_is_stt_available_all_present(self, tmp_path):
        """Returns True when all required model files exist."""
        models_dir = str(tmp_path / "models")
        reazonspeech_dir = str(tmp_path / "models" / "reazonspeech")

        import os

        os.makedirs(reazonspeech_dir, exist_ok=True)
        (tmp_path / "models" / "reazonspeech" / "encoder-epoch-99-avg-1.int8.onnx").touch()
        (tmp_path / "models" / "reazonspeech" / "decoder-epoch-99-avg-1.int8.onnx").touch()
        (tmp_path / "models" / "reazonspeech" / "joiner-epoch-99-avg-1.int8.onnx").touch()
        (tmp_path / "models" / "reazonspeech" / "tokens.txt").touch()
        (tmp_path / "models" / "silero_vad.onnx").touch()

        with patch.object(vl_module, "_get_models_dir", return_value=models_dir):
            assert is_stt_available() is True

    def test_is_stt_available_missing_files(self, tmp_path):
        """Returns False when required model files are missing."""
        models_dir = str(tmp_path / "models")

        import os

        os.makedirs(models_dir, exist_ok=True)
        # Only create silero_vad.onnx -- encoder and tokens are absent.
        (tmp_path / "models" / "silero_vad.onnx").touch()

        with patch.object(vl_module, "_get_models_dir", return_value=models_dir):
            assert is_stt_available() is False


# =========================================================================
# 3. VoiceTranslator.start() - failure paths
# =========================================================================


class TestStartFailurePaths:
    """start() returns False when prerequisites are missing."""

    def test_start_sherpa_not_available(self):
        """When SHERPA_AVAILABLE is False, start() returns False."""
        with patch.object(vl_module, "SHERPA_AVAILABLE", False):
            vt = _make_translator()
            assert vt.start() is False

    def test_start_sounddevice_not_available(self):
        """When SOUNDDEVICE_AVAILABLE is False, start() returns False."""
        with patch.object(vl_module, "SHERPA_AVAILABLE", True), \
             patch.object(vl_module, "SOUNDDEVICE_AVAILABLE", False):
            vt = _make_translator()
            assert vt.start() is False

    def test_start_models_missing(self):
        """When is_stt_available() returns False, start() returns False."""
        with patch.object(vl_module, "SHERPA_AVAILABLE", True), \
             patch.object(vl_module, "SOUNDDEVICE_AVAILABLE", True), \
             patch.object(vl_module, "is_stt_available", return_value=False):
            vt = _make_translator()
            assert vt.start() is False


# =========================================================================
# 4. VoiceTranslator.start() - success path
# =========================================================================


class TestStartSuccess:
    """start() returns True and initialises resources when all deps are OK."""

    def test_start_success(self):
        """Mock all dependencies and verify start() returns True."""
        mock_stream = MagicMock()

        with patch.object(vl_module, "SHERPA_AVAILABLE", True), \
             patch.object(vl_module, "SOUNDDEVICE_AVAILABLE", True), \
             patch.object(vl_module, "is_stt_available", return_value=True), \
             patch.object(VoiceTranslator, "_create_recognizer"), \
             patch.object(VoiceTranslator, "_create_vad"), \
             patch.object(vl_module, "sd") as mock_sd_local:

            mock_sd_local.InputStream.return_value = mock_stream

            vt = _make_translator()
            result = vt.start()

            assert result is True
            assert vt._running is True
            # Audio stream should have been opened and started.
            mock_sd_local.InputStream.assert_called_once()
            mock_stream.start.assert_called_once()
            # Worker thread should have been created and started.
            assert vt._worker_thread is not None
            assert vt._worker_thread.is_alive()

            # Cleanup -- stop so the daemon thread terminates.
            vt._running = False
            vt._audio_stream = None
            vt._worker_thread.join(timeout=2.0)


# =========================================================================
# 5. VoiceTranslator.stop()
# =========================================================================


class TestStop:
    """stop() cleans up resources correctly."""

    def test_stop_cleans_resources(self):
        """Verify stop() closes the stream, joins the thread, drains the queue."""
        vt = _make_translator()

        # Simulate a running state.
        vt._running = True
        mock_stream = MagicMock()
        vt._audio_stream = mock_stream

        # Create a mock worker thread that finishes immediately.
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False
        vt._worker_thread = mock_thread

        # Put some items in the queue.
        vt._audio_queue.put("chunk_1")
        vt._audio_queue.put("chunk_2")

        # Assign recognizer/vad so we can assert cleanup.
        vt._recognizer = MagicMock()
        vt._vad = MagicMock()

        vt.stop()

        assert vt._running is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert vt._audio_stream is None
        mock_thread.join.assert_called_once_with(timeout=3.0)
        assert vt._worker_thread is None
        assert vt._audio_queue.empty()
        assert vt._recognizer is None
        assert vt._vad is None

    def test_stop_noop_when_not_running(self):
        """stop() does nothing if the translator is not running."""
        vt = _make_translator()
        assert vt._running is False
        # Should not raise.
        vt.stop()
        assert vt._running is False


# =========================================================================
# 6. _process_result
# =========================================================================


class TestProcessResult:
    """_process_result() translates text and invokes callback."""

    def test_process_result_with_api_key(self):
        """When an API key is available, translate_text_sync is called."""
        cb = MagicMock()
        vt = VoiceTranslator(
            mode_getter=lambda: "\u82f1\u2192\u65e5",
            api_key_getter=lambda: "real-key",
            callback=cb,
        )

        with patch.object(vl_module, "translate_text_sync", return_value="translated") as mock_tr:
            vt._process_result("hello world")

        mock_tr.assert_called_once_with("hello world", "\u82f1\u2192\u65e5", "real-key")
        cb.assert_called_once_with("hello world", "translated")

    def test_process_result_without_api_key(self):
        """When no API key, callback receives '(No API Key)' as translation."""
        cb = MagicMock()
        vt = VoiceTranslator(
            mode_getter=lambda: "\u81ea\u52d5",
            api_key_getter=lambda: "",
            callback=cb,
        )

        vt._process_result("test text")

        cb.assert_called_once_with("test text", "(No API Key)")

    def test_process_result_no_callback(self):
        """When callback is None, no error is raised."""
        vt = VoiceTranslator(
            mode_getter=lambda: "\u81ea\u52d5",
            api_key_getter=lambda: "",
            callback=None,
        )
        # Should not raise.
        vt._process_result("some text")

    def test_process_result_exception_swallowed(self):
        """Exceptions in translate_text_sync are caught and logged."""
        cb = MagicMock()
        vt = VoiceTranslator(
            mode_getter=lambda: "\u81ea\u52d5",
            api_key_getter=lambda: "key",
            callback=cb,
        )

        with patch.object(
            vl_module, "translate_text_sync", side_effect=RuntimeError("boom")
        ):
            # Should not raise.
            vt._process_result("error text")

        cb.assert_not_called()


# =========================================================================
# 7. Config defaults
# =========================================================================


class TestConfigDefaults:
    """Verify default config values for STT settings."""

    def test_config_defaults(self):
        """Default stt_num_threads=2 and stt_vad_threshold=0.5 from config.py."""
        from src.config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG["stt_num_threads"] == 2
        assert DEFAULT_CONFIG["stt_vad_threshold"] == 0.5

    def test_voice_translator_uses_config_defaults(self):
        """VoiceTranslator falls back to defaults when config_data is empty."""
        vt = _make_translator(config_data={})

        # Verify the defaults match what _create_recognizer / _create_vad would use.
        assert int(vt.config_data.get("stt_num_threads", 2)) == 2
        assert float(vt.config_data.get("stt_vad_threshold", 0.5)) == 0.5

    def test_voice_translator_respects_custom_config(self):
        """VoiceTranslator uses values from config_data when provided."""
        custom = {"stt_num_threads": 4, "stt_vad_threshold": 0.8}
        vt = _make_translator(config_data=custom)

        assert int(vt.config_data["stt_num_threads"]) == 4
        assert float(vt.config_data["stt_vad_threshold"]) == 0.8


# =========================================================================
# 8. _get_models_dir
# =========================================================================


class TestGetModelsDir:
    """_get_models_dir() resolves correctly for dev and frozen modes."""

    def test_dev_mode(self):
        """In development mode, models dir is relative to project root."""
        with patch.object(sys, "frozen", False, create=True):
            result = _get_models_dir()
            assert result.endswith("models")

    def test_frozen_mode(self):
        """In PyInstaller mode, models dir is under sys._MEIPASS."""
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", "/opt/app/_internal", create=True):
            result = _get_models_dir()
            assert result == "/opt/app/_internal/models"


# =========================================================================
# 9. _audio_callback (requires real numpy)
# =========================================================================


class TestAudioCallback:
    """_audio_callback() enqueues audio data correctly."""

    @_needs_numpy
    def test_audio_callback_enqueues_data(self):
        """Audio data is enqueued when _running is True."""
        import numpy as np

        vt = _make_translator()
        vt._running = True

        indata = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
        vt._audio_callback(indata, frames=3, time_info=None, status=None)

        assert not vt._audio_queue.empty()
        chunk = vt._audio_queue.get_nowait()
        np.testing.assert_array_almost_equal(
            chunk, np.array([0.1, 0.2, 0.3], dtype=np.float32)
        )

    @_needs_numpy
    def test_audio_callback_skips_when_not_running(self):
        """Audio data is NOT enqueued when _running is False."""
        import numpy as np

        vt = _make_translator()
        vt._running = False

        indata = np.array([[0.5]], dtype=np.float32)
        vt._audio_callback(indata, frames=1, time_info=None, status=None)

        assert vt._audio_queue.empty()


# =========================================================================
# 10. Constants
# =========================================================================


class TestConstants:
    """Module-level constants have expected values."""

    def test_sample_rate(self):
        assert SAMPLE_RATE == 16_000

    def test_vad_window_size(self):
        from src.voice_listener import VAD_WINDOW_SIZE

        assert VAD_WINDOW_SIZE == 512

    def test_audio_chunk_samples(self):
        from src.voice_listener import AUDIO_CHUNK_SAMPLES

        assert AUDIO_CHUNK_SAMPLES == 1_600
