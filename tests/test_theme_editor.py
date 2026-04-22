"""テーマエディタ関連のユニットテスト（Issue #38 Phase B）。

GUI(CustomTkinter) 本体を起動しないため、純粋ロジック部分
（theme_loader の検証関数）を対象にする。エディタの Toplevel UI 自体は
手動確認に委ねる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestFilenameValidation:
    def test_valid_filenames(self) -> None:
        from src.theme_loader import is_valid_theme_filename
        assert is_valid_theme_filename("my_theme")
        assert is_valid_theme_filename("my-theme")
        assert is_valid_theme_filename("Theme123")

    def test_invalid_filenames(self) -> None:
        from src.theme_loader import is_valid_theme_filename
        assert not is_valid_theme_filename("my theme")
        assert not is_valid_theme_filename("theme.json")
        assert not is_valid_theme_filename("テーマ")
        assert not is_valid_theme_filename("")
        assert not is_valid_theme_filename("../etc/passwd")

    def test_builtin_keys_are_reserved(self) -> None:
        from src.theme_loader import BUILTIN_THEME_KEYS
        assert "default" in BUILTIN_THEME_KEYS
        assert "gradient" in BUILTIN_THEME_KEYS
        assert "minimal" in BUILTIN_THEME_KEYS
        assert "cyberpunk" in BUILTIN_THEME_KEYS


class TestColorValidation:
    def test_valid_colors(self) -> None:
        from src.theme_loader import is_valid_color
        assert is_valid_color("#000")
        assert is_valid_color("#FFFFFF")
        assert is_valid_color("#00000020")  # RGBA 8桁
        assert is_valid_color("#abcdef")

    def test_invalid_colors(self) -> None:
        from src.theme_loader import is_valid_color
        assert not is_valid_color("red")
        assert not is_valid_color("000000")
        assert not is_valid_color("#GGGGGG")
        assert not is_valid_color("")
        assert not is_valid_color(None)
        assert not is_valid_color(123)


class TestImportPathValidation:
    """エディタ _import で適用されるファイル名チェック相当。"""

    def test_accepts_valid_filename(self, tmp_path: Path) -> None:
        from src.theme_loader import BUILTIN_THEME_KEYS, is_valid_theme_filename

        path = tmp_path / "custom_theme.json"
        _write(path, {"name": "Custom", "base": "default"})
        basename = path.stem
        assert is_valid_theme_filename(basename)
        assert basename not in BUILTIN_THEME_KEYS

    def test_rejects_builtin_name(self, tmp_path: Path) -> None:
        from src.theme_loader import BUILTIN_THEME_KEYS

        path = tmp_path / "default.json"
        _write(path, {"name": "Hijack"})
        basename = path.stem
        assert basename in BUILTIN_THEME_KEYS  # 衝突として拒否されるべき


class TestEditorPayloadRoundtrip:
    """エディタが書き出すペイロードが loader を通る。"""

    def test_saved_payload_roundtrips(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        builtin: dict[str, dict] = {
            "default": {
                "name": "Default",
                "APP_BG": "#000000",
                "APP_BG_GRADIENT": "#111111",
                "CARD_BG": "#222222",
                "CARD_BG_GLASS": "#222222",
                "PANEL_BG": "#181818",
                "BORDER": "#333333",
                "ACCENT": "#22C55E",
                "ACCENT_SECONDARY": "#38BDF8",
                "ACCENT_WARN": "#F97316",
                "TEXT_PRIMARY": "#FFFFFF",
                "TEXT_SUBTLE": "#AAAAAA",
                "SHADOW": "#00000020",
                "GLOW": False,
            }
        }

        # エディタが保存するのと同形式のペイロード
        payload = {
            "name": "Editor Saved",
            "base": "default",
            "GLOW": True,
            "APP_BG": "#0A0A0A",
            "APP_BG_GRADIENT": "#111111",
            "CARD_BG": "#1A1A1A",
            "CARD_BG_GLASS": "#1A1A1A",
            "PANEL_BG": "#121212",
            "BORDER": "#2A2A2A",
            "ACCENT": "#00FF88",
            "ACCENT_SECONDARY": "#00BFFF",
            "ACCENT_WARN": "#FFAA00",
            "TEXT_PRIMARY": "#FFFFFF",
            "TEXT_SUBTLE": "#888888",
            "SHADOW": "#00000040",
        }
        _write(tmp_path / "editor_saved.json", payload)
        result = load_custom_themes(builtin, themes_dir=str(tmp_path))
        assert "editor_saved" in result
        assert result["editor_saved"]["ACCENT"] == "#00FF88"
        assert result["editor_saved"]["GLOW"] is True


class TestThemeEditorModuleImport:
    """customtkinter が利用可能なときだけエディタモジュールを import 確認。"""

    def test_module_imports_when_customtkinter_available(self) -> None:
        pytest.importorskip("customtkinter")
        from src import theme_editor  # noqa: F401
        from src.theme_editor import ThemeEditorDialog  # noqa: F401
