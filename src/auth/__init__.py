"""
認証プロバイダーモジュール

各プラットフォーム（Twitch, YouTube等）のOAuth認証を統一的に扱う。
"""

from src.auth.base import AuthProvider, AuthResult
from src.auth.twitch import TwitchAuthProvider
from src.auth.youtube import YouTubeAuthProvider

# 後方互換性のため旧関数をエクスポート
from src.auth.twitch import (
    build_auth_url,
    run_auth_server_and_get_token,
    validate_token,
    validate_token_with_info,
)

__all__ = [
    "AuthProvider",
    "AuthResult",
    "TwitchAuthProvider",
    "YouTubeAuthProvider",
    # 後方互換性
    "build_auth_url",
    "run_auth_server_and_get_token",
    "validate_token",
    "validate_token_with_info",
]
