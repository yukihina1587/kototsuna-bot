"""テーマエディター ダイアログ（Issue #38 Phase B）。

builtin テーマを雛形に、カラーピッカーで色を調整してカスタムテーマとして
保存／インポート／エクスポートできる Toplevel ダイアログ。
"""

from __future__ import annotations

import json
import os
import shutil
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from src.logger import logger
from src.theme_loader import (
    BUILTIN_THEME_KEYS,
    get_themes_dir,
    is_valid_color,
    is_valid_theme_filename,
    load_custom_themes,
)


# エディタで編集するカラーフィールドのグループ定義
_COLOR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "基本カラー",
        (
            ("APP_BG", "アプリ背景"),
            ("CARD_BG", "カード背景"),
            ("PANEL_BG", "パネル背景"),
            ("BORDER", "ボーダー"),
        ),
    ),
    (
        "アクセントカラー",
        (
            ("ACCENT", "アクセント（主）"),
            ("ACCENT_SECONDARY", "アクセント（副）"),
            ("ACCENT_WARN", "アクセント（警告）"),
        ),
    ),
    (
        "テキストカラー",
        (
            ("TEXT_PRIMARY", "テキスト（主）"),
            ("TEXT_SUBTLE", "テキスト（副）"),
        ),
    ),
    (
        "詳細",
        (
            ("APP_BG_GRADIENT", "グラデーション先"),
            ("CARD_BG_GLASS", "カード（ガラス）"),
            ("SHADOW", "シャドウ"),
        ),
    ),
)




