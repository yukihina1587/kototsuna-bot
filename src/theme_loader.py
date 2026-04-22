"""カスタムテーマの JSON ロード（Issue #38 Phase A）。

`<config_dir>/themes/*.json` を起動時にスキャンして、GUI 側の `THEMES`
辞書にマージするためのローダ。builtin テーマを上書きすることはできず、
不正なファイルは警告ログを出してスキップする。

JSON 形式:
    {
        "name": "My Custom Theme",     // UI に表示される名前（必須）
        "base": "default",             // 継承元テーマ（省略時は "default"）
        "APP_BG": "#1A1A1A",           // 以降、上書きしたいフィールドのみ
        "ACCENT": "#00FF88",
        ...
    }
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Iterable

from src.logger import logger


_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def is_valid_theme_filename(name: str) -> bool:
    """テーマ JSON のファイル名（拡張子なし）として妥当か判定。"""
    return bool(_FILENAME_RE.match(name))


def is_valid_color(value: object) -> bool:
    """`#RRGGBB` / `#RGB` / `#RRGGBBAA` 形式の色コードとして妥当か判定。"""
    return isinstance(value, str) and bool(_COLOR_RE.match(value))

_REQUIRED_AFTER_MERGE: tuple[str, ...] = (
    "name",
    "APP_BG",
    "APP_BG_GRADIENT",
    "CARD_BG",
    "CARD_BG_GLASS",
    "PANEL_BG",
    "BORDER",
    "ACCENT",
    "ACCENT_SECONDARY",
    "ACCENT_WARN",
    "TEXT_PRIMARY",
    "TEXT_SUBTLE",
    "SHADOW",
)

_COLOR_FIELDS: tuple[str, ...] = (
    "APP_BG",
    "APP_BG_GRADIENT",
    "CARD_BG",
    "CARD_BG_GLASS",
    "PANEL_BG",
    "BORDER",
    "ACCENT",
    "ACCENT_SECONDARY",
    "ACCENT_WARN",
    "TEXT_PRIMARY",
    "TEXT_SUBTLE",
    "SHADOW",
)

BUILTIN_THEME_KEYS: frozenset[str] = frozenset(
    {"default", "gradient", "minimal", "cyberpunk"}
)


def _get_config_dir() -> str:
    """config.json と同じ親ディレクトリを返す（config._get_config_dir と同ロジック）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_themes_dir() -> str:
    """カスタムテーマ JSON を置くディレクトリのパス。"""
    return os.path.join(_get_config_dir(), "themes")


def _is_valid_color(value: object) -> bool:
    return is_valid_color(value)


def _validate_merged(key: str, theme: dict) -> tuple[bool, str]:
    """base 継承後の完成テーマが全フィールドを満たすかチェック。"""
    for field in _REQUIRED_AFTER_MERGE:
        if field not in theme:
            return False, f"missing required field: {field}"
    for field in _COLOR_FIELDS:
        if not is_valid_color(theme.get(field)):
            return False, f"invalid color value for {field}: {theme.get(field)!r}"
    if not isinstance(theme.get("name"), str) or not theme["name"].strip():
        return False, "name must be a non-empty string"
    # GLOW は省略可（既定 False）
    if "GLOW" in theme and not isinstance(theme["GLOW"], bool):
        return False, "GLOW must be a boolean"

    # Phase C: フォント/角丸（すべて省略可、型だけ検証）
    if "FONT_FAMILY" in theme:
        fam = theme["FONT_FAMILY"]
        if not isinstance(fam, str) or not fam.strip():
            return False, "FONT_FAMILY must be a non-empty string"
    if "FONT_SIZE_BASE" in theme:
        size = theme["FONT_SIZE_BASE"]
        if not isinstance(size, int) or isinstance(size, bool) or not (8 <= size <= 32):
            return False, "FONT_SIZE_BASE must be an int in [8, 32]"
    for radius_field in ("CORNER_RADIUS", "BUTTON_CORNER_RADIUS"):
        if radius_field in theme:
            r = theme[radius_field]
            if not isinstance(r, int) or isinstance(r, bool) or not (0 <= r <= 40):
                return False, f"{radius_field} must be an int in [0, 40]"
    return True, ""


def _load_single(
    path: str, builtin_themes: dict[str, dict]
) -> tuple[str, dict] | None:
    """JSON ファイル 1 件を読み込んで (key, merged_theme) を返す。失敗時 None。"""
    key = os.path.splitext(os.path.basename(path))[0]

    # キー衝突チェック（builtin が勝つ）
    if key in BUILTIN_THEME_KEYS:
        logger.warning(
            f"Custom theme '{key}' conflicts with builtin theme, skipping: {path}"
        )
        return None

    # キーの安全性（英数字とアンダースコア/ハイフンのみ）
    if not is_valid_theme_filename(key):
        logger.warning(f"Invalid theme file name (use alnum/_/- only): {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load theme file {path}: {e}")
        return None

    if not isinstance(raw, dict):
        logger.warning(f"Theme file must be a JSON object: {path}")
        return None

    # base 継承
    base_key = raw.get("base", "default")
    if base_key not in builtin_themes:
        logger.warning(
            f"Theme {key!r}: unknown base {base_key!r}, falling back to 'default'"
        )
        base_key = "default"
    merged: dict = dict(builtin_themes[base_key])

    # base フィールドを除いて上書き
    for field, value in raw.items():
        if field == "base":
            continue
        merged[field] = value

    ok, err = _validate_merged(key, merged)
    if not ok:
        logger.warning(f"Invalid custom theme {key!r} ({path}): {err}")
        return None

    return key, merged


def load_custom_themes(
    builtin_themes: dict[str, dict],
    themes_dir: str | None = None,
) -> dict[str, dict]:
    """themes_dir から全 *.json をロードして { key: merged_theme } を返す。

    Args:
        builtin_themes: GUI 側の THEMES（base 継承の元になる）。
        themes_dir: テスト時に差し替え可能。省略時は `get_themes_dir()`。

    Returns:
        カスタムテーマ辞書。ディレクトリが無い/読み取れない場合は空 dict。
    """
    directory = themes_dir if themes_dir is not None else get_themes_dir()
    if not os.path.isdir(directory):
        return {}

    result: dict[str, dict] = {}
    try:
        entries: Iterable[os.DirEntry] = os.scandir(directory)
    except OSError as e:
        logger.warning(f"Failed to scan themes dir {directory}: {e}")
        return {}

    for entry in entries:
        if not entry.is_file() or not entry.name.lower().endswith(".json"):
            continue
        loaded = _load_single(entry.path, builtin_themes)
        if loaded is not None:
            key, theme = loaded
            result[key] = theme
            logger.info(f"Custom theme loaded: {key} ({theme.get('name')})")

    return result
