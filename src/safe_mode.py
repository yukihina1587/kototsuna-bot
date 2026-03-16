"""セーフモード管理 - 起動クラッシュ検出とフォールバック起動。

起動するたびにカウンタを増加させ、正常終了時にリセットする。
CRASH_THRESHOLD 回以上連続クラッシュした場合、セーフモードを提案する。
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

from src.logger import logger

CRASH_THRESHOLD = 2


def _get_state_path() -> str:
    """startup_state.json の保存先パスを返す。

    PyInstallerビルドでは exe と同じフォルダ、
    開発環境ではプロジェクトルートに置く。
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, "startup_state.json")


def _load_state() -> dict[str, Any]:
    path = _get_state_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"startup_state.json 読み込みエラー: {e}")
    return {"crash_count": 0}


def _save_state(state: dict[str, Any]) -> None:
    path = _get_state_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"startup_state.json 書き込みエラー: {e}")


def record_startup() -> int:
    """起動を記録し、インクリメント後の連続クラッシュ回数を返す。

    正常起動が完了したら必ず reset_crash_count() を呼ぶこと。

    Returns:
        現在の連続クラッシュ回数（1以上）
    """
    state = _load_state()
    state["crash_count"] = state.get("crash_count", 0) + 1
    state["last_startup"] = datetime.now().isoformat()
    _save_state(state)
    logger.info(f"Startup recorded. Consecutive crash count: {state['crash_count']}")
    return state["crash_count"]


def reset_crash_count() -> None:
    """正常起動完了時にクラッシュカウントをリセットする。"""
    state = _load_state()
    if state.get("crash_count", 0) != 0:
        state["crash_count"] = 0
        state["last_success"] = datetime.now().isoformat()
        _save_state(state)
        logger.info("Crash count reset after successful startup")


def should_suggest_safe_mode(crash_count: int) -> bool:
    """セーフモードを提案すべきかを返す。

    Args:
        crash_count: record_startup() の戻り値
    """
    return crash_count >= CRASH_THRESHOLD
