"""
チャンネル履歴の管理・入力正規化・Twitch API によるチャンネル存在確認。
"""
import re
import time
from datetime import datetime, timezone
from typing import Optional

from src.logger import logger

HISTORY_MAX = 20
_CACHE_TTL = 300  # 5分

# {login: (valid: bool, display_name: str, user_data: dict, timestamp: float)}
_validation_cache: dict = {}


# ---------------------------------------------------------------------------
# 正規化
# ---------------------------------------------------------------------------

def normalize_channel_name(name: str) -> str:
    """
    URL 貼り付け・大文字小文字を正規化してチャンネルログイン名を返す。
    例: "https://twitch.tv/YukkiHina_Yukky" -> "yukkhina_yukky"
    """
    name = name.strip()
    m = re.search(r'twitch\.tv/([A-Za-z0-9_]+)', name)
    if m:
        name = m.group(1)
    return name.lower()


# ---------------------------------------------------------------------------
# 履歴 CRUD
# ---------------------------------------------------------------------------

def get_history(config: dict) -> list:
    """履歴リスト（コピー）を返す。"""
    return list(config.get("channel_history", []))


def add_to_history(config: dict, login: str, display_name: str = "", user_id: str = "") -> dict:
    """
    接続成功したチャンネルを履歴の先頭に追加（重複は更新・最大 HISTORY_MAX 件）。
    config を in-place で更新して返す。
    """
    login = login.lower()
    history = [h for h in config.get("channel_history", []) if h.get("login", "").lower() != login]
    entry = {
        "login": login,
        "display_name": display_name or login,
        "user_id": user_id or "",
        "last_connected_at": datetime.now(timezone.utc).isoformat(),
    }
    history.insert(0, entry)
    config["channel_history"] = history[:HISTORY_MAX]
    return config


def remove_from_history(config: dict, login: str) -> dict:
    """指定ログインを履歴から削除して返す。"""
    login = login.lower()
    config["channel_history"] = [
        h for h in config.get("channel_history", []) if h.get("login", "").lower() != login
    ]
    return config


# ---------------------------------------------------------------------------
# Twitch API バリデーション（キャッシュ付き）
# ---------------------------------------------------------------------------

def validate_channel(token: str, client_id: str, login: str) -> tuple:
    """
    Twitch /helix/users で存在確認（5分 TTL キャッシュ）。

    Returns:
        (valid: bool, display_name: str, user_data: dict)
        valid=None  → レート制限 / ネットワーク不可（判断保留）
    """
    global _validation_cache
    login = login.lower()
    now = time.monotonic()

    cached = _validation_cache.get(login)
    if cached and now - cached[3] < _CACHE_TTL:
        return cached[0], cached[1], cached[2]

    try:
        import requests
        bearer = token.replace("oauth:", "")
        resp = requests.get(
            f"https://api.twitch.tv/helix/users?login={login}",
            headers={"Authorization": f"Bearer {bearer}", "Client-Id": client_id},
            timeout=5,
        )
        if resp.status_code == 429:
            logger.warning("Twitch API rate limited during channel validation")
            return None, login, {}
        if resp.status_code != 200:
            result = (False, "", {})
        else:
            data = resp.json().get("data", [])
            if data:
                user = data[0]
                result = (True, user.get("display_name", login), user)
            else:
                result = (False, "", {})
    except Exception as e:
        logger.warning(f"Channel validation request failed: {e}")
        return None, login, {}

    _validation_cache[login] = (*result, now)
    return result


def clear_validation_cache(login: Optional[str] = None) -> None:
    """キャッシュをクリア（login 指定なしで全削除）。"""
    global _validation_cache
    if login:
        _validation_cache.pop(login.lower(), None)
    else:
        _validation_cache.clear()
