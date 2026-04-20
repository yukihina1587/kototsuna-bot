"""Edge TTS engine.

Microsoft Edge の読み上げサービス（無料・APIキー不要・ローカルサーバー不要）を
Python ライブラリ ``edge-tts`` 経由で呼び出す。ネット接続のみ必須。

Voice ID は ``ja-JP-NanamiNeural`` のような文字列。出力は MP3。
"""

from __future__ import annotations

from typing import Optional, Union

import aiohttp

from src.logger import logger
from src.tts_engines.base import TTSEngine


class EdgeTtsEngine(TTSEngine):
    """Edge TTS (online, library-based). No server startup required."""

    name = "edge-tts"
    default_url = ""
    audio_format = "mp3"

    DEFAULT_VOICE = "ja-JP-NanamiNeural"

    # GUI ドロップダウンで見せる日本語音声（代表的な声のみ厳選）。
    # 完全な一覧は ``edge_tts.list_voices()`` で取得できるが、
    # 初期ロード時のネットワーク呼び出しを避けるため固定リストにする。
    JP_VOICES: list[tuple[str, str, str]] = [
        ("ja-JP-NanamiNeural", "Nanami", "女性"),
        ("ja-JP-KeitaNeural", "Keita", "男性"),
        ("ja-JP-AoiNeural", "Aoi", "女性"),
        ("ja-JP-DaichiNeural", "Daichi", "男性"),
        ("ja-JP-MayuNeural", "Mayu", "女性"),
        ("ja-JP-NaokiNeural", "Naoki", "男性"),
        ("ja-JP-ShioriNeural", "Shiori", "女性"),
    ]

    def __init__(
        self,
        api_url: Optional[str] = None,
        name: str = "edge-tts",
    ) -> None:
        super().__init__("")
        self.name = name

    async def health_check(
        self,
        session: aiohttp.ClientSession,
        timeout: float = 2.0,
    ) -> bool:
        """ライブラリが import できれば利用可能扱い。合成時にネット不達ならフォールバックする。"""
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception as e:
            logger.debug(f"edge-tts import failed: {e}")
            return False

    def list_voices_sync(self, timeout: float = 5.0) -> list[dict]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            logger.warning("edge-tts ライブラリが未インストールです")
            return []

        return [
            {
                "name": short_name,
                "style": gender,
                "id": voice_id,
                "display": f"Edge / {short_name} ({gender})",
            }
            for voice_id, short_name, gender in self.JP_VOICES
        ]

    async def synthesize_async(
        self,
        session: aiohttp.ClientSession,
        text: str,
        voice_id: Union[str, int, None],
        timeout: float = 5.0,
    ) -> Optional[bytes]:
        try:
            import edge_tts
        except ImportError:
            logger.error("edge-tts ライブラリが未インストールです")
            return None

        voice = (
            voice_id
            if isinstance(voice_id, str) and voice_id.strip()
            else self.DEFAULT_VOICE
        )

        try:
            communicate = edge_tts.Communicate(text, voice)
            buffer = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    data = chunk.get("data")
                    if data:
                        buffer.extend(data)
            if not buffer:
                logger.warning("edge-tts returned empty audio")
                return None
            return bytes(buffer)
        except Exception as e:
            logger.error(f"edge-tts synthesize error: {e}")
            return None
