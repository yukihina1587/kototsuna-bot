"""
Text-to-Speech module using VOICEVOX API with pyttsx3 fallback
Supports reading Japanese text with Meimei Himari voice (VOICEVOX)
Falls back to pyttsx3 when VOICEVOX is not available
"""
import asyncio
import aiohttp
import json
import threading
import queue
import tempfile
import os
import sys
from datetime import datetime
from pathlib import Path
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from typing import Optional, Tuple
from src.logger import logger
from src.tts_engines import TTSEngine, get_engine, get_preset_url


def _get_tts_log_path() -> Path:
    """TTSログファイルのパスを返す（logger.py と同じディレクトリ規則）"""
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent.parent / "dist"
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return log_dir / f"tts_{today}.txt"


def _append_tts_log(text: str) -> None:
    """読み上げテキストをタイムスタンプ付きでファイルに追記する"""
    try:
        log_path = _get_tts_log_path()
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
    except Exception as e:
        logger.warning(f"TTSログ書き込み失敗: {e}")

# Try to import pygame for audio playback (init is deferred to avoid startup hangs)
pygame = None
PYGAME_IMPORTED = False
PYGAME_INIT_ATTEMPTED = False
AUDIO_AVAILABLE = False
try:
    import pygame as _pygame  # type: ignore
    pygame = _pygame
    PYGAME_IMPORTED = True
except ImportError:
    logger.warning("pygame not installed. TTS playback will fall back to pyttsx3 if available.")

# Try to import pyttsx3 as fallback TTS engine
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    PYTTSX3_AVAILABLE = False
    logger.info("pyttsx3 not installed. Fallback TTS will be unavailable.")

# VOICEVOX settings
VOICEVOX_API_URL = "http://localhost:50021"
# 冥鳴ひまり (Meimei Himari) - Speaker ID
# ノーマル: 14
MEIMEI_HIMARI_SPEAKER_ID = 14


def is_japanese(text: str) -> bool:
    """
    Check if text contains Japanese characters (Hiragana, Katakana, or Kanji)

    Args:
        text: Text to check

    Returns:
        True if text contains Japanese characters
    """
    if not text:
        return False

    japanese_ranges = [
        (0x3040, 0x309F),  # Hiragana
        (0x30A0, 0x30FF),  # Katakana
        (0x4E00, 0x9FFF),  # Kanji (CJK Unified Ideographs)
        (0x3400, 0x4DBF),  # Kanji Extension A
    ]

    for char in text:
        char_code = ord(char)
        for start, end in japanese_ranges:
            if start <= char_code <= end:
                return True
    return False


def clean_text_for_tts(text: str, use_dictionary: bool = True) -> str:
    """
    Clean text for TTS by removing special characters and URLs

    Args:
        text: Original text
        use_dictionary: 辞書を適用するかどうか

    Returns:
        Cleaned text
    """
    import re
    from src.tts_dictionary import get_dictionary

    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

    # Remove @ mentions (keep the name part)
    text = re.sub(r'@(\w+)', r'\1さん', text)

    # Remove emote tags if any
    text = text.replace('<k>', '').replace('</k>', '')

    # Apply dictionary for reading corrections
    if use_dictionary:
        try:
            dictionary = get_dictionary()
            text = dictionary.apply_dictionary(text)
        except Exception as e:
            logger.warning(f"Failed to apply dictionary: {e}")

    # Limit length (VOICEVOX has limits)
    if len(text) > 100:
        text = text[:100] + "..."

    return text.strip()


