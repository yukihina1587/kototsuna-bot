"""Twitchボットコマンドシステムのコアモジュール。

権限管理、クールダウン制御、テンプレート変数置換を提供する。
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import IntEnum

from src.logger import logger


# ---------------------------------------------------------------------------
# 権限レベル
# ---------------------------------------------------------------------------


class PermissionLevel(IntEnum):
    """コマンド実行に必要な権限レベル。

    数値が大きいほど高い権限を表す。
    上位権限は下位権限をすべて包含する。
    """

    EVERYONE = 0
    SUBSCRIBER = 1
    VIP = 2
    MODERATOR = 3
    BROADCASTER = 4


# ---------------------------------------------------------------------------
# クールダウン管理
# ---------------------------------------------------------------------------


class CooldownManager:
    """コマンドのグローバル・ユーザー別クールダウンを管理するクラス。

    time.monotonic() を使用して経過時間を追跡する。
    システムクロックの巻き戻しに影響されない。
    """

    def __init__(self) -> None:
        """クールダウンマネージャーを初期化する。"""
        self._global_cooldowns: dict[str, float] = {}
        self._user_cooldowns: dict[str, dict[str, float]] = {}

    def check(
        self,
        cmd: str,
        user: str,
        global_cd: float,
        user_cd: float,
    ) -> tuple[bool, float]:
        """コマンド実行が許可されるか判定する。

        グローバルクールダウンとユーザー別クールダウンの両方を確認し、
        いずれか長い方の残り時間を返す。

        Args:
            cmd: コマンド名
            user: ユーザー名
            global_cd: グローバルクールダウン（秒）
            user_cd: ユーザー別クールダウン（秒）

        Returns:
            (allowed, remaining_seconds) のタプル。
            allowed が True なら実行可能、False なら remaining_seconds 秒待つ必要がある。
        """
        now = time.monotonic()
        remaining = 0.0

        # グローバルクールダウン判定
        last_global = self._global_cooldowns.get(cmd)
        if last_global is not None:
            elapsed = now - last_global
            if elapsed < global_cd:
                remaining = max(remaining, global_cd - elapsed)

        # ユーザー別クールダウン判定
        user_times = self._user_cooldowns.get(cmd)
        if user_times is not None:
            last_user = user_times.get(user)
            if last_user is not None:
                elapsed = now - last_user
                if elapsed < user_cd:
                    remaining = max(remaining, user_cd - elapsed)

        if remaining > 0:
            logger.debug(
                "クールダウン中: cmd=%s, user=%s, 残り%.1f秒",
                cmd,
                user,
                remaining,
            )
            return False, round(remaining, 1)

        return True, 0.0

    def record(self, cmd: str, user: str) -> None:
        """コマンド使用を記録する。

        Args:
            cmd: コマンド名
            user: ユーザー名
        """
        now = time.monotonic()
        self._global_cooldowns[cmd] = now

        if cmd not in self._user_cooldowns:
            self._user_cooldowns[cmd] = {}
        self._user_cooldowns[cmd][user] = now

        logger.debug("クールダウン記録: cmd=%s, user=%s", cmd, user)


# ---------------------------------------------------------------------------
# 権限チェック
# ---------------------------------------------------------------------------


def check_permission(
    author: object,
    required: PermissionLevel,
    channel_name: str,
) -> bool:
    """ユーザーが指定された権限レベルを満たすか判定する。

    上位権限は下位権限をすべて包含する。
    例: BROADCASTER は MODERATOR / VIP / SUBSCRIBER / EVERYONE の権限も持つ。

    Args:
        author: twitchio の message.author オブジェクト。
                .is_mod, .is_subscriber, .name, .badges 属性を参照する。
        required: 必要な権限レベル
        channel_name: チャンネル名（配信者判定に使用）

    Returns:
        権限を満たしていれば True
    """
    # ユーザーの実効権限レベルを算出（高い方が優先）
    user_level = PermissionLevel.EVERYONE

    # サブスクライバー判定
    if getattr(author, "is_subscriber", False):
        user_level = max(user_level, PermissionLevel.SUBSCRIBER)

    # VIP判定（badges辞書に "vip" キーが存在するか）
    badges: dict[str, str] = getattr(author, "badges", {}) or {}
    if "vip" in badges:
        user_level = max(user_level, PermissionLevel.VIP)

    # モデレーター判定
    if getattr(author, "is_mod", False):
        user_level = max(user_level, PermissionLevel.MODERATOR)

    # 配信者判定
    author_name: str = getattr(author, "name", "")
    if author_name.lower() == channel_name.lower():
        user_level = PermissionLevel.BROADCASTER

    allowed = user_level >= required

    if not allowed:
        logger.debug(
            "権限不足: user=%s (level=%s), required=%s",
            author_name,
            user_level.name,
            required.name,
        )

    return allowed


# ---------------------------------------------------------------------------
# テンプレート変数置換
# ---------------------------------------------------------------------------


def substitute_variables(
    template: str,
    author: object,
    channel: str,
) -> str:
    """テンプレート文字列内の変数プレースホルダーを置換する。

    対応する変数:
        {user}    - ユーザーの表示名（display_name）、なければ author.name
        {channel} - チャンネル名
        {time}    - 現在時刻（HH:MM 形式）
        {date}    - 現在日付（YYYY/MM/DD 形式）

    Args:
        template: プレースホルダーを含むテンプレート文字列
        author: twitchio の message.author オブジェクト
        channel: チャンネル名

    Returns:
        変数が置換された文字列
    """
    # ユーザー表示名の取得
    display_name: str = getattr(author, "display_name", "") or ""
    if not display_name:
        display_name = getattr(author, "name", "unknown")

    now = datetime.now()

    replacements: dict[str, str] = {
        "{user}": display_name,
        "{channel}": channel,
        "{time}": now.strftime("%H:%M"),
        "{date}": now.strftime("%Y/%m/%d"),
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result
