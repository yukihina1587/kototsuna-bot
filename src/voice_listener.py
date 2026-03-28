"""Local speech recognition using sherpa-onnx ReazonSpeech-k2-v2 + Silero VAD.

Replaces the previous Gladia/Google SR implementation with fully offline
recognition powered by sherpa-onnx transducer models.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import ctypes
from collections import deque
from typing import Any, Callable, Optional

from src.logger import logger
from src.translator import translate_text_sync

# --- Optional dependency availability checks ---------------------------------

_dll_dir_handles: list[object] = []


def _prepare_windows_numpy_dlls() -> None:
    """Register and preload DLL directories needed by numpy in frozen Windows builds."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return

    candidates: list[str] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.extend([
            meipass,
            os.path.join(meipass, "numpy.libs"),
        ])

    runtime_cache = os.environ.get("KOTOTSUNA_RUNTIME_CACHE", "")
    if runtime_cache:
        pyd_cache = os.path.join(runtime_cache, "pyd_cache")
        candidates.extend([
            pyd_cache,
            os.path.join(pyd_cache, "numpy.libs"),
        ])

    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "executable", "") else ""
    if exe_dir:
        candidates.append(exe_dir)

    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen or not os.path.isdir(path):
            continue
        seen.add(path)
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                _dll_dir_handles.append(os.add_dll_directory(path))
            except OSError as err:
                logger.warning(f"Failed to register DLL dir {path}: {err!r}")

        try:
            for name in os.listdir(path):
                low = name.lower()
                if not low.endswith(".dll"):
                    continue
                if any(token in low for token in ("openblas", "vcruntime140", "msvcp140", "python312")):
                    ctypes.WinDLL(os.path.join(path, name))
        except OSError as err:
            logger.warning(f"Failed to preload DLLs from {path}: {err!r}")


_numpy_import_error: str | None = None
try:
    _prepare_windows_numpy_dlls()
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception as _numpy_err:
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False
    _numpy_import_error = str(_numpy_err)
    logger.warning(f"numpy import failed: {_numpy_err!r}. Speech recognition will be unavailable.")

_sherpa_import_error: str | None = None
try:
    import sherpa_onnx
    SHERPA_AVAILABLE = True
except Exception as _sherpa_err:
    SHERPA_AVAILABLE = False
    _sherpa_import_error = str(_sherpa_err)
    logger.warning(
        f"sherpa_onnx import failed: {_sherpa_err!r}. Speech recognition will be unavailable."
    )

_sounddevice_import_error: str | None = None
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except Exception as _sd_err:
    sd = None  # type: ignore[assignment]
    SOUNDDEVICE_AVAILABLE = False
    _sounddevice_import_error = str(_sd_err)
    logger.warning(
        f"sounddevice import failed: {_sd_err!r}. Speech recognition will be unavailable."
    )

# --- Constants ----------------------------------------------------------------

SAMPLE_RATE: int = 16_000
VAD_WINDOW_SIZE: int = 512
AUDIO_CHUNK_SAMPLES: int = 1_600  # 100 ms at 16 kHz
PRE_ROLL_SECONDS: float = 0.3  # VADトリガー前の音声を保持する秒数


# --- Model path helpers -------------------------------------------------------


