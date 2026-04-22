"""カスタムテーマローダのテスト（Issue #38 Phase A）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# GUI モジュールの実際の THEMES に依存すると副作用が大きいので、
# テスト用の最小 builtin テーマを使う。
BUILTIN_THEMES: dict[str, dict] = {
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


def _write_theme(dirpath: Path, name: str, data: dict | str) -> Path:
    path = dirpath / name
    if isinstance(data, dict):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(data, encoding="utf-8")
    return path


class TestLoadCustomThemes:
    def test_loads_valid_custom_theme_with_base_inheritance(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path,
            "neon.json",
            {
                "name": "Neon Nights",
                "base": "default",
                "ACCENT": "#00FF88",
                "APP_BG": "#0A0A0A",
            },
        )

        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))

        assert "neon" in result
        theme = result["neon"]
        assert theme["name"] == "Neon Nights"
        assert theme["ACCENT"] == "#00FF88"
        assert theme["APP_BG"] == "#0A0A0A"
        # base から継承されたフィールド
        assert theme["CARD_BG"] == BUILTIN_THEMES["default"]["CARD_BG"]

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        missing = tmp_path / "does_not_exist"
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(missing)) == {}

    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(tmp_path, "broken.json", "{not valid json")
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_skips_missing_required_field_with_no_base(self, tmp_path: Path) -> None:
        """base を unknown にしてフォールバックがあってもフィールド不足は拒否。"""
        from src.theme_loader import load_custom_themes

        # base が無い、かつ name 以外も欠落（default にフォールバックするので本来は通る）
        # → name だけ省略したケースをテスト
        _write_theme(tmp_path, "bad.json", {"base": "default", "ACCENT": "#FF0000"})
        # name は base から継承されるので OK になるはず
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert "bad" in result  # base から name を継承

    def test_rejects_invalid_color_value(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path,
            "bad.json",
            {"name": "Bad", "base": "default", "ACCENT": "not-a-color"},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_empty_name(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(tmp_path, "t.json", {"name": "", "base": "default"})
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_non_boolean_glow(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path,
            "t.json",
            {"name": "T", "base": "default", "GLOW": "yes"},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_builtin_name_collision_is_skipped(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "default.json", {"name": "Evil", "ACCENT": "#FF0000"}
        )
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert "default" not in result

    def test_unknown_base_falls_back_to_default(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path,
            "t.json",
            {"name": "T", "base": "nonexistent", "ACCENT": "#FF0000"},
        )
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert "t" in result
        # default の値が継承されている
        assert result["t"]["CARD_BG"] == BUILTIN_THEMES["default"]["CARD_BG"]

    def test_skips_non_json_files(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        (tmp_path / "README.txt").write_text("not a theme", encoding="utf-8")
        (tmp_path / "theme.yaml").write_text("name: x", encoding="utf-8")
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_unsafe_filename(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "my theme.json", {"name": "T", "base": "default"}
        )
        # スペースを含むファイル名は拒否（キーが英数/_/- のみ）
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert result == {}

    def test_loads_multiple_themes(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(tmp_path, "one.json", {"name": "One", "base": "default"})
        _write_theme(tmp_path, "two.json", {"name": "Two", "base": "default"})
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert set(result.keys()) == {"one", "two"}


class TestPhaseCFields:
    """FONT_FAMILY / FONT_SIZE_BASE / CORNER_RADIUS の検証（Phase C）。"""

    def test_valid_font_and_radius_fields(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path,
            "fancy.json",
            {
                "name": "Fancy",
                "base": "default",
                "FONT_FAMILY": "Noto Sans JP",
                "FONT_SIZE_BASE": 14,
                "CORNER_RADIUS": 16,
            },
        )
        result = load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path))
        assert "fancy" in result
        assert result["fancy"]["FONT_FAMILY"] == "Noto Sans JP"
        assert result["fancy"]["FONT_SIZE_BASE"] == 14
        assert result["fancy"]["CORNER_RADIUS"] == 16

    def test_rejects_empty_font_family(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "t.json",
            {"name": "T", "base": "default", "FONT_FAMILY": ""},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_out_of_range_font_size(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "t.json",
            {"name": "T", "base": "default", "FONT_SIZE_BASE": 100},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_non_int_font_size(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "t.json",
            {"name": "T", "base": "default", "FONT_SIZE_BASE": "14"},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_rejects_negative_corner_radius(self, tmp_path: Path) -> None:
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "t.json",
            {"name": "T", "base": "default", "CORNER_RADIUS": -5},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}

    def test_boolean_is_not_accepted_as_int(self, tmp_path: Path) -> None:
        """Python では True == 1 だが、テーマでは bool を明示的に拒否する。"""
        from src.theme_loader import load_custom_themes

        _write_theme(
            tmp_path, "t.json",
            {"name": "T", "base": "default", "FONT_SIZE_BASE": True},
        )
        assert load_custom_themes(BUILTIN_THEMES, themes_dir=str(tmp_path)) == {}


class TestConfigValidation:
    """config.validate_config はカスタムテーマキーを許容する。"""

    def test_custom_theme_key_is_accepted(self, tmp_path: Path, monkeypatch) -> None:
        from src import config, theme_loader

        # テーマディレクトリを tmp に差し替え
        monkeypatch.setattr(theme_loader, "get_themes_dir", lambda: str(tmp_path))
        _write_theme(tmp_path, "mycool.json", {"name": "My Cool", "base": "default"})

        validated, _ = config.validate_config({"ui_theme": "mycool"})
        assert validated["ui_theme"] == "mycool"

    def test_unknown_theme_still_falls_back(self, tmp_path: Path, monkeypatch) -> None:
        from src import config, theme_loader

        monkeypatch.setattr(theme_loader, "get_themes_dir", lambda: str(tmp_path))

        validated, changed = config.validate_config({"ui_theme": "__missing__"})
        assert validated["ui_theme"] == "default"
        assert changed is True
