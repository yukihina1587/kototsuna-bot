"""
プラットフォームアダプターの抽象基底クラス

各プラットフォーム（Twitch, YouTube等）はこのインターフェースを実装する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Any
from src.comment_data import CommentData


class PlatformType(Enum):
    """対応プラットフォーム"""
    TWITCH = auto()
    YOUTUBE = auto()
    KICK = auto()


class EventType(Enum):
    """特別イベントの種類"""
    FOLLOW = "follow"
    SUBSCRIPTION = "subscription"
    GIFT_SUB = "gift_sub"
    BITS = "bits"  # Twitch Bits
    SUPER_CHAT = "super_chat"  # YouTube Super Chat
    MEMBER = "member"  # YouTube Member
    RAID = "raid"
    OTHER = "other"


@dataclass
class SpecialEvent:
    """特別イベント（フォロー、サブスク、投げ銭等）のデータモデル"""
    event_type: EventType
    message: str
    user_name: str = ""
    amount: Optional[int] = None  # Bits / Super Chat金額
    currency: Optional[str] = None  # 通貨（Super Chat用）
    tier: Optional[str] = None  # サブスクティア
    months: Optional[int] = None  # サブスク継続月数
    raw_data: dict = field(default_factory=dict)  # プラットフォーム固有のデータ


class PlatformAdapter(ABC):
    """
    プラットフォームアダプターの抽象基底クラス

    各プラットフォームはこのクラスを継承し、以下のメソッドを実装する：
    - connect: プラットフォームに接続
    - disconnect: 接続を切断
    - send_message: チャットにメッセージを送信

    コールバックの設定：
    - set_message_callback: メッセージ受信時のコールバック
    - set_event_callback: 特別イベント受信時のコールバック
    """

    def __init__(self):
        self._message_callback: Optional[Callable[[CommentData], None]] = None
        self._event_callback: Optional[Callable[[SpecialEvent], None]] = None
        self._connected = False
        self._channel: Optional[str] = None

    @property
    @abstractmethod
    def platform_type(self) -> PlatformType:
        """プラットフォームの種類を返す"""
        pass

    @property
    def is_connected(self) -> bool:
        """接続中かどうか"""
        return self._connected

    @property
    def channel(self) -> Optional[str]:
        """接続中のチャンネル名"""
        return self._channel

    @abstractmethod
    async def connect(self, channel: str, **kwargs) -> bool:
        """
        プラットフォームに接続する

        Args:
            channel: チャンネル名/ID
            **kwargs: プラットフォーム固有のオプション

        Returns:
            成功した場合True
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """接続を切断する"""
        pass

    @abstractmethod
    async def send_message(self, message: str) -> bool:
        """
        チャットにメッセージを送信する

        Args:
            message: 送信するメッセージ

        Returns:
            成功した場合True
        """
        pass

    def set_message_callback(self, callback: Callable[[CommentData], None]) -> None:
        """
        メッセージ受信時のコールバックを設定

        Args:
            callback: CommentDataを受け取るコールバック関数
        """
        self._message_callback = callback

    def set_event_callback(self, callback: Callable[[SpecialEvent], None]) -> None:
        """
        特別イベント受信時のコールバックを設定

        Args:
            callback: SpecialEventを受け取るコールバック関数
        """
        self._event_callback = callback

    def _notify_message(self, comment: CommentData) -> None:
        """メッセージコールバックを呼び出す"""
        if self._message_callback:
            self._message_callback(comment)

    def _notify_event(self, event: SpecialEvent) -> None:
        """イベントコールバックを呼び出す"""
        if self._event_callback:
            self._event_callback(event)
