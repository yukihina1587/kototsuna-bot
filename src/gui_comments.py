"""コメントカードの描画。モデル実行やネットワーク接続は行わない。"""

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.comment_data import CommentData
from src.gui_theme import readable_color, text_on


def _bind_wrap(label: ctk.CTkLabel) -> None:
    def resize(_event: tk.Event) -> None:
        # CTkLabel.bind は内部の Canvas と Label 両方に届く。
        # event.width を使うと相互に異なる幅を設定し続けるため外枠で統一する。
        width = max(40, label.winfo_width() - 6)
        if label.cget("wraplength") != width:
            label.configure(wraplength=width)

    label.bind("<Configure>", resize)


def _wrapping_label(parent: tk.Misc, text: str, font: tuple, color: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=font, text_color=color,
                         anchor="w", justify="left", width=1, wraplength=240)
    label.pack(fill="x", pady=(2, 4))
    _bind_wrap(label)
    return label


def _emote_text(parent: tk.Misc, comment: CommentData, background: str, foreground: str,
                font: tuple, image_getter: Callable) -> tk.Text:
    widget = tk.Text(parent, wrap="word", width=1, height=1, bg=background, fg=foreground,
                     font=font, borderwidth=0, highlightthickness=0, relief="flat",
                     cursor="arrow", insertwidth=0, padx=0, pady=2)
    widget.pack(fill="x", pady=(2, 4))
    last_end = 0
    for emote in sorted(comment.emotes, key=lambda item: item.get("start", 0)):
        start, end = emote.get("start", 0), emote.get("end", 0) + 1
        if start < last_end or start < 0 or end <= start or end > len(comment.message):
            continue
        widget.insert("end", comment.message[last_end:start])
        image = image_getter(emote)
        if image:
            widget.image_create("end", image=image)
        else:
            widget.insert("end", comment.message[start:end])
        last_end = end
    widget.insert("end", comment.message[last_end:])
    widget.configure(state="disabled")

    def resize(event: tk.Event) -> None:
        if widget.winfo_width() <= 1:
            return
        # 論理行数では折り返された行が欠けるため、実際の表示行数を使う。
        lines = widget.count("1.0", "end-1c", "displaylines")
        height = (lines[0] if lines else 0) + 1
        if int(widget.cget("height")) != height:
            widget.configure(height=height)

    widget.bind("<Configure>", resize)
    return widget


def create_comment_tile(parent: tk.Misc, comment: CommentData, palette: dict,
                        style: str, image_getter: Callable) -> ctk.CTkFrame:
    background = palette["PANEL_BG"]
    text = palette["TEXT_PRIMARY"]
    muted = palette["TEXT_SUBTLE"]
    family = palette.get("FONT_FAMILY", "Segoe UI")
    size = palette.get("FONT_SIZE_BASE", 13)
    radius = 18 if style == "bubble" else (4 if style == "minimal" else palette.get("CORNER_RADIUS", 12))
    tile = ctk.CTkFrame(parent, fg_color=background, corner_radius=radius,
                        border_width=1, border_color=palette["BORDER"])
    body = ctk.CTkFrame(tile, fg_color="transparent")
    body.pack(fill="x", padx=12, pady=10)
    header = ctk.CTkFrame(body, fg_color="transparent")
    header.pack(fill="x", pady=(0, 6))

    avatar_color = readable_color(comment.color, background, palette["ACCENT"])
    avatar = ctk.CTkLabel(header, text=(comment.display_username[:1] or "?").upper(),
                 width=28, height=28, corner_radius=9, fg_color=avatar_color,
                 text_color=text_on(avatar_color), font=(family, size, "bold"))
    avatar.pack(side="left", padx=(0, 8))
    ctk.CTkLabel(header, text=comment.formatted_timestamp, width=55,
                 font=(family, max(10, size - 3)), text_color=muted).pack(side="right", padx=(8, 0))
    # 長いユーザー名は本文の幅に合わせる。バッジとプラットフォームも残す。
    name = f"{comment.display_username} {comment.badge_text}".strip()
    name_label = ctk.CTkLabel(header, text=name, width=1, anchor="w",
                             font=(family, size, "bold"),
                             text_color=readable_color(comment.color, background, text))
    name_label.pack(side="left", fill="x", expand=True)
    _bind_wrap(name_label)

    if comment.emotes:
        message_widget = _emote_text(body, comment, background, text, (family, size), image_getter)
    else:
        message_widget = _wrapping_label(body, comment.message, (family, size), text)
    translated_label = None
    if comment.translated:
        translation = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        translation.pack(fill="x", pady=(5, 2))
        ctk.CTkFrame(translation, width=2, height=1, corner_radius=0,
                     fg_color=palette["ACCENT"]).pack(side="left", fill="y", padx=(0, 9))
        content = ctk.CTkFrame(translation, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True)
        translated_label = _wrapping_label(content, comment.translated, (family, size),
                                           readable_color(palette["ACCENT"], background, text))
    ctk.CTkLabel(body, text=comment.platform_name, height=18,
                 font=(family, max(10, size - 3)), text_color=muted, anchor="w").pack(fill="x", pady=(4, 0))

    def refresh_palette(current: dict) -> None:
        background, foreground = current["PANEL_BG"], current["TEXT_PRIMARY"]
        tile.configure(fg_color=background, border_color=current["BORDER"])
        color = readable_color(comment.color, background, current["ACCENT"])
        avatar.configure(fg_color=color, text_color=text_on(color))
        name_label.configure(text_color=readable_color(comment.color, background, foreground))
        if isinstance(message_widget, tk.Text):
            message_widget.configure(bg=background, fg=foreground)
        else:
            message_widget.configure(text_color=foreground)
        if translated_label is not None:
            translated_label.configure(text_color=readable_color(current["ACCENT"], background, foreground))

    tile._refresh_palette = refresh_palette
    return tile
