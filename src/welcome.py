"""初見視聴者ウェルカムメッセージ機能（Issue #140）。

Twitch IRC `first-msg` タグを利用してチャンネルにおける初発言を検出し、
設定されたテンプレートに従ってチャット／TTS／オーバーレイへ通知する。

このモジュールは純粋ロジックのみを提供し、I/O は呼び出し側で行う。
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any


VALID_WELCOME_TARGETS = {"chat", "tts", "overlay"}
DEFAULT_WELCOME_MESSAGE = "@{user} さん、はじめまして！ようこそ {channel} へ 🎉"
DEFAULT_WELCOME_TARGETS = ["chat"]
DEFAULT_WELCOME_COOLDOWN_SEC = 5
MAX_WELCOME_COOLDOWN_SEC = 3600
MAX_DEDUP_USERS = 5000


class _SafeFormatDict(dict):
    """未知キーが来てもプレースホルダ文字列を残す format_map 用の dict。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalize_targets(raw: Any) -> list[str]:
    """設定値から安全な targets リストを構築する。"""
    if not isinstance(raw, list):
        return list(DEFAULT_WELCOME_TARGETS)
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in VALID_WELCOME_TARGETS and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def format_welcome_message(template: str, *, user: str, channel: str) -> str:
    """テンプレートに `{user}` / `{channel}` を埋め込む。未知キーはそのまま残す。"""
    if not isinstance(template, str) or not template.strip():
        template = DEFAULT_WELCOME_MESSAGE
    payload = _SafeFormatDict(user=str(user or ""), channel=str(channel or ""))
    try:
        return template.format_map(payload)
    except (IndexError, ValueError):
        # `{0}` 等の数値キーや壊れた書式は素のテンプレートを返す
        return template


def is_first_message(tags: dict | None) -> bool:
    """Twitch IRC `first-msg` タグが立っているか判定する。"""
    if not tags:
        return False
    value = tags.get("first-msg") if hasattr(tags, "get") else None
    return value == "1" or value is True


class WelcomeDispatcher:
    """ウェルカム通知の発火可否を判定する純粋ロジック。

    呼び出し側は ``should_fire`` で発火可否を確認し、配信に成功したら
    ``mark_fired`` を必ず呼ぶ（試行ごとではなく成功時に呼ぶこと）。
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        cooldown_sec: int = DEFAULT_WELCOME_COOLDOWN_SEC,
        max_dedup: int = MAX_DEDUP_USERS,
    ) -> None:
        self._enabled = bool(enabled)
        self._cooldown_sec = max(0, min(MAX_WELCOME_COOLDOWN_SEC, int(cooldown_sec)))
        self._max_dedup = max(1, int(max_dedup))
        self._seen_users: set[str] = set()
        self._last_fire_ts: float | None = None

    def update_config(self, *, enabled: bool, cooldown_sec: int) -> None:
        self._enabled = bool(enabled)
        self._cooldown_sec = max(0, min(MAX_WELCOME_COOLDOWN_SEC, int(cooldown_sec)))

    def reset_dedup(self) -> None:
        """セッションを跨いで dedup を初期化する（テスト・GUI のリセット用）。"""
        self._seen_users.clear()
        self._last_fire_ts = None

    def _normalize_user(self, username: str) -> str:
        return (username or "").strip().lower()

    def has_seen(self, username: str) -> bool:
        return self._normalize_user(username) in self._seen_users

    def should_fire(
        self,
        *,
        username: str,
        is_first: bool,
        now: float | None = None,
    ) -> bool:
        """発火条件: 機能 ON、first-msg タグあり、未通知、クールダウン経過。"""
        if not self._enabled:
            return False
        if not is_first:
            return False
        key = self._normalize_user(username)
        if not key:
            return False
        if key in self._seen_users:
            return False
        ts = float(now if now is not None else time.monotonic())
        if self._cooldown_sec > 0 and self._last_fire_ts is not None:
            if (ts - self._last_fire_ts) < self._cooldown_sec:
                return False
        return True

    def mark_fired(self, username: str, *, now: float | None = None) -> None:
        """配信成功時に呼ぶ。dedup 集合とクールダウン時刻を更新する。"""
        key = self._normalize_user(username)
        if not key:
            return
        if len(self._seen_users) >= self._max_dedup:
            # 古いユーザーは雑に消す（厳密 LRU は不要、暴走防止が目的）
            self._seen_users.pop()
        self._seen_users.add(key)
        self._last_fire_ts = float(now if now is not None else time.monotonic())


def build_welcome_payload(
    *,
    template: str,
    user: str,
    channel: str,
    targets: Iterable[str],
) -> dict:
    """配信用ペイロードを生成する。GUI のテスト送信からも利用する。"""
    text = format_welcome_message(template, user=user, channel=channel)
    normalized = [t for t in targets if t in VALID_WELCOME_TARGETS]
    return {
        "text": text,
        "user": str(user or ""),
        "channel": str(channel or ""),
        "targets": normalized,
    }
