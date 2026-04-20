"""VOICEVOX-compatible HTTP engine.

Implements the common VOICEVOX API (``/version``, ``/speakers``,
``/audio_query``, ``/synthesis``) that is also spoken by COEIROINK,
AivisSpeech, and SHAREVOX. Each preset differs only in default port.
"""

from __future__ import annotations

from typing import Optional

import aiohttp

from src.logger import logger
from src.tts_engines.base import TTSEngine


class VoicevoxEngine(TTSEngine):
    """VOICEVOX / COEIROINK / AivisSpeech / SHAREVOX shared implementation."""

    name = "voicevox"
    default_url = "http://localhost:50021"

    # Engine name -> default HTTP URL.
    PRESETS: dict[str, str] = {
        "voicevox": "http://localhost:50021",
        "coeiroink": "http://localhost:50032",
        "aivisspeech": "http://localhost:10101",
        "sharevox": "http://localhost:50025",
    }

    def __init__(
        self,
        api_url: Optional[str] = None,
        name: str = "voicevox",
    ) -> None:
        super().__init__(api_url or self.PRESETS.get(name, self.default_url))
        self.name = name

    async def health_check(
        self,
        session: aiohttp.ClientSession,
        timeout: float = 2.0,
    ) -> bool:
        try:
            async with session.get(
                f"{self.api_url}/version",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.debug(f"{self.name} health check failed: {e}")
            return False

    def list_voices_sync(self, timeout: float = 5.0) -> list[dict]:
        try:
            import requests
            response = requests.get(f"{self.api_url}/speakers", timeout=timeout)
            if response.status_code != 200:
                logger.warning(
                    f"{self.name} /speakers returned {response.status_code}"
                )
                return []
            speakers = response.json()
            result: list[dict] = []
            for speaker in speakers:
                name = speaker.get("name", "Unknown")
                for style in speaker.get("styles", []):
                    style_name = style.get("name", "Default")
                    style_id = style.get("id", 0)
                    result.append(
                        {
                            "name": name,
                            "style": style_name,
                            "id": style_id,
                            "display": f"{name} / {style_name}",
                        }
                    )
            return result
        except Exception as e:
            logger.error(f"{self.name} voice list fetch failed: {e}")
            return []

    async def synthesize_async(
        self,
        session: aiohttp.ClientSession,
        text: str,
        voice_id,
        timeout: float = 5.0,
    ) -> Optional[bytes]:
        try:
            speaker = int(voice_id)
        except (TypeError, ValueError):
            logger.error(
                f"{self.name} requires integer voice_id, got {voice_id!r}"
            )
            return None

        try:
            async with session.post(
                f"{self.api_url}/audio_query",
                params={"text": text, "speaker": speaker},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"{self.name} audio_query failed: {response.status}"
                    )
                    return None
                audio_query = await response.json()

            async with session.post(
                f"{self.api_url}/synthesis",
                params={"speaker": speaker},
                headers={"Content-Type": "application/json"},
                json=audio_query,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"{self.name} synthesis failed: {response.status}"
                    )
                    return None
                return await response.read()
        except Exception as e:
            logger.error(f"{self.name} synthesize error: {e}")
            return None
