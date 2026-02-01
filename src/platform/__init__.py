"""
プラットフォーム抽象化レイヤー

複数の配信プラットフォーム（Twitch, YouTube等）を統一的に扱うためのモジュール。
"""

from src.platform.base import PlatformAdapter, PlatformType, SpecialEvent, EventType
from src.platform.twitch import TwitchAdapter, TwitchBot, EventSubHandler
from src.platform.youtube import YouTubeAdapter, create_youtube_comment

__all__ = [
    "PlatformAdapter",
    "PlatformType",
    "SpecialEvent",
    "EventType",
    "TwitchAdapter",
    "TwitchBot",
    "EventSubHandler",
    "YouTubeAdapter",
    "create_youtube_comment",
]