def _get_models_dir() -> str:
    """Return the absolute path to the ``models/`` directory.

    * PyInstaller (frozen): next to the executable.
    * Development: project root (one level above ``src/``).
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "models")
    return os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "models"
    )


def is_stt_available() -> bool:
    """Return *True* when the required STT model files are present on disk."""
    models_dir = _get_models_dir()
    required_files = [
        os.path.join(models_dir, "reazonspeech", "encoder-epoch-99-avg-1.int8.onnx"),
        os.path.join(models_dir, "reazonspeech", "decoder-epoch-99-avg-1.int8.onnx"),
        os.path.join(models_dir, "reazonspeech", "joiner-epoch-99-avg-1.int8.onnx"),
        os.path.join(models_dir, "reazonspeech", "tokens.txt"),
        os.path.join(models_dir, "silero_vad.onnx"),
    ]
    return all(os.path.exists(f) for f in required_files)


# --- VoiceTranslator ---------------------------------------------------------


class VoiceTranslator:
    """Capture microphone audio, detect speech with Silero VAD, recognise with
    ReazonSpeech-k2-v2, and pass the recognised text through local translation.
    """

    # Keywords used to filter out stereo-mix / loopback virtual devices.
    STEREO_MIX_KEYWORDS: list[str] = [
        "stereo mix",
        "ステレオ ミキサー",
        "ステレオミキサー",
        "what u hear",
        "wave out",
    ]

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_microphone_devices() -> list[dict[str, Any]]:
        """Return a list of input devices, excluding stereo-mix variants.

        Each element is ``{'index': int, 'name': str}``.
        """
        devices: list[dict[str, Any]] = []
        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice is not available; cannot enumerate devices.")
            return devices

        try:
            all_devices = sd.query_devices()
            for i, dev in enumerate(all_devices):
                if dev["max_input_channels"] > 0:
                    name: str = dev["name"]
                    name_lower = name.lower()
                    is_stereo_mix = any(
                        kw in name_lower for kw in VoiceTranslator.STEREO_MIX_KEYWORDS
                    )
                    if not is_stereo_mix:
                        devices.append({"index": i, "name": name})
        except Exception as e:
            logger.error(f"Failed to get microphone devices: {e}")
        return devices

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        mode_getter: Callable[[], str],
        api_key_getter: Callable[[], str],
        callback: Optional[Callable[[str, str], None]],
        config_data: Optional[dict[str, Any]] = None,
        device_index: Optional[int] = None,
    ) -> None:
        """Initialise the voice translator.

        Parameters
        ----------
        mode_getter:
            Callable returning the current translation mode string.
        api_key_getter:
            Legacy callable kept for compatibility. Local translation does not use an API key.
        callback:
            ``callback(recognised_text, translated_text)`` invoked on each
            final recognition result.
        config_data:
            Application configuration dictionary.  Relevant keys:
            ``stt_num_threads`` (default 2), ``stt_vad_threshold`` (default 0.5).
        device_index:
            Microphone device index for *sounddevice*.  ``None`` selects the
            system default input device.
        """
        self.mode_getter = mode_getter
        self.api_key_getter = api_key_getter
        self.callback = callback
        self.config_data: dict[str, Any] = config_data or {}
        self.device_index = device_index

        # Internal state
        self._running: bool = False
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._audio_stream: Optional[Any] = None  # sd.InputStream

        # sherpa-onnx handles (created in start())
        self._recognizer: Optional[Any] = None  # sherpa_onnx.OfflineRecognizer
        self._vad: Optional[Any] = None  # sherpa_onnx.VoiceActivityDetector
        self._vad_window_size: int = VAD_WINDOW_SIZE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start audio capture and recognition.  Returns *True* on success."""
        logger.info("VoiceTranslator.start() called")

        if self._running:
            logger.warning("VoiceTranslator is already running.")
            return True

        # --- Pre-flight checks ---
        if not NUMPY_AVAILABLE:
            logger.error("numpy is not installed. Cannot start STT.")
            return False

        if not SHERPA_AVAILABLE:
            logger.error("sherpa_onnx is not installed. Cannot start STT.")
            return False

        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice is not installed. Cannot start STT.")
            return False

        if not is_stt_available():
            logger.error(
                "STT model files are missing.  "
                f"Expected under: {_get_models_dir()}"
            )
            return False

        # --- Create recognizer and VAD ---
        try:
            self._create_recognizer()
            self._create_vad()
        except Exception as e:
            logger.error(f"Failed to initialise sherpa-onnx: {e}", exc_info=True)
            self._recognizer = None
            self._vad = None
            return False

        # --- Open audio stream ---
        try:
            self._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=AUDIO_CHUNK_SAMPLES,
                device=self.device_index,
                callback=self._audio_callback,
            )
            self._audio_stream.start()
            logger.info(
                f"Audio stream opened (device_index={self.device_index}, "
                f"sample_rate={SAMPLE_RATE})"
            )
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}", exc_info=True)
            self._recognizer = None
            self._vad = None
            return False

        # --- Start worker thread ---
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._recognition_worker, daemon=True, name="stt-worker"
        )
        self._worker_thread.start()

        logger.info("VoiceTranslator started successfully (sherpa-onnx local STT).")
        return True

    def stop(self) -> None:
        """Stop recognition and release all resources."""
        if not self._running:
            logger.debug("VoiceTranslator.stop() called but not running.")
            return

        logger.info("Stopping VoiceTranslator...")
        self._running = False

        # Stop the audio stream first so no new data enters the queue.
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
                logger.info("Audio stream closed.")
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}", exc_info=True)
            finally:
                self._audio_stream = None

        # Wait for the worker thread to finish.
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=3.0)
            if self._worker_thread.is_alive():
                logger.warning("STT worker thread did not exit within timeout.")
            self._worker_thread = None

        # Drain the queue so it does not hold stale references.
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        self._recognizer = None
        self._vad = None

        logger.info("VoiceTranslator stopped.")

    # ------------------------------------------------------------------
    # Internals -- model creation
    # ------------------------------------------------------------------

    def _create_recognizer(self) -> None:
        """Instantiate the sherpa-onnx OfflineRecognizer (transducer).

        sherpa-onnx uses narrow (ANSI) file I/O on Windows, so paths with
        non-ASCII characters cause silent failures.  We temporarily change
        CWD to the models parent directory and pass relative paths.
        """
        models_dir = _get_models_dir()
        # Parent of models/ — used as CWD anchor for relative paths
        base_dir = os.path.dirname(models_dir)
        reazonspeech_rel = os.path.join("models", "reazonspeech")

        num_threads: int = int(self.config_data.get("stt_num_threads", 2))

        encoder_rel = os.path.join(reazonspeech_rel, "encoder-epoch-99-avg-1.int8.onnx")
        decoder_rel = os.path.join(reazonspeech_rel, "decoder-epoch-99-avg-1.int8.onnx")
        joiner_rel = os.path.join(reazonspeech_rel, "joiner-epoch-99-avg-1.int8.onnx")
        tokens_rel = os.path.join(reazonspeech_rel, "tokens.txt")

        # Verify files exist using absolute paths
        for name, rel in [("encoder", encoder_rel), ("decoder", decoder_rel),
                          ("joiner", joiner_rel), ("tokens", tokens_rel)]:
            abs_path = os.path.join(base_dir, rel)
            exists = os.path.exists(abs_path)
            size = os.path.getsize(abs_path) if exists else 0
            logger.info(f"  {name}: {abs_path} (exists={exists}, size={size:,} bytes)")

        logger.info(
            f"Creating OfflineRecognizer (num_threads={num_threads}, "
            f"sherpa_onnx={sherpa_onnx.__version__}, cwd_anchor={base_dir})"
        )

        # Change CWD so sherpa-onnx receives ASCII-only relative paths
        prev_cwd = os.getcwd()
        try:
            os.chdir(base_dir)
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=encoder_rel,
                decoder=decoder_rel,
                joiner=joiner_rel,
                tokens=tokens_rel,
                num_threads=num_threads,
                provider="cpu",
                decoding_method="greedy_search",
                feature_dim=80,
                sample_rate=SAMPLE_RATE,
            )
        finally:
            os.chdir(prev_cwd)

        logger.info("OfflineRecognizer created.")

    def _create_vad(self) -> None:
        """Instantiate the Silero VAD via sherpa-onnx."""
        models_dir = _get_models_dir()
        base_dir = os.path.dirname(models_dir)
        vad_rel = os.path.join("models", "silero_vad.onnx")
        vad_threshold: float = float(self.config_data.get("stt_vad_threshold", 0.2))

        logger.info(
            f"Creating VoiceActivityDetector (threshold={vad_threshold}, "
            f"model={os.path.join(base_dir, vad_rel)})"
        )

        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.threshold = vad_threshold
        vad_config.silero_vad.min_silence_duration = 0.5
        vad_config.silero_vad.min_speech_duration = 0.1
        vad_config.silero_vad.max_speech_duration = 20.0
        vad_config.silero_vad.window_size = self._vad_window_size
        vad_config.sample_rate = SAMPLE_RATE

        prev_cwd = os.getcwd()
        try:
            os.chdir(base_dir)
            vad_config.silero_vad.model = vad_rel
            self._vad = sherpa_onnx.VoiceActivityDetector(
                vad_config, buffer_size_in_seconds=30
            )
        finally:
            os.chdir(prev_cwd)

        logger.info("VoiceActivityDetector created.")

    # ------------------------------------------------------------------
    # Internals -- audio pipeline
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """Called by sounddevice for each audio block.  Enqueues samples."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        if self._running:
            # indata shape is (frames, 1) -- flatten to 1-D float32.
            self._audio_queue.put(indata[:, 0].copy())

    def _recognition_worker(self) -> None:
        """Worker thread: reads audio from the queue, runs VAD, recognises."""
        logger.info("STT worker thread started.")
        buffer = np.array([], dtype=np.float32)

        # Ring buffer: VADトリガー前の音声を保持し、発話冒頭の欠落を防ぐ
        pre_roll_size = int(SAMPLE_RATE * PRE_ROLL_SECONDS)
        pre_roll: deque[float] = deque(maxlen=pre_roll_size)

        while self._running:
            # Fetch the next audio chunk (with timeout so we can check _running).
            try:
                samples = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            buffer = np.concatenate([buffer, samples])

            # Feed VAD in window-sized chunks.
            while len(buffer) >= self._vad_window_size:
                chunk = buffer[: self._vad_window_size]
                self._vad.accept_waveform(chunk)
                buffer = buffer[self._vad_window_size :]
                # Keep recent audio in ring buffer for pre-roll
                pre_roll.extend(chunk)

            # Process every completed speech segment.
            while not self._vad.empty():
                speech_samples = self._vad.front.samples
                self._vad.pop()

                # Prepend pre-roll audio to capture speech onset
                if pre_roll:
                    pre_roll_array = np.array(pre_roll, dtype=np.float32)
                    speech_samples = np.concatenate([pre_roll_array, speech_samples])
                    pre_roll.clear()

                stream = self._recognizer.create_stream()
                stream.accept_waveform(SAMPLE_RATE, speech_samples)
                self._recognizer.decode_stream(stream)

                text: str = stream.result.text.strip()
                if text:
                    self._process_result(text)

        logger.info("STT worker thread exiting.")

    # ------------------------------------------------------------------
    # Internals -- result handling
    # ------------------------------------------------------------------

    def _process_result(self, text: str) -> None:
        """Translate recognised text and invoke the user callback."""
        try:
            mode = self.mode_getter()
            logger.info(f"Recognized: {text}")

            translated = translate_text_sync(text, mode)

            if self.callback:
                self.callback(text, translated)
        except Exception as e:
            logger.error(f"Result processing error: {e}", exc_info=True)
