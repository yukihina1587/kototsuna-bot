"""配色の可読性と既存テーマ形式との互換性。GUIなしで実行できる。"""

from copy import deepcopy

import pytest

from src.gui_theme import THEMES, contrast_ratio, readable_color, text_on, widget_theme
from src.theme_loader import _validate_merged


@pytest.mark.parametrize("name", THEMES)
def test_builtin_palettes_keep_readable_text_and_compatible_schema(name):
    palette = THEMES[name]
    assert _validate_merged(name, palette) == (True, "")
    for background in ("APP_BG", "CARD_BG", "PANEL_BG"):
        for foreground in ("TEXT_PRIMARY", "TEXT_SUBTLE"):
            assert contrast_ratio(palette[foreground], palette[background]) >= 4.5
    assert contrast_ratio(text_on(palette["ACCENT"]), palette["ACCENT"]) >= 4.5


def test_widget_palette_does_not_mutate_input_or_remove_ctk_settings():
    original = {"CTkSwitch": {"button_length": 0, "text_color": "old"}}
    snapshot = deepcopy(original)
    result = widget_theme(original, THEMES["minimal"])
    assert original == snapshot
    assert result["CTkSwitch"]["button_length"] == 0
    assert result["CTkSwitch"]["text_color"] == THEMES["minimal"]["TEXT_PRIMARY"]


@pytest.mark.parametrize("color", [None, "invalid", "#ZZZZZZ", "#111715", "", "#FFFFFFextra", "#FFFFFF20"])
def test_unreadable_or_invalid_viewer_colors_fall_back(color):
    assert readable_color(color, "#111715", "#FFFFFF") == "#FFFFFF"


def test_readable_viewer_color_is_kept():
    assert readable_color("#91D5B3", "#111715", "#FFFFFF") == "#91D5B3"


@pytest.mark.parametrize("color", ["#fff", "#FFFFFF", "#FFFFFF20"])
def test_supported_theme_color_formats(color):
    assert contrast_ratio(color, "#000000") == pytest.approx(21.0)
