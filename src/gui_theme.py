"""ことつなの共通配色。設定キーとカスタムテーマの継承形式は維持する。"""

from copy import deepcopy
import re

THEMES = {
    "gradient": {  # 案1: グラデーション × グラスモーフィズム
        "name": "グラデーション（モダン）",
        "APP_BG": "#0A0E27",
        "APP_BG_GRADIENT": "#1A1535",  # グラデーション用
        "CARD_BG": "#1C1F3A",
        "CARD_BG_GLASS": "#1C1F3A",  # 半透明風
        "PANEL_BG": "#151830",
        "BORDER": "#2D3250",
        "ACCENT": "#00D9FF",  # シアン
        "ACCENT_SECONDARY": "#FF00E5",  # マゼンタ
        "ACCENT_WARN": "#FFB800",
        "TEXT_PRIMARY": "#FFFFFF",
        "TEXT_SUBTLE": "#A0A8C8",
        "SHADOW": "#000000",
        "GLOW": True,  # グロー効果を有効化
    },
    "minimal": {  # 案2: ミニマリスト × マテリアルデザイン
        "name": "ミニマル（シンプル）",
        "APP_BG": "#FAFAFA",
        "APP_BG_GRADIENT": "#F5F5F5",
        "CARD_BG": "#FFFFFF",
        "CARD_BG_GLASS": "#FFFFFF",
        "PANEL_BG": "#F8F9FA",
        "BORDER": "#E0E0E0",
        "ACCENT": "#1976D2",  # Material Blue
        "ACCENT_SECONDARY": "#0288D1",
        "ACCENT_WARN": "#F57C00",
        "TEXT_PRIMARY": "#212121",
        "TEXT_SUBTLE": "#757575",
        "SHADOW": "#00000015",
        "GLOW": False,
    },
    "cyberpunk": {  # 案3: サイバーパンク × ゲーミング
        "name": "サイバーパンク（ゲーミング）",
        "APP_BG": "#000000",
        "APP_BG_GRADIENT": "#0D0208",
        "CARD_BG": "#0A0A0A",
        "CARD_BG_GLASS": "#1A1A1A",
        "PANEL_BG": "#050505",
        "BORDER": "#FF00FF",  # ネオンピンク
        "ACCENT": "#00FFFF",  # ネオンシアン
        "ACCENT_SECONDARY": "#FF00FF",  # ネオンマゼンタ
        "ACCENT_WARN": "#FFFF00",  # ネオンイエロー
        "TEXT_PRIMARY": "#00FFFF",
        "TEXT_SUBTLE": "#008080",  # ダークシアン（半透明の代替）
        "SHADOW": "#004040",  # ダークシアン（半透明の代替）
        "GLOW": True,  # グロー効果強め
    },
    "default": {  # 現在のデフォルトテーマ（既存）
        "name": "デフォルト（クラシック）",
        "APP_BG": "#0C1424",
        "APP_BG_GRADIENT": "#0C1424",
        "CARD_BG": "#111B2E",
        "CARD_BG_GLASS": "#111B2E",
        "PANEL_BG": "#0E1728",
        "BORDER": "#1F2C43",
        "ACCENT": "#22C55E",
        "ACCENT_SECONDARY": "#38BDF8",
        "ACCENT_WARN": "#F97316",
        "TEXT_PRIMARY": "#FFFFFF",
        "TEXT_SUBTLE": "#9BAEC6",
        "SHADOW": "#00000020",
        "GLOW": False,
    }
}

# 既存キーを維持し、カスタムテーマにも同じ基準のコントラストを適用する。
THEMES["default"].update({
    "name": "デフォルト（フォレスト）",
    "APP_BG": "#111715", "APP_BG_GRADIENT": "#111715",
    "CARD_BG": "#1A2420", "CARD_BG_GLASS": "#1A2420",
    "PANEL_BG": "#151E1A", "BORDER": "#34483C",
    "ACCENT": "#91D5B3", "ACCENT_SECONDARY": "#BDB6EB",
    "ACCENT_WARN": "#EDBD7A", "TEXT_PRIMARY": "#EAF2EC",
    "TEXT_SUBTLE": "#A8B8AE", "SHADOW": "#080D0A",
    "CORNER_RADIUS": 14, "BUTTON_CORNER_RADIUS": 8,
    "FONT_SIZE_BASE": 13,
})
THEMES["minimal"].update({
    "APP_BG": "#F3F5F2", "PANEL_BG": "#EAF0EA", "BORDER": "#CCD8CF",
    "ACCENT": "#256B4D", "ACCENT_SECONDARY": "#6551A1",
    "ACCENT_WARN": "#9B570B", "TEXT_PRIMARY": "#20382A",
    "TEXT_SUBTLE": "#53675A", "CORNER_RADIUS": 14,
    "BUTTON_CORNER_RADIUS": 8, "FONT_SIZE_BASE": 13,
})
THEMES["cyberpunk"]["TEXT_SUBTLE"] = "#64B4B4"


