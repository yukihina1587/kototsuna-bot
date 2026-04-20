"""TTS engine abstraction.

Each concrete engine implements health_check / list_voices_sync / synthesize_async.
Engines are backend-agnostic; the caller (``src.tts.VoicevoxTTS``) handles
audio playback, queueing, and fallback to pyttsx3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import aiohttp


class TTSEngine(ABC):
    """Common interface for all TTS engines supported by ことつな!."""

    name: str = "base"
    default_url: str = ""

    def __init__(self, api_url: Optional[str] = None) -> None:
        url = api_url if api_url else self.default_url
        self.api_url = url.rstrip("/") if url else ""

    @abstractmethod
    async def health_check(
        self,
        session: aiohttp.ClientSession,
        timeout: float = 2.0,
    ) -> bool:
        """Return True if the engine endpoint responds."""

    @abstractmethod
    def list_voices_sync(self, timeout: float = 5.0) -> list[dict]:
        """Return available voices (synchronous; used from GUI thread).

        Each entry: ``{"name": str, "style": str, "id": int|str, "display": str}``
        """

    @abstractmethod
    async def synthesize_async(
        self,
        session: aiohttp.ClientSession,
        text: str,
        voice_id,
        timeout: float = 5.0,
    ) -> Optional[bytes]:
        """Generate WAV bytes for ``text`` using ``voice_id``.

        Returns None on any failure — the caller decides whether to retry or
        fall back to another engine.
        """
