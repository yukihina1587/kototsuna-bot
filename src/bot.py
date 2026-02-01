"""
後方互換性のためのモジュール

新しい実装は src/platform/twitch.py を参照してください。
"""

# 後方互換性のため、旧インポートパスを維持
from src.platform.twitch import (
    TwitchAdapter,
    TwitchBot as TranslateBot,
    EventSubHandler,
)

__all__ = [
    "TranslateBot",
    "TwitchAdapter",
    "EventSubHandler",
]