def luminance(color: str) -> float:
    """sRGB の相対輝度。テーマで許可済みの RGB / RGBA を受け取る。"""
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def text_on(background: str) -> str:
    """アクセント色が明るくても暗くてもボタン文字を読めるようにする。"""
    return max(("#101A14", "#FFFFFF"), key=lambda color: contrast_ratio(color, background))


def readable_color(color: str | None, background: str, fallback: str) -> str:
    """外部のユーザー色が背景に埋もれる場合はテーマの文字色に戻す。"""
    try:
        if isinstance(color, str) and re.fullmatch(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", color) and contrast_ratio(color, background) >= 4.5:
            return color
    except (ValueError, TypeError, AttributeError):
        pass
    return fallback


def widget_theme(base: dict, palette: dict) -> dict:
    """CTk の既定スキーマを保ったまま全コントロールの色を統一する。"""
    result = deepcopy(base)
    card, panel = palette["CARD_BG"], palette["PANEL_BG"]
    border, accent = palette["BORDER"], palette["ACCENT"]
    text, muted = palette["TEXT_PRIMARY"], palette["TEXT_SUBTLE"]
    on_accent = text_on(accent)
    radius = palette.get("CORNER_RADIUS", 12)
    button_radius = palette.get("BUTTON_CORNER_RADIUS", 8)
    overrides = {
        "CTk": {"fg_color": palette["APP_BG"]},
        "CTkToplevel": {"fg_color": palette["APP_BG"]},
        "CTkFrame": {"fg_color": card, "top_fg_color": card, "border_color": border, "corner_radius": radius},
        "CTkLabel": {"text_color": text},
        "CTkButton": {"fg_color": panel, "hover_color": border, "text_color": text,
                      "text_color_disabled": muted, "border_color": border, "corner_radius": button_radius},
        "CTkEntry": {"fg_color": panel, "border_color": border, "border_width": 1,
                     "text_color": text, "placeholder_text_color": muted, "corner_radius": button_radius},
        "CTkCheckBox": {"fg_color": accent, "hover_color": accent, "border_color": muted,
                        "text_color": text, "text_color_disabled": muted, "checkmark_color": on_accent},
        "CTkRadioButton": {"fg_color": accent, "hover_color": accent, "border_color": muted,
                           "text_color": text, "text_color_disabled": muted},
        "CTkSwitch": {"fg_color": border, "progress_color": accent, "button_color": text,
                      "button_hover_color": muted, "text_color": text, "text_color_disabled": muted},
        "CTkSlider": {"fg_color": border, "progress_color": accent, "button_color": accent, "button_hover_color": text},
        "CTkProgressBar": {"fg_color": border, "progress_color": accent},
        "CTkOptionMenu": {"fg_color": panel, "button_color": border, "button_hover_color": card,
                          "text_color": text, "text_color_disabled": muted, "corner_radius": button_radius},
        "CTkComboBox": {"fg_color": panel, "border_color": border, "button_color": border,
                        "button_hover_color": card, "text_color": text, "text_color_disabled": muted, "border_width": 1},
        "CTkScrollbar": {"button_color": border, "button_hover_color": muted},
        "CTkSegmentedButton": {"fg_color": panel, "selected_color": border, "selected_hover_color": border,
                               "unselected_color": panel, "unselected_hover_color": card, "text_color": text},
        "CTkTextbox": {"fg_color": panel, "text_color": text, "border_color": border,
                       "scrollbar_button_color": border, "scrollbar_button_hover_color": muted},
        "CTkScrollableFrame": {"label_fg_color": card},
        "DropdownMenu": {"fg_color": panel, "hover_color": border, "text_color": text},
        "CTkFont": {"family": palette.get("FONT_FAMILY", "Segoe UI"), "size": palette.get("FONT_SIZE_BASE", 13)},
    }
    for name, values in overrides.items():
        result[name] = {**result.get(name, {}), **values}
    return result


def apply_widget_theme(palette: dict) -> None:
    import customtkinter as ctk

    ctk.ThemeManager.theme = widget_theme(ctk.ThemeManager.theme, palette)
    ctk.set_appearance_mode("Light" if luminance(palette["APP_BG"]) > 0.5 else "Dark")


def refresh_widget_colors(root, previous: dict, palette: dict) -> None:
    """既存ウィジェットを再生成せず、入力・スクロール・接続先を保って配色する。"""
    import tkinter as tk
    import customtkinter as ctk

    before = widget_theme(ctk.ThemeManager.theme, previous)
    after = widget_theme(ctk.ThemeManager.theme, palette)
    surface_roles = ("APP_BG", "CARD_BG", "PANEL_BG", "BORDER", "ACCENT", "ACCENT_SECONDARY", "ACCENT_WARN")
    text_roles = ("TEXT_PRIMARY", "TEXT_SUBTLE", "ACCENT", "ACCENT_SECONDARY", "ACCENT_WARN")
    plans, callbacks = [], []

    def visit(widget):
        if isinstance(widget, tk.Toplevel) and widget is not root:
            # テーマエディターなどの独立したプレビュー配色には触れない。
            return
        defaults = before.get(type(widget).__name__, {})
        new_defaults = after.get(type(widget).__name__, {})
        is_ctk = isinstance(widget, (ctk.CTk, ctk.CTkBaseClass, ctk.CTkScrollableFrame))
        if is_ctk:
            options = {key for key in defaults if "color" in key}
            options.update(("fg_color", "bg_color", "text_color", "border_color"))
            if isinstance(widget, (ctk.CTkOptionMenu, ctk.CTkComboBox)):
                for key, value in before["DropdownMenu"].items():
                    if "color" in key:
                        option = "dropdown_" + key
                        options.add(option)
                        defaults = {**defaults, option: value}
                        new_defaults = {**new_defaults, option: after["DropdownMenu"][key]}
        elif isinstance(widget, tk.PanedWindow):
            options = {"background"}
        elif isinstance(widget, tk.Text) and not isinstance(widget.master, ctk.CTkTextbox):
            options = {"background", "foreground", "insertbackground", "selectbackground"}
        else:
            options = set()

        bindings = getattr(widget, "_palette_bindings", {})
        updates = {}
        for option in options:
            try:
                value = widget.cget(option)
            except (ValueError, AttributeError, tk.TclError):
                continue  # CTk の既定スキーマには公開されていない項目も含まれる。
            if value is None or value == "transparent":
                continue
            binding = bindings.get(option)
            if binding is None or value != binding[2]:
                binding = None
                if option == "text_color":
                    background = widget.cget("fg_color")
                    if isinstance(background, str) and background.startswith("#") and value == text_on(background):
                        binding = ("contrast", "fg_color", value)
                if binding is None and option in defaults and value == defaults[option]:
                    binding = ("default", option, value)
                if binding is None:
                    roles = text_roles if option in ("text_color", "foreground", "insertbackground") else surface_roles + text_roles
                    for role in roles:
                        if value == previous[role]:
                            binding = ("palette", role, value)
                            break
            if binding is None:
                continue  # 固定の警告色やユーザー指定の色は維持する。
            kind, key, _ = binding
            if kind == "palette":
                updates[option] = palette[key]
            elif kind == "default":
                updates[option] = new_defaults[key]
            bindings[option] = binding

        contrast = bindings.get("text_color")
        if contrast and contrast[0] == "contrast":
            background = updates.get("fg_color", widget.cget("fg_color"))
            if isinstance(background, str) and background.startswith("#"):
                updates["text_color"] = text_on(background)
        # 色が同じカスタムテーマを経由しても、元の役割を見失わないよう保持する。
        for option, value in updates.items():
            kind, key, _ = bindings[option]
            bindings[option] = (kind, key, value)
        widget._palette_bindings = bindings
        if updates:
            plans.append((widget, updates))
        callback = getattr(widget, "_refresh_palette", None)
        if callback:
            callbacks.append(callback)
        # CTkTabview等は通常のwinfo_childrenから内部コントロールを隠す。
        for child in tk.Misc.winfo_children(widget):
            visit(child)

    visit(root)
    # 親のconfigureが子の背景も更新するため、全ウィジェットの旧色を先に読む。
    for widget, updates in plans:
        widget.configure(**updates)
    for callback in callbacks:
        callback(palette)
