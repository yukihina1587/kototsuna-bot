"""
既知 BOT アカウントの自動フィルタリング (Issue #145)
"""
from __future__ import annotations

from typing import List


class BotFilter:
    """Twitch チャット BOT 自動フィルタリング。

    アプリ内蔵のデフォルト BOT リストと、ユーザーが追加したカスタムリストの
    両方を参照し、送信者が BOT かどうかを判定する。
    """

    # アプリ内蔵デフォルト BOT リスト（lowercase で管理）
    DEFAULT_BOTS: frozenset[str] = frozenset([
        "nightbot",
        "streamlabs",
        "streamlabs_chatbot",
        "streamelements",
        "moobot",
        "fossabot",
        "sery_bot",
        "wizebot",
        "botisimo",
        "galaxibot",
        "pretzelrocks",
        "soundalerts",
        "kofistreambot",
        "creatisbot",
        "vantabot",
        "commanderroot",
        "electricallongboard",
        "logviewer",
        "buttsbot",
        "own3d_tv",
        "phantombot",
        "stay_hydrated_bot",
        "vivbot",
        "ankhbot",
        "markov_chain_ftw",
        "comettv",
        "deepbot",
        "coebot",
    ])

    def __init__(self, enabled: bool = True, custom_bots: List[str] | None = None) -> None:
        self.enabled = enabled
        self.custom_bots: set[str] = {b.lower() for b in (custom_bots or [])}

    def is_bot(self, username: str) -> bool:
        """ユーザー名が既知 BOT かどうか判定する（大文字小文字区別なし）。"""
        if not self.enabled:
            return False
        lower = username.lower()
        return lower in self.DEFAULT_BOTS or lower in self.custom_bots

    def add_custom(self, username: str) -> None:
        """カスタム BOT リストにユーザー名を追加する。"""
        self.custom_bots.add(username.strip().lower())

    def remove_custom(self, username: str) -> None:
        """カスタム BOT リストからユーザー名を削除する。"""
        self.custom_bots.discard(username.strip().lower())

    def list_custom(self) -> list[str]:
        """カスタム BOT リストをソート済みで返す。"""
        return sorted(self.custom_bots)

    def to_config(self) -> dict:
        """config.json に保存する形式でデータを返す。"""
        return {
            "bot_filter_enabled": self.enabled,
            "bot_filter_custom": sorted(self.custom_bots),
        }


_instance: BotFilter | None = None


def get_bot_filter() -> BotFilter:
    """グローバルシングルトンを返す。"""
    global _instance
    if _instance is None:
        from src.config import load_config
        cfg = load_config()
        _instance = BotFilter(
            enabled=cfg.get("bot_filter_enabled", True),
            custom_bots=cfg.get("bot_filter_custom", []),
        )
    return _instance


def reset_bot_filter() -> None:
    """設定変更後にシングルトンをリセットする。"""
    global _instance
    _instance = None