def _init_pygame_audio(timeout: float = 3.0) -> bool:
    """
    Initialize pygame.mixer with a timeout to avoid freezing the UI if the audio
    driver is unresponsive. Returns True if audio is ready.
    """
    global AUDIO_AVAILABLE, PYGAME_INIT_ATTEMPTED

    if AUDIO_AVAILABLE:
        return True
    if not PYGAME_IMPORTED:
        return False
    if PYGAME_INIT_ATTEMPTED:
        return AUDIO_AVAILABLE

    PYGAME_INIT_ATTEMPTED = True
    result = {"ok": False, "err": None}

    def _worker():
        try:
            pygame.mixer.init()
            result["ok"] = True
        except Exception as e:
            result["err"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        logger.error(f"pygame.mixer.init() timed out after {timeout} seconds. Disabling pygame audio.")
        return False

    if result["ok"]:
        AUDIO_AVAILABLE = True
        logger.info("pygame audio initialized successfully.")
        return True

    logger.error(f"Failed to initialize pygame audio: {result['err']}")
    return False


class VoicevoxTTS:
    """VOICEVOX-compatible TTS handler with pyttsx3 fallback.

    Despite the name, this class now delegates synthesis to a pluggable
    ``TTSEngine`` instance. The default engine is VOICEVOX; other
    API-compatible engines (COEIROINK, AivisSpeech, SHAREVOX) are selected
    by passing a different ``engine_name`` or a preset URL.
    """

    def __init__(
        self,
        api_url: str = VOICEVOX_API_URL,
        speaker_id: int = MEIMEI_HIMARI_SPEAKER_ID,
        engine_name: str = "voicevox",
    ):
        """
        Initialize TTS.

        Args:
            api_url: Engine API endpoint URL (VOICEVOX-compatible HTTP).
            speaker_id: Voice ID for the current engine.
            engine_name: ``voicevox`` / ``coeiroink`` / ``aivisspeech`` / ``sharevox``.
        """
        self.engine_name = engine_name
        self.engine: TTSEngine = get_engine(engine_name, api_url)
        self.api_url = self.engine.api_url
        self.speaker_id = speaker_id
        self.enabled = False

        # Separate queues for synthesis and playback
        self.synthesis_queue = queue.Queue()  # Text to synthesize
        self.play_queue = queue.Queue()  # Audio data to play

        self.synthesis_thread = None
        self.playback_thread = None
        self.stop_worker = False

        # TTS engine mode: 'voicevox' or 'pyttsx3'
        self.engine_mode = 'voicevox'
        self.voicevox_available = False
        self.last_voicevox_check = 0  # タイムスタンプ
        self.voicevox_check_interval = 5  # 5秒ごとにチェック
        self.pyttsx3_engine = None

        # aiohttp session for connection pooling
        self.aio_session = None
        self.aio_loop = None

        # Check if VOICEVOX is available
        self.voicevox_available = self._check_voicevox_availability()

    def _check_voicevox_availability(self):
        """Check if the active engine endpoint responds (synchronous, init path)."""
        try:
            import requests
            logger.debug(f"Checking {self.engine_name} API at {self.api_url}/version")
            response = requests.get(f"{self.api_url}/version", timeout=2)
            if response.status_code == 200:
                logger.info(f"{self.engine_name} API is available at {self.api_url}")
                self._log_speaker_info()
                return True
            return False
        except Exception as e:
            logger.debug(f"{self.engine_name} not available: {e}")
            return False

    def _log_speaker_info(self):
        """Log speaker information (called once at init)"""
        try:
            for voice in self.engine.list_voices_sync(timeout=3.0):
                if voice.get("id") == self.speaker_id:
                    logger.info(
                        f"Found speaker: {voice.get('name')} - {voice.get('style')} (ID: {self.speaker_id})"
                    )
                    return
            logger.warning(f"Speaker ID {self.speaker_id} not found")
        except Exception as e:
            logger.debug(f"Failed to get speaker info: {e}")

    def get_speakers_list(self) -> list:
        """Return available voices from the current engine.

        Returns: List of dicts with ``name``/``style``/``id``/``display`` keys.
        """
        try:
            return self.engine.list_voices_sync()
        except Exception as e:
            logger.error(f"スピーカー一覧取得エラー: {e}")
            return []

    def set_speaker(self, speaker_id: int):
        """Change the active voice ID for the current engine."""
        self.speaker_id = speaker_id
        logger.info(f"{self.engine_name} voice changed to ID: {speaker_id}")

    def switch_engine(
        self,
        engine_name: str,
        api_url: Optional[str] = None,
    ) -> None:
        """Swap out the underlying TTS engine (keeps workers running).

        Args:
            engine_name: ``voicevox`` / ``coeiroink`` / ``aivisspeech`` / ``sharevox``.
            api_url: Optional override. When None, the preset URL is used.
        """
        resolved_url = api_url if api_url else get_preset_url(engine_name)
        self.engine_name = engine_name
        self.engine = get_engine(engine_name, resolved_url)
        self.api_url = self.engine.api_url
        logger.info(
            f"TTS engine switched to {engine_name} at {self.api_url}"
        )
        self.voicevox_available = self._check_voicevox_availability()

    def test_voice(self, text: str = "これはテスト音声です") -> bool:
        """テスト音声を再生"""
        try:
            self.speak(text)
            return True
        except Exception as e:
            logger.error(f"テスト音声再生エラー: {e}")
            return False

    async def _check_voicevox_availability_async(self):
        """Check if the active engine responds (async, used by the worker loop)."""
        if self.aio_session is None:
            return False
        return await self.engine.health_check(self.aio_session, timeout=2.0)

    def _update_engine_mode(self, new_mode: str):
        """
        エンジンモードを更新

        Args:
            new_mode: 新しいエンジンモード ('voicevox' or 'pyttsx3')
        """
        if self.engine_mode != new_mode:
            if new_mode == 'voicevox' and not _init_pygame_audio():
                logger.warning("Cannot switch to VOICEVOX because pygame audio is not available.")
                return
            old_mode = self.engine_mode
            self.engine_mode = new_mode
            logger.info(f"TTS engine switched: {old_mode} → {new_mode}")

            # セッションの作成/破棄
            if new_mode == 'voicevox' and self.aio_session is None and self.aio_loop:
                async def create_session():
                    connector = aiohttp.TCPConnector(limit=5, limit_per_host=2)
                    return aiohttp.ClientSession(connector=connector)
                try:
                    self.aio_session = self.aio_loop.run_until_complete(create_session())
                except Exception as e:
                    logger.error(f"Failed to create aiohttp session: {e}")

    async def _synthesize_voicevox_async(
        self, text: str, speaker_id: Optional[int] = None, retry: bool = True
    ) -> Optional[bytes]:
        """Synthesize speech via the active engine (async), with one retry."""
        effective_speaker = speaker_id if speaker_id is not None else self.speaker_id

        if self.aio_session is None:
            return None

        audio = await self.engine.synthesize_async(
            self.aio_session, text, effective_speaker, timeout=5.0
        )
        if audio is not None:
            return audio

        if retry:
            logger.info(f"Retrying {self.engine_name} synthesis...")
            await asyncio.sleep(0.5)
            return await self._synthesize_voicevox_async(
                text, speaker_id=effective_speaker, retry=False
            )
        return None

    def _synthesize_pyttsx3(self, text: str) -> Optional[bytes]:
        """
        Synthesize speech using pyttsx3 fallback engine

        Args:
            text: Text to synthesize

        Returns:
            WAV audio data as bytes, or None if failed
        """
        if not PYTTSX3_AVAILABLE:
            logger.warning("pyttsx3 not available for fallback")
            return None

        try:
            # Initialize engine each time for thread safety
            engine = pyttsx3.init()

            # Configure voice for Japanese if available
            voices = engine.getProperty('voices')
            japanese_voice_set = False
            for voice in voices:
                # Check for Japanese voice
                voice_name_lower = voice.name.lower()
                if 'japanese' in voice_name_lower or 'japan' in voice_name_lower or 'ja' in voice_name_lower:
                    engine.setProperty('voice', voice.id)
                    japanese_voice_set = True
                    logger.debug(f"Using Japanese voice: {voice.name}")
                    break

            if not japanese_voice_set:
                logger.warning("No Japanese voice found, using default voice")

            # Set speech rate (slower for better clarity)
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)

            # Save to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name

            engine.save_to_file(text, temp_path)
            engine.runAndWait()

            # Give it a moment to finish writing
            import time
            time.sleep(0.1)

            # Read the WAV file
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()

                # Clean up
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

                # Stop the engine
                engine.stop()

                logger.debug(f"pyttsx3 synthesis successful: {len(audio_data)} bytes")
                return audio_data
            else:
                logger.error(f"pyttsx3 failed to create audio file: {temp_path}")
                engine.stop()
                return None

        except Exception as e:
            logger.error(f"Error during pyttsx3 synthesis: {e}", exc_info=True)
            return None

    def _get_pyttsx3_engine(self):
        """Lazy-load pyttsx3 engine to avoid heavy init at import time"""
        if not PYTTSX3_AVAILABLE:
            return None
        if self.pyttsx3_engine is None:
            try:
                self.pyttsx3_engine = pyttsx3.init()
                # Slightly faster speech for readability
                self.pyttsx3_engine.setProperty('rate', 210)
            except Exception as e:
                logger.error(f"Failed to initialize pyttsx3 engine: {e}", exc_info=True)
                self.pyttsx3_engine = None
        return self.pyttsx3_engine

    def _speak_pyttsx3(self, text: str) -> bool:
        """Speak text directly with pyttsx3 (no pygame dependency)"""
        engine = self._get_pyttsx3_engine()
        if not engine:
            return False
        try:
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception as e:
            logger.error(f"pyttsx3 speak error: {e}", exc_info=True)
            return False

    def play_audio(self, audio_data: bytes):
        """
        Play audio data using pygame

        Args:
            audio_data: WAV audio data
        """
        if not AUDIO_AVAILABLE:
            logger.warning("pygame not available, cannot play audio")
            return

        temp_path = None
        try:
            # Create temporary file for audio data
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name

            # Play audio using pygame
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.play()

            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)

        except pygame.error as e:
            logger.error(f"Pygame error during audio playback: {e}", exc_info=True)
        except IOError as e:
            logger.error(f"IO error during audio playback: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error playing audio: {e}", exc_info=True)
        finally:
            # Clean up temporary file
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def _synthesis_worker(self):
        """Background worker thread for synthesizing audio"""
        logger.info("TTS synthesis worker started")

        # Create event loop for this thread
        self.aio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.aio_loop)

        # Create aiohttp session with connection pooling
        async def create_session():
            connector = aiohttp.TCPConnector(limit=5, limit_per_host=2)
            return aiohttp.ClientSession(connector=connector)

        # Always create session for health checks
        self.aio_session = self.aio_loop.run_until_complete(create_session())

        import time
        last_health_check = 0

        while not self.stop_worker:
            try:
                # 定期的なVOICEVOXヘルスチェック（5秒ごと）
                current_time = time.time()
                if current_time - last_health_check > self.voicevox_check_interval:
                    last_health_check = current_time

                    # VOICEVOX可用性チェック
                    voicevox_available = self.aio_loop.run_until_complete(
                        self._check_voicevox_availability_async()
                    )

                    # エンジンの動的切り替え
                    if voicevox_available and self.engine_mode != 'voicevox':
                        # VOICEVOXが復活したら切り替え
                        self._update_engine_mode('voicevox')
                        logger.info("✅ VOICEVOX Engine が利用可能になりました。切り替えます。")
                    elif not voicevox_available and self.engine_mode == 'voicevox':
                        # VOICEVOXが使えなくなったらpyttsx3に切り替え
                        if PYTTSX3_AVAILABLE:
                            self._update_engine_mode('pyttsx3')
                            logger.warning("⚠️ VOICEVOX Engine が応答しません。pyttsx3に切り替えます。")

                # Get (text, speaker_id) from synthesis queue
                item = self.synthesis_queue.get(timeout=1)
                if item is None:
                    self.synthesis_queue.task_done()
                    continue

                # Unpack tuple: (text, override_speaker_id)
                if isinstance(item, tuple):
                    text, override_speaker_id = item
                else:
                    text = item
                    override_speaker_id = None

                cleaned_text = clean_text_for_tts(text)
                if not cleaned_text:
                    self.synthesis_queue.task_done()
                    continue

                # pyttsx3はpygameに依存しないのでそのまま再生（per-user voice非対応）
                if self.engine_mode == 'pyttsx3':
                    self._speak_pyttsx3(cleaned_text)
                    self.synthesis_queue.task_done()
                    continue

                audio_data = None

                # Determine effective speaker ID
                effective_speaker = (
                    override_speaker_id
                    if override_speaker_id is not None
                    else self.speaker_id
                )

                # 現在のエンジンモードに基づいて合成
                if self.engine_mode == 'voicevox' and self.aio_session:
                    audio_data = self.aio_loop.run_until_complete(
                        self._synthesize_voicevox_async(
                            cleaned_text, speaker_id=effective_speaker
                        )
                    )

                    # VOICEVOX失敗時は即座にpyttsx3にフォールバック
                    if not audio_data and PYTTSX3_AVAILABLE:
                        logger.warning("VOICEVOX synthesis failed, using pyttsx3 fallback")
                        self._speak_pyttsx3(cleaned_text)
                        self.synthesis_queue.task_done()
                        continue

                if audio_data:
                    # Add to playback queue
                    self.play_queue.put(audio_data)
                else:
                    logger.warning(f"Failed to synthesize: {cleaned_text}")

                self.synthesis_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in synthesis worker: {e}", exc_info=True)

        # Cleanup
        if self.aio_session:
            self.aio_loop.run_until_complete(self.aio_session.close())
        self.aio_loop.close()

        logger.info("TTS synthesis worker stopped")

    def _playback_worker(self):
        """Background worker thread for playing audio"""
        logger.info("TTS playback worker started")
        while not self.stop_worker:
            try:
                # Get audio from queue with timeout
                audio_data = self.play_queue.get(timeout=1)
                if audio_data is not None:
                    self.play_audio(audio_data)
                self.play_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in playback worker: {e}", exc_info=True)
                # task_done を呼び出してキューがブロックされないようにする
                try:
                    self.play_queue.task_done()
                except ValueError:
                    pass  # task_done が既に呼ばれた場合
        logger.info("TTS playback worker stopped")

    def _ensure_workers_running(self):
        """ワーカースレッドが動作しているか確認し、停止していたら再起動"""
        if self.synthesis_thread is None or not self.synthesis_thread.is_alive():
            logger.warning("Synthesis worker was dead, restarting...")
            self.synthesis_thread = threading.Thread(target=self._synthesis_worker, daemon=True)
            self.synthesis_thread.start()

        if self.engine_mode == 'voicevox':
            if self.playback_thread is None or not self.playback_thread.is_alive():
                logger.warning("Playback worker was dead, restarting...")
                self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
                self.playback_thread.start()

    def start(self):
        """Start TTS service"""
        logger.info("=== TTS起動プロセス開始 ===")

        # VOICEVOXの可用性を再チェック（起動時に利用不可でも、今は利用可能かもしれない）
        self.voicevox_available = self._check_voicevox_availability()
        logger.info(f"VOICEVOX可用性（再チェック）: {self.voicevox_available}")
        logger.info(f"pygame imported: {PYGAME_IMPORTED}")
        logger.info(f"pyttsx3 available: {PYTTSX3_AVAILABLE}")

        engine_mode = None

        # Prefer VOICEVOX if available and pygame audio can be initialized safely
        if self.voicevox_available:
            logger.info("VOICEVOXが利用可能です。pygameオーディオを初期化しています...")
            pygame_ready = _init_pygame_audio()
            logger.info(f"pygameオーディオ初期化結果: {pygame_ready}")

            if pygame_ready:
                engine_mode = 'voicevox'
                logger.info("✅ TTSエンジンをVOICEVOXで起動します")
            else:
                logger.warning("⚠️ pygameオーディオの初期化に失敗しました。pyttsx3にフォールバックします。")
        else:
            logger.warning(f"⚠️ VOICEVOX APIに接続できません（URL: {self.api_url}）")

        # Fallback to pyttsx3 if VOICEVOX/pygame is not available
        if engine_mode is None and PYTTSX3_AVAILABLE:
            engine_mode = 'pyttsx3'
            logger.info("✅ TTSエンジンをpyttsx3で起動します（フォールバック）")

        if engine_mode is None:
            logger.error("❌ TTSエンジンを起動できません: VOICEVOXが利用不可、pyttsx3も見つかりません")
            return False

        self.engine_mode = engine_mode
        self.enabled = True
        self.stop_worker = False

        # Start synthesis worker thread
        if self.synthesis_thread is None or not self.synthesis_thread.is_alive():
            self.synthesis_thread = threading.Thread(target=self._synthesis_worker, daemon=True)
            self.synthesis_thread.start()
            logger.info("合成ワーカースレッドを起動しました")

        # Start playback worker thread (only needed for VOICEVOX/pygame playback)
        if self.engine_mode == 'voicevox' and (self.playback_thread is None or not self.playback_thread.is_alive()):
            self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
            self.playback_thread.start()
            logger.info("再生ワーカースレッドを起動しました")

        logger.info(f"✅ TTSサービスが{self.engine_mode}エンジンで起動しました")
        logger.info("=== TTS起動プロセス完了 ===")
        return True

    def stop(self):
        """Stop TTS service"""
        self.enabled = False
        self.stop_worker = True

        # Wait for threads to finish
        if self.synthesis_thread and self.synthesis_thread.is_alive():
            self.synthesis_thread.join(timeout=2)
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2)

        logger.info("TTS service stopped")

    def speak(self, text: str, force: bool = False, speaker_id: Optional[int] = None):
        """
        Speak text (add to synthesis queue)

        Args:
            text: Text to speak
            force: Force speak even if TTS is disabled
            speaker_id: Override speaker ID for this utterance (None = use default)
        """
        if not self.enabled and not force:
            logger.warning(f"⚠️ TTSが無効です。読み上げをスキップします: {text[:50]}...")
            return

        # ワーカースレッドが動作しているか確認し、停止していたら再起動
        self._ensure_workers_running()

        # Clean text
        cleaned_text = clean_text_for_tts(text)
        if not cleaned_text:
            logger.debug(f"クリーニング後のテキストが空です: {text[:50]}...")
            return

        logger.debug(f"🔊 TTSキューに追加: {cleaned_text}")
        logger.debug(f"エンジンモード: {self.engine_mode}, キューサイズ: {self.synthesis_queue.qsize()}")

        # 読み上げテキストをタイムスタンプ付きでログファイルに追記
        _append_tts_log(cleaned_text)

        # Add to synthesis queue as (text, speaker_id) tuple
        self.synthesis_queue.put((cleaned_text, speaker_id))


# Global TTS instance
_tts_instance = None


def get_tts_instance() -> VoicevoxTTS:
    """Get or create the global TTS instance, honoring ``config.json`` overrides."""
    global _tts_instance
    if _tts_instance is None:
        engine_name = "voicevox"
        api_url = VOICEVOX_API_URL
        speaker_id = MEIMEI_HIMARI_SPEAKER_ID
        try:
            from src.config import load_config
            cfg = load_config()
            engine_name = cfg.get("tts_engine", "voicevox") or "voicevox"
            engine_urls = cfg.get("tts_engine_urls") or {}
            api_url = (
                engine_urls.get(engine_name)
                or cfg.get("voicevox_url")
                or get_preset_url(engine_name)
            )
            speaker_id = int(cfg.get("voicevox_speaker_id", MEIMEI_HIMARI_SPEAKER_ID))
        except Exception as e:
            logger.debug(f"Falling back to default TTS config ({e})")
        _tts_instance = VoicevoxTTS(
            api_url=api_url,
            speaker_id=speaker_id,
            engine_name=engine_name,
        )
    return _tts_instance
