"""
認証プロバイダーの抽象基底クラス
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum, auto


class AuthStatus(Enum):
    """認証ステータス"""
    NOT_AUTHENTICATED = auto()
    AUTHENTICATED = auto()
    EXPIRED = auto()
    INVALID = auto()


@dataclass
class AuthResult:
    """認証結果のデータモデル"""
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    user_name: Optional[str] = None
    user_id: Optional[str] = None
    scopes: Optional[List[str]] = None
    error_message: Optional[str] = None


class AuthProvider(ABC):
    """
    認証プロバイダーの抽象基底クラス

    各プラットフォームはこのクラスを継承し、OAuth認証を実装する。
    """

    def __init__(self, client_id: str, client_secret: Optional[str] = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._status = AuthStatus.NOT_AUTHENTICATED

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def refresh_token(self) -> Optional[str]:
        return self._refresh_token

    @property
    def status(self) -> AuthStatus:
        return self._status

    @property
    def is_authenticated(self) -> bool:
        return self._status == AuthStatus.AUTHENTICATED

    @abstractmethod
    def build_auth_url(self) -> str:
        """
        OAuth認証URLを生成する

        Returns:
            認証ページのURL
        """
        pass

    @abstractmethod
    def start_auth_server(self) -> AuthResult:
        """
        ローカル認証サーバーを起動してトークンを取得する

        Returns:
            認証結果
        """
        pass

    @abstractmethod
    def validate_token(self, token: Optional[str] = None) -> AuthResult:
        """
        トークンの有効性を検証する

        Args:
            token: 検証するトークン（Noneの場合は保存済みトークンを使用）

        Returns:
            検証結果
        """
        pass

    @abstractmethod
    async def refresh_access_token(self) -> AuthResult:
        """
        アクセストークンを更新する（リフレッシュトークンを使用）

        Returns:
            更新結果
        """
        pass

    def set_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        """
        トークンを設定する

        Args:
            access_token: アクセストークン
            refresh_token: リフレッシュトークン（オプション）
        """
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._status = AuthStatus.AUTHENTICATED

    def clear_tokens(self) -> None:
        """トークンをクリアする"""
        self._access_token = None
        self._refresh_token = None
        self._status = AuthStatus.NOT_AUTHENTICATED
