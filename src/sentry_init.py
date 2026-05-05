"""
Sentry SDK 初期化とイベントスクラブ。

PR1 ではモジュールのみ用意し、`init_sentry()` の呼び出しは PR2（オプトイン UI）で
config フラグ参照と合わせて main.py に追加する想定。

設計方針:
- 配信者向けツールという性質上、PII（チャンネル名・コメント本文・トークン等）を
  Sentry に送らない。`_scrub_event` で `before_send` フックとして除去する。
- `sentry-sdk` が import 失敗しても本体起動は止めない（外部依存のため）。
- Tkinter のボタンコールバック例外は `Tk.report_callback_exception` を上書きして
  Sentry に転送する（標準の sys.excepthook では拾えないため）。
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Callable, Optional

from src import __version__
from src.logger import _mask_secrets

# 最後に捕捉した Sentry イベント ID（ユーザーフィードバック紐付け用、PR3）
_last_event_id: Optional[str] = None
# 例外捕捉時に呼ばれるコールバック（GUI 側でフィードバックダイアログを出す用、PR3）
_post_capture_callback: Optional[Callable[[str], None]] = None

# 公開可能な DSN 定数（Sentry 設計上、クライアント配布アプリでは公開で問題ない）
# 環境変数 KOTOTSUNA_SENTRY_DSN で上書き可能
_DEFAULT_DSN = (
    "https://ae70bf69c755394587c8d7439e5b91c9"
    "@o4511336076476416.ingest.us.sentry.io/4511336079294464"
)

# event の extra / breadcrumb data から伏せ字にするキー
_REDACT_KEYS = frozenset({
    "channel", "channel_name", "username", "display_name", "user",
    "message", "comment", "text", "content",
    "oauth", "oauth_token", "access_token", "refresh_token",
    "client_secret", "password", "token",
})

_REDACTED = "***"

_module_logger = logging.getLogger("KototsunaBot")


def _redact_mapping(data: Any) -> Any:
    """dict / list を再帰的に走査して機微キーを伏せ字にする。"""
    if isinstance(data, dict):
        return {
            k: (_REDACTED if k.lower() in _REDACT_KEYS else _redact_mapping(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_redact_mapping(x) for x in data]
    if isinstance(data, str):
        return _mask_secrets(data)
    return data


def _scrub_event(event: dict, hint: dict) -> Optional[dict]:
    """before_send フック: PII を除去し、無害な例外をドロップする。"""
    # 既知の無害例外はドロップ
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_type = exc_info[0]
        if exc_type is KeyboardInterrupt or exc_type is SystemExit:
            return None

    # ユーザー情報は送らない
    event.pop("user", None)

    # メッセージ・例外メッセージにシークレットマスクを適用
    if "message" in event and isinstance(event["message"], str):
        event["message"] = _mask_secrets(event["message"])

    for exc in event.get("exception", {}).get("values", []) or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = _mask_secrets(exc["value"])
        # ローカル変数（vars）はそもそも with_locals=False で送らない設定だが念のため除去
        for frame in exc.get("stacktrace", {}).get("frames", []) or []:
            frame.pop("vars", None)

    # extra / contexts / breadcrumbs を再帰的に伏せ字
    if "extra" in event:
        event["extra"] = _redact_mapping(event["extra"])
    if "contexts" in event:
        event["contexts"] = _redact_mapping(event["contexts"])

    for crumb in event.get("breadcrumbs", {}).get("values", []) or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = _mask_secrets(crumb["message"])
        if "data" in crumb:
            crumb["data"] = _redact_mapping(crumb["data"])

    return event


def _install_tk_excepthook() -> None:
    """Tkinter コールバック内の例外を Sentry に転送するフックを仕込む。

    Tk はコールバック例外を独自の `report_callback_exception` で処理するため、
    sys.excepthook では拾えない。クラス側を上書きすることで CustomTkinter の
    `CTk` などサブクラスにも一括適用される。
    """
    try:
        import tkinter as tk
        import sentry_sdk
    except Exception:
        return

    _original = tk.Tk.report_callback_exception

    def _hooked(self, exc, val, tb):
        global _last_event_id
        try:
            event_id = sentry_sdk.capture_exception((exc, val, tb))
            if event_id:
                _last_event_id = event_id
                # フィードバックダイアログ等のコールバックを発火（登録されていれば）
                if _post_capture_callback is not None:
                    try:
                        _post_capture_callback(event_id)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            _original(self, exc, val, tb)
        except Exception:
            pass

    tk.Tk.report_callback_exception = _hooked  # type: ignore[assignment]


def register_post_capture_callback(callback: Optional[Callable[[str], None]]) -> None:
    """例外捕捉後に呼ばれるコールバックを登録する（GUI でフィードバックUIを出す用）。

    callback は event_id を引数に取る。GUI 側は after() でメインスレッドに戻すこと。
    None を渡すと解除。
    """
    global _post_capture_callback
    _post_capture_callback = callback


def get_last_event_id() -> Optional[str]:
    """最後に Sentry が捕捉したイベント ID を返す（無ければ None）。"""
    return _last_event_id


def submit_feedback(message: str, name: str = "", email: str = "",
                    event_id: Optional[str] = None) -> bool:
    """ユーザー入力フィードバックを Sentry に送信する。

    Args:
        message: ユーザーが書いた再現手順や説明。空なら送信しない。
        name: 任意の表示名。
        email: 任意のメールアドレス。
        event_id: 紐付けたい Sentry イベント ID。None なら直近の捕捉ID。

    Returns:
        送信を試みた場合 True、SDK欠落・メッセージ空・例外などで送らなかった場合 False。
    """
    if not message or not message.strip():
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False

    target_event_id = event_id or _last_event_id

    try:
        # sentry-sdk 2.7+ は capture_feedback、それ以前は capture_user_feedback。
        # 両対応で捕捉する。
        if hasattr(sentry_sdk, "capture_feedback"):
            sentry_sdk.capture_feedback(
                {
                    "message": message.strip(),
                    "name": name.strip() or None,
                    "contact_email": email.strip() or None,
                    "associated_event_id": target_event_id,
                }
            )
        elif hasattr(sentry_sdk, "capture_user_feedback") and target_event_id:
            sentry_sdk.capture_user_feedback(
                {
                    "event_id": target_event_id,
                    "name": name.strip() or "anonymous",
                    "email": email.strip() or "anonymous@example.com",
                    "comments": message.strip(),
                }
            )
        else:
            return False
    except Exception as e:
        _module_logger.warning(f"[Sentry] feedback送信に失敗: {e}")
        return False
    return True


def init_sentry(enabled: bool, dsn: Optional[str] = None) -> bool:
    """Sentry SDK を初期化する。

    Args:
        enabled: ユーザーがクラッシュレポート送信に同意しているかどうか。
                 False の場合は何もせず即座に False を返す（=送信されない）。
        dsn: 明示的に DSN を指定する場合に渡す。省略時は環境変数 → 定数 の順。

    Returns:
        実際に初期化が走った場合 True。同意なし / SDK欠落 / DSN欠落時は False。
    """
    if not enabled:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        _module_logger.warning(
            "[Sentry] sentry-sdk が import できないためテレメトリを無効化します"
        )
        return False

    effective_dsn = dsn or os.environ.get("KOTOTSUNA_SENTRY_DSN") or _DEFAULT_DSN
    if not effective_dsn:
        return False

    try:
        sentry_sdk.init(
            dsn=effective_dsn,
            release=f"kototsuna@{__version__}",
            environment="production" if getattr(sys, "frozen", False) else "development",
            send_default_pii=False,
            traces_sample_rate=0.0,
            max_breadcrumbs=50,
            attach_stacktrace=False,
            include_local_variables=False,
            before_send=_scrub_event,
            integrations=[
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
    except Exception as e:
        _module_logger.warning(f"[Sentry] init に失敗しました: {e}")
        return False

    _install_tk_excepthook()
    _module_logger.info(f"[Sentry] initialized (release=kototsuna@{__version__})")
    return True
