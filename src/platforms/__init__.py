"""
プラットフォーム抽象化レイヤー

複数の配信プラットフォーム（Twitch, YouTube等）を統一的に扱うためのモジュール。
"""

from src.platforms.base import PlatformAdapter, PlatformType, SpecialEvent, EventType
from src.platforms.twitch import TwitchAdapter, TwitchBot, EventSubHandler
from src.platforms.youtube import YouTubeAdapter, create_youtube_comment
from src.platforms.manager import MultiPlatformManager

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
    "MultiPlatformManager",
]