class ThemeEditorDialog(ctk.CTkToplevel):
    """テーマエディタ Toplevel。

    使い方::

        dlg = ThemeEditorDialog(master, builtin_themes, on_saved=callback)
        dlg.grab_set()
    """

    def __init__(
        self,
        master,
        builtin_themes: dict[str, dict],
        on_saved: Callable[[str], None] | None = None,
        base_theme_key: str = "default",
    ) -> None:
        super().__init__(master)
        self.title("🎨 テーマエディター")
        self.geometry("820x620")
        self.transient(master)
        self.resizable(True, True)

        self._builtin_themes = builtin_themes
        self._on_saved = on_saved

        # 編集中の値
        initial = dict(builtin_themes.get(base_theme_key, builtin_themes["default"]))
        self._color_vars: dict[str, tk.StringVar] = {}
        for _group_label, fields in _COLOR_GROUPS:
            for field, _label in fields:
                self._color_vars[field] = tk.StringVar(value=initial.get(field, "#000000"))

        self._name_var = tk.StringVar(value="My Custom Theme")
        self._base_var = tk.StringVar(
            value=base_theme_key if base_theme_key in BUILTIN_THEME_KEYS else "default"
        )
        self._glow_var = tk.BooleanVar(value=bool(initial.get("GLOW", False)))

        # Phase C: フォント・角丸
        self._font_family_var = tk.StringVar(
            value=str(initial.get("FONT_FAMILY", "Segoe UI"))
        )
        self._font_size_var = tk.IntVar(value=int(initial.get("FONT_SIZE_BASE", 12)))
        self._corner_radius_var = tk.IntVar(value=int(initial.get("CORNER_RADIUS", 10)))

        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=12, pady=12)

        # 2ペイン: 左=エディタ / 右=プレビュー
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        editor = ctk.CTkScrollableFrame(root, fg_color="transparent")
        editor.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._preview_frame = ctk.CTkFrame(root, corner_radius=12)
        self._preview_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # ---- エディタ部 ----
        ctk.CTkLabel(editor, text="テーマ名", font=("Segoe UI Semibold", 12)).pack(
            anchor="w", pady=(0, 2)
        )
        ctk.CTkEntry(editor, textvariable=self._name_var).pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(editor, text="継承元", font=("Segoe UI Semibold", 12)).pack(
            anchor="w", pady=(0, 2)
        )
        ctk.CTkOptionMenu(
            editor,
            variable=self._base_var,
            values=sorted(BUILTIN_THEME_KEYS),
            command=self._on_base_changed,
        ).pack(fill="x", pady=(0, 10))

        for group_label, fields in _COLOR_GROUPS:
            ctk.CTkLabel(editor, text=group_label, font=("Segoe UI Semibold", 12)).pack(
                anchor="w", pady=(6, 2)
            )
            for field, label in fields:
                self._build_color_row(editor, field, label)

        ctk.CTkCheckBox(
            editor, text="グロー効果 (GLOW)", variable=self._glow_var,
            command=self._refresh_preview
        ).pack(anchor="w", pady=(8, 10))

        # Phase C: フォント・角丸
        ctk.CTkLabel(
            editor, text="フォント・形状", font=("Segoe UI Semibold", 12)
        ).pack(anchor="w", pady=(6, 2))

        font_row = ctk.CTkFrame(editor, fg_color="transparent")
        font_row.pack(fill="x", pady=2)
        ctk.CTkLabel(font_row, text="フォント名", width=140, anchor="w").pack(side="left")
        font_entry = ctk.CTkEntry(font_row, textvariable=self._font_family_var, width=200)
        font_entry.pack(side="left")
        font_entry.bind("<FocusOut>", lambda _e: self._refresh_preview())
        font_entry.bind("<Return>", lambda _e: self._refresh_preview())

        size_row = ctk.CTkFrame(editor, fg_color="transparent")
        size_row.pack(fill="x", pady=2)
        ctk.CTkLabel(size_row, text="基本サイズ (8-32)", width=140, anchor="w").pack(
            side="left"
        )
        ctk.CTkOptionMenu(
            size_row,
            variable=self._font_size_var,
            values=[str(n) for n in range(8, 33)],
            command=lambda _v: self._refresh_preview(),
            width=80,
        ).pack(side="left")

        radius_row = ctk.CTkFrame(editor, fg_color="transparent")
        radius_row.pack(fill="x", pady=2)
        ctk.CTkLabel(radius_row, text="角丸 (0-40)", width=140, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            radius_row,
            variable=self._corner_radius_var,
            values=[str(n) for n in range(0, 41, 2)],
            command=lambda _v: self._refresh_preview(),
            width=80,
        ).pack(side="left")

        # ---- ボタン列 ----
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btn_bar, text="保存", command=self._save).pack(side="left", padx=4)
        ctk.CTkButton(btn_bar, text="エクスポート", command=self._export).pack(
            side="left", padx=4
        )
        ctk.CTkButton(btn_bar, text="インポート", command=self._import).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btn_bar, text="プレビュー更新", command=self._refresh_preview
        ).pack(side="left", padx=4)
        ctk.CTkButton(btn_bar, text="閉じる", command=self.destroy).pack(side="right", padx=4)

    def _build_color_row(self, parent, field: str, label: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, textvariable=self._color_vars[field], width=120)
        entry.pack(side="left", padx=(0, 4))
        # 入力確定で即反映
        entry.bind("<FocusOut>", lambda _e: self._refresh_preview())
        entry.bind("<Return>", lambda _e: self._refresh_preview())
        ctk.CTkButton(
            row,
            text="🎨 選択",
            width=70,
            command=lambda f=field: self._pick_color(f),
        ).pack(side="left")

    # --------------------------------------------------------------- events

    def _on_base_changed(self, _display_name: str) -> None:
        base_key = self._base_var.get()
        if base_key not in self._builtin_themes:
            return
        base = self._builtin_themes[base_key]
        for field, var in self._color_vars.items():
            if field in base:
                var.set(base[field])
        self._glow_var.set(bool(base.get("GLOW", False)))
        self._font_family_var.set(str(base.get("FONT_FAMILY", "Segoe UI")))
        self._font_size_var.set(int(base.get("FONT_SIZE_BASE", 12)))
        self._corner_radius_var.set(int(base.get("CORNER_RADIUS", 10)))
        self._refresh_preview()

    def _pick_color(self, field: str) -> None:
        current = self._color_vars[field].get()
        initial = current if is_valid_color(current) else "#000000"
        result = colorchooser.askcolor(color=initial, parent=self, title=f"色を選択: {field}")
        if result and result[1]:
            self._color_vars[field].set(result[1].upper())
            self._refresh_preview()

    # --------------------------------------------------------------- preview

    def _refresh_preview(self) -> None:
        # 全 widget 破棄して再構築
        for child in self._preview_frame.winfo_children():
            child.destroy()

        def c(field: str, fallback: str = "#808080") -> str:
            v = self._color_vars[field].get().strip()
            return v if is_valid_color(v) else fallback

        app_bg = c("APP_BG")
        card_bg = c("CARD_BG")
        panel_bg = c("PANEL_BG")
        border = c("BORDER")
        accent = c("ACCENT")
        accent_sec = c("ACCENT_SECONDARY")
        accent_warn = c("ACCENT_WARN")
        text_primary = c("TEXT_PRIMARY", "#FFFFFF")
        text_subtle = c("TEXT_SUBTLE", "#888888")

        family = (self._font_family_var.get() or "Segoe UI").strip()
        try:
            base_size = max(8, min(32, int(self._font_size_var.get())))
        except (tk.TclError, ValueError):
            base_size = 12
        try:
            radius = max(0, min(40, int(self._corner_radius_var.get())))
        except (tk.TclError, ValueError):
            radius = 10
        font_title = (f"{family} Semibold", base_size + 6)
        font_label = (f"{family} Semibold", base_size)
        font_body = (family, base_size)
        font_sub = (family, max(8, base_size - 1))

        try:
            self._preview_frame.configure(fg_color=app_bg)
        except Exception:
            pass

        ctk.CTkLabel(
            self._preview_frame, text="プレビュー",
            text_color=text_primary, font=font_title,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        card = ctk.CTkFrame(
            self._preview_frame,
            fg_color=card_bg,
            border_color=border,
            border_width=1,
            corner_radius=radius,
        )
        card.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(
            card,
            text=self._name_var.get() or "(無題のテーマ)",
            text_color=text_primary, font=font_label,
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            card, text="サブタイトル（TEXT_SUBTLE）",
            text_color=text_subtle, font=font_sub,
        ).pack(anchor="w", padx=10, pady=(0, 8))

        panel = ctk.CTkFrame(
            self._preview_frame, fg_color=panel_bg, corner_radius=radius
        )
        panel.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(
            panel, text="パネル（PANEL_BG）",
            text_color=text_subtle, font=font_body,
        ).pack(anchor="w", padx=10, pady=6)

        btn_row = ctk.CTkFrame(self._preview_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 10))
        ctk.CTkButton(
            btn_row, text="主ボタン", fg_color=accent, hover_color=accent,
            corner_radius=radius, font=font_body,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="副ボタン", fg_color=accent_sec, hover_color=accent_sec,
            corner_radius=radius, font=font_body,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="警告", fg_color=accent_warn, hover_color=accent_warn,
            corner_radius=radius, font=font_body,
        ).pack(side="left", padx=6)

    # ------------------------------------------------------------------ io

    def _build_theme_payload(self) -> dict:
        payload: dict = {
            "name": self._name_var.get().strip() or "Custom Theme",
            "base": self._base_var.get(),
            "GLOW": bool(self._glow_var.get()),
        }
        for field, var in self._color_vars.items():
            payload[field] = var.get().strip()
        # Phase C: フォント・角丸
        family = (self._font_family_var.get() or "").strip()
        if family:
            payload["FONT_FAMILY"] = family
        try:
            size = int(self._font_size_var.get())
            payload["FONT_SIZE_BASE"] = max(8, min(32, size))
        except (tk.TclError, ValueError):
            pass
        try:
            radius = int(self._corner_radius_var.get())
            payload["CORNER_RADIUS"] = max(0, min(40, radius))
        except (tk.TclError, ValueError):
            pass
        return payload

    def _validate_payload(self, payload: dict) -> tuple[bool, str]:
        if not payload.get("name"):
            return False, "テーマ名を入力してください"
        for field, _ in self._color_vars.items():
            val = payload.get(field, "")
            if not is_valid_color(val):
                return False, f"不正な色コード: {field} = {val!r}"
        return True, ""

    def _save(self) -> None:
        payload = self._build_theme_payload()
        ok, err = self._validate_payload(payload)
        if not ok:
            messagebox.showerror("保存できません", err, parent=self)
            return

        filename = self._ask_filename()
        if not filename:
            return

        themes_dir = get_themes_dir()
        try:
            os.makedirs(themes_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("エラー", f"themes ディレクトリ作成失敗: {e}", parent=self)
            return

        path = os.path.join(themes_dir, f"{filename}.json")
        if os.path.exists(path):
            if not messagebox.askyesno(
                "上書き確認", f"{filename}.json は既に存在します。上書きしますか？",
                parent=self,
            ):
                return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("エラー", f"書き込み失敗: {e}", parent=self)
            return

        # ロードし直して妥当性確認
        reloaded = load_custom_themes(self._builtin_themes, themes_dir=themes_dir)
        if filename not in reloaded:
            messagebox.showwarning(
                "検証エラー",
                "保存しましたが、検証に失敗してロードできませんでした。ログを確認してください。",
                parent=self,
            )
            return

        logger.info(f"Custom theme saved: {path}")
        messagebox.showinfo("保存しました", f"{filename}.json を保存しました", parent=self)
        if self._on_saved is not None:
            self._on_saved(filename)

    def _ask_filename(self) -> str | None:
        """ファイル名（拡張子なし・英数/_/-のみ）を尋ねる。"""
        dlg = ctk.CTkInputDialog(
            text="ファイル名（英数字・アンダースコア・ハイフンのみ）",
            title="テーマを保存",
        )
        value = dlg.get_input()
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not is_valid_theme_filename(value):
            messagebox.showerror(
                "不正なファイル名",
                "ファイル名は英数字・アンダースコア・ハイフンのみ使用できます",
                parent=self,
            )
            return None
        if value in BUILTIN_THEME_KEYS:
            messagebox.showerror(
                "予約語",
                f"{value!r} は組み込みテーマ名と重複します",
                parent=self,
            )
            return None
        return value

    def _export(self) -> None:
        payload = self._build_theme_payload()
        ok, err = self._validate_payload(payload)
        if not ok:
            messagebox.showerror("エクスポートできません", err, parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="テーマをエクスポート",
            defaultextension=".json",
            filetypes=[("Theme JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("エクスポート完了", f"{path} に書き出しました", parent=self)
        except OSError as e:
            messagebox.showerror("エラー", f"書き込み失敗: {e}", parent=self)

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="テーマをインポート",
            filetypes=[("Theme JSON", "*.json")],
        )
        if not path:
            return

        # スキーマ検証のためロードを試みる
        tmpdir = os.path.dirname(path)
        src_basename = os.path.splitext(os.path.basename(path))[0]
        if (
            not is_valid_theme_filename(src_basename)
            or src_basename in BUILTIN_THEME_KEYS
        ):
            messagebox.showerror(
                "インポートできません",
                "ファイル名は英数字・アンダースコア・ハイフンのみ、かつ組み込み名と衝突しないこと",
                parent=self,
            )
            return
        reloaded = load_custom_themes(self._builtin_themes, themes_dir=tmpdir)
        if src_basename not in reloaded:
            messagebox.showerror(
                "検証エラー",
                "JSON の内容が不正です。必須フィールドや色コードを確認してください。",
                parent=self,
            )
            return

        # themes ディレクトリへコピー
        themes_dir = get_themes_dir()
        try:
            os.makedirs(themes_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("エラー", f"themes ディレクトリ作成失敗: {e}", parent=self)
            return

        dst = os.path.join(themes_dir, f"{src_basename}.json")
        if os.path.exists(dst) and not messagebox.askyesno(
            "上書き確認", f"{src_basename}.json は既に存在します。上書きしますか？",
            parent=self,
        ):
            return

        try:
            shutil.copy2(path, dst)
        except OSError as e:
            messagebox.showerror("エラー", f"コピー失敗: {e}", parent=self)
            return

        # エディタを取り込んだテーマで初期化
        imported = reloaded[src_basename]
        self._name_var.set(imported.get("name", src_basename))
        for field, var in self._color_vars.items():
            if field in imported:
                var.set(imported[field])
        self._glow_var.set(bool(imported.get("GLOW", False)))
        self._font_family_var.set(str(imported.get("FONT_FAMILY", "Segoe UI")))
        self._font_size_var.set(int(imported.get("FONT_SIZE_BASE", 12)))
        self._corner_radius_var.set(int(imported.get("CORNER_RADIUS", 10)))
        self._refresh_preview()

        messagebox.showinfo(
            "インポート完了",
            f"{src_basename}.json を取り込みました。UIテーマから選択できます。",
            parent=self,
        )
        logger.info(f"Custom theme imported: {dst}")
        if self._on_saved is not None:
            self._on_saved(src_basename)
