"""
Twitch チャット BOT 自動フィルタリングモジュール

既知の BOT アカウントを TTS 読み上げ・翻訳対象から自動除外する。
誤 BAN 対策として、チャンネルオーナーと認証ユーザー（配信者 BOT）は
protected_names に指定することで絶対にフィルタリングされない。
"""
from __future__ import annotations

from typing import Collection


class BotFilter:
    """Twitch チャット BOT 自動フィルタリング"""

    # アプリ内蔵デフォルト BOT リスト（小文字で管理）
    DEFAULT_BOTS: frozenset[str] = frozenset([
        "nightbot", "streamlabs", "streamlabs_chatbot", "streamelements",
        "moobot", "fossabot", "sery_bot", "wizebot", "botisimo",
        "galaxibot", "pretzelrocks", "soundalerts", "kofistreambot",
        "creatisbot", "vantabot", "commanderroot", "electricallongboard",
        "logviewer", "buttsbot", "own3d_tv", "phantombot",
        "stay_hydrated_bot", "vivbot", "ankhbot", "markov_chain_ftw",
        "comettv", "deepbot", "coebot",
    ])

    def __init__(
        self,
        enabled: bool = True,
        custom_bots: Collection[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.custom_bots: set[str] = {b.lower() for b in (custom_bots or [])}

    def is_bot(self, username: str, protected_names: Collection[str] | None = None) -> bool:
        """ユーザー名が BOT かどうか判定する。

        Args:
            username: 判定するユーザー名
            protected_names: 絶対にフィルタリングしないユーザー名のコレクション
                             （チャンネルオーナー・認証ユーザーを渡すことで誤 BAN を防止）

        Returns:
            True: BOT として判定（フィルタリング対象）
            False: 通常ユーザー（またはフィルタリング無効 / protected）
        """
        if not self.enabled:
            return False

        lower = username.lower()

        # 誤 BAN 対策: protected_names に含まれるユーザーは絶対にフィルタリングしない
        if protected_names:
            if any(lower == p.lower() for p in protected_names if p):
                return False

        return lower in self.DEFAULT_BOTS or lower in self.custom_bots

    def add_custom(self, username: str) -> None:
        """カスタム BOT リストにユーザー名を追加する"""
        self.custom_bots.add(username.lower())

    def remove_custom(self, username: str) -> None:
        """カスタム BOT リストからユーザー名を削除する"""
        self.custom_bots.discard(username.lower())

    def get_custom_bots(self) -> list[str]:
        """カスタム BOT リストをソートして返す"""
        return sorted(self.custom_bots)

    def to_config(self) -> dict:
        """設定を dict 形式で返す（config.json 保存用）"""
        return {
            "bot_filter_enabled": self.enabled,
            "bot_filter_custom": sorted(self.custom_bots),
        }


# モジュールレベルのシングルトン
_instance: BotFilter | None = None


def get_bot_filter(enabled: bool = True, custom_bots: Collection[str] | None = None) -> BotFilter:
    """グローバル BotFilter インスタンスを返す。初回呼び出し時に生成する。"""
    global _instance
    if _instance is None:
        _instance = BotFilter(enabled=enabled, custom_bots=custom_bots)
    return _instance


def reset_bot_filter() -> None:
    """テスト用: シングルトンをリセットする"""
    global _instance
    _instance = None
