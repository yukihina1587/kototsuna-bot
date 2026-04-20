"""Public API for TTS engines.

Phase 1: VOICEVOX and its API-compatible siblings (COEIROINK, AivisSpeech,
SHAREVOX) share a single implementation, differing only in default URL.
Phase 2: Edge TTS（edge-tts ライブラリ／オンライン・APIキー不要・サーバー起動不要）を追加。
"""

from __future__ import annotations

from typing import Optional

from src.tts_engines.base import TTSEngine
from src.tts_engines.edge import EdgeTtsEngine
from src.tts_engines.voicevox import VoicevoxEngine


# Engine name -> factory.
_FACTORIES = {
    "voicevox": lambda url=None: VoicevoxEngine(url, name="voicevox"),
    "coeiroink": lambda url=None: VoicevoxEngine(url, name="coeiroink"),
    "aivisspeech": lambda url=None: VoicevoxEngine(url, name="aivisspeech"),
    "sharevox": lambda url=None: VoicevoxEngine(url, name="sharevox"),
    "edge-tts": lambda url=None: EdgeTtsEngine(url, name="edge-tts"),
}


def get_engine(name: str, api_url: Optional[str] = None) -> TTSEngine:
    """Instantiate an engine by name. Unknown names fall back to VOICEVOX."""
    factory = _FACTORIES.get(name, _FACTORIES["voicevox"])
    return factory(api_url)


def list_available_engines() -> list[dict]:
    """Return GUI-ready metadata for the engine selector dropdown."""
    return [
        {
            "name": "voicevox",
            "display": "VOICEVOX",
            "default_url": VoicevoxEngine.PRESETS["voicevox"],
        },
        {
            "name": "coeiroink",
            "display": "COEIROINK",
            "default_url": VoicevoxEngine.PRESETS["coeiroink"],
        },
        {
            "name": "aivisspeech",
            "display": "AivisSpeech",
            "default_url": VoicevoxEngine.PRESETS["aivisspeech"],
        },
        {
            "name": "sharevox",
            "display": "SHAREVOX",
            "default_url": VoicevoxEngine.PRESETS["sharevox"],
        },
        {
            "name": "edge-tts",
            "display": "Edge TTS (オンライン)",
            "default_url": "",
        },
    ]


def get_preset_url(engine_name: str) -> str:
    """Return the default URL for a VOICEVOX-compatible engine preset.

    Edge TTS のようにローカル URL を持たないエンジンは空文字列を返す。
    """
    if engine_name == "edge-tts":
        return ""
    return VoicevoxEngine.PRESETS.get(engine_name, VoicevoxEngine.default_url)


__all__ = [
    "TTSEngine",
    "VoicevoxEngine",
    "EdgeTtsEngine",
    "get_engine",
    "list_available_engines",
    "get_preset_url",
]
