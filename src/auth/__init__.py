"""
認証プロバイダーモジュール

各プラットフォーム（Twitch, YouTube等）のOAuth認証を統一的に扱う。
"""

from src.auth.base import AuthProvider, AuthResult
from src.auth.twitch import TwitchAuthProvider
from src.auth.youtube import YouTubeAuthProvider

__all__ = [
    "AuthProvider",
    "AuthResult",
    "TwitchAuthProvider",
    "YouTubeAuthProvider",
]
