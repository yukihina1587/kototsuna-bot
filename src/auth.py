"""
後方互換性のためのモジュール

新しい実装は src/auth/ パッケージを参照してください。
"""

# 後方互換性のため、旧インポートパスを維持
from src.auth.twitch import (
    TwitchAuthProvider,
    build_auth_url,
    run_auth_server_and_get_token,
    validate_token,
    validate_token_with_info,
    REDIRECT_URI,
    SCOPES,
    REDIRECT_HTML,
)

__all__ = [
    "TwitchAuthProvider",
    "build_auth_url",
    "run_auth_server_and_get_token",
    "validate_token",
    "validate_token_with_info",
    "REDIRECT_URI",
    "SCOPES",
    "REDIRECT_HTML",
]
