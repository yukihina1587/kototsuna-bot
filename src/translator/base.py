"""
翻訳エンジンの抽象基底クラス

全ての翻訳エンジンはこのインターフェースを実装する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TranslateMode(Enum):
    """翻訳モード"""
    AUTO = "自動"
    EN_TO_JA = "英→日"
    JA_TO_EN = "日→英"

    @classmethod
    def from_string(cls, value: str) -> "TranslateMode":
        """文字列からTranslateModeを取得"""
        for mode in cls:
            if mode.value == value:
                return mode
        return cls.AUTO


@dataclass
class TranslateResult:
    """翻訳結果"""
    success: bool
    translated_text: str
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    error: Optional[str] = None


class TranslatorInterface(ABC):
    """翻訳エンジンの抽象インターフェース"""

    @abstractmethod
    async def translate(
        self,
        text: str,
        mode: TranslateMode,
    ) -> TranslateResult:
        """
        テキストを非同期で翻訳する

        Args:
            text: 翻訳するテキスト
            mode: 翻訳モード

        Returns:
            TranslateResult: 翻訳結果
        """
        pass

    @abstractmethod
    def translate_sync(
        self,
        text: str,
        mode: TranslateMode,
    ) -> TranslateResult:
        """
        テキストを同期的に翻訳する

        Args:
            text: 翻訳するテキスト
            mode: 翻訳モード

        Returns:
            TranslateResult: 翻訳結果
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """エンジン名を取得"""
        pass

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """
        設定を検証する

        Returns:
            tuple[bool, str]: (有効かどうか, メッセージ)
        """
        pass

    @abstractmethod
    def get_usage(self) -> Optional[dict]:
        """
        API使用状況を取得（対応している場合）

        Returns:
            dict or None: 使用状況情報
        """
        pass
