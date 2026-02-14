# -*- coding: utf-8 -*-
"""
GUI差分更新ヘルパーモジュール
ウィジェットリストの差分更新を効率的に行うためのユーティリティ
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk
from src.logger import logger


class DifferentialListManager:
    """
    リストの差分更新を管理するクラス。
    全ウィジェットをdestroy→再作成する代わりに、
    追加/削除/変更があった分だけウィジェット操作を行う。
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        key_func: Callable[[Any], str],
        create_widget_func: Callable[[ctk.CTkFrame, Any, int], ctk.CTkFrame],
        empty_widget_func: Optional[Callable[[ctk.CTkFrame], ctk.CTkFrame]] = None,
    ):
        """
        Args:
            parent: ウィジェットの親フレーム
            key_func: アイテムからユニークキーを取得する関数
            create_widget_func: (parent, item, index) -> widget を作成する関数
            empty_widget_func: 空の場合のプレースホルダーを作成する関数
        """
        self.parent = parent
        self.key_func = key_func
        self.create_widget_func = create_widget_func
        self.empty_widget_func = empty_widget_func
        self._current_keys: List[str] = []
        self._widgets: Dict[str, ctk.CTkFrame] = {}
        self._empty_widget: Optional[ctk.CTkFrame] = None

    def update(self, items: List[Any]) -> None:
        """
        アイテムリストに基づいてウィジェットを差分更新する。

        Args:
            items: 表示するアイテムのリスト
        """
        new_keys = [self.key_func(item) for item in items]

        # 空プレースホルダーの管理
        if not items and self.empty_widget_func:
            if self._empty_widget is None:
                # 既存ウィジェットをすべて削除
                self._destroy_all()
                self._empty_widget = self.empty_widget_func(self.parent)
            return
        elif self._empty_widget is not None:
            self._empty_widget.destroy()
            self._empty_widget = None

        old_key_set = set(self._current_keys)
        new_key_set = set(new_keys)

        # 削除: 新しいリストにないキーのウィジェットを削除
        removed_keys = old_key_set - new_key_set
        for key in removed_keys:
            widget = self._widgets.pop(key, None)
            if widget:
                widget.destroy()

        # 順序変更がある場合は全再構築（インデックス番号の正確性を保証）
        remaining_keys = [k for k in self._current_keys if k in new_key_set]
        if new_keys != remaining_keys:
            # 既存ウィジェットをすべて破棄して再作成
            for key in list(self._widgets.keys()):
                self._widgets[key].destroy()
            self._widgets.clear()

            for i, (key, item) in enumerate(zip(new_keys, items)):
                widget = self.create_widget_func(self.parent, item, i)
                self._widgets[key] = widget
        else:
            # 順序は同じで追加のみの場合
            for i, (key, item) in enumerate(zip(new_keys, items)):
                if key not in self._widgets:
                    widget = self.create_widget_func(self.parent, item, i)
                    self._widgets[key] = widget

        self._current_keys = new_keys

    def clear(self) -> None:
        """すべてのウィジェットを削除"""
        self._destroy_all()
        if self._empty_widget:
            self._empty_widget.destroy()
            self._empty_widget = None

    def _destroy_all(self) -> None:
        """管理中の全ウィジェットを破棄"""
        for widget in self._widgets.values():
            widget.destroy()
        self._widgets.clear()
        self._current_keys.clear()

    @property
    def count(self) -> int:
        return len(self._current_keys)


def create_participant_row(
    parent: ctk.CTkFrame,
    participant: Dict[str, str],
    index: int,
    on_edit: Optional[Callable[[str], None]] = None,
    on_delete: Optional[Callable[[str], None]] = None,
    on_drag_start: Optional[Callable] = None,
    on_drag_motion: Optional[Callable] = None,
    on_drag_end: Optional[Callable] = None,
    on_hover: Optional[Callable] = None,
) -> ctk.CTkFrame:
    """
    参加者行ウィジェットを生成する共通ヘルパー。

    Args:
        parent: 親フレーム
        participant: 参加者情報 dict (username, timestamp, keyword)
        index: 表示順インデックス
        on_edit: 編集コールバック
        on_delete: 削除コールバック
        on_drag_start/motion/end: ドラッグ&ドロップ用
        on_hover: ホバー時コールバック

    Returns:
        作成されたフレームウィジェット
    """
    username = participant.get("username", "")

    entry_frame = ctk.CTkFrame(parent)
    entry_frame.pack(fill="x", pady=2, padx=2)
    entry_frame.grid_columnconfigure(0, weight=1)

    info_label = ctk.CTkLabel(
        entry_frame,
        text=f"{index + 1}. {username}",
        font=("Arial", 14, "bold"),
        anchor="w",
    )
    info_label.grid(row=0, column=0, sticky="ew", padx=(5, 2))

    # ドラッグ&ドロップ
    if on_drag_start:
        info_label.bind("<Button-1>", lambda e, idx=index, f=entry_frame: on_drag_start(e, idx, f))
    if on_drag_motion:
        info_label.bind("<B1-Motion>", on_drag_motion)
    if on_drag_end:
        info_label.bind("<ButtonRelease-1>", on_drag_end)
    if on_hover:
        entry_frame.bind("<Enter>", lambda e, idx=index: on_hover(e, idx))

    # ボタン（編集・削除がある場合のみ）
    if on_edit or on_delete:
        button_container = ctk.CTkFrame(entry_frame, fg_color="transparent")
        button_container.grid(row=0, column=1, sticky="e")

        if on_edit:
            ctk.CTkButton(
                button_container,
                text="✏️",
                command=lambda u=username: on_edit(u),
                width=35,
                height=26,
                font=("Arial", 14),
                fg_color="#3B82F6",
                hover_color="#2563EB",
            ).pack(side="left", padx=1)

        if on_delete:
            ctk.CTkButton(
                button_container,
                text="🗑️",
                command=lambda u=username: on_delete(u),
                width=35,
                height=26,
                font=("Arial", 14),
                fg_color="#EF4444",
                hover_color="#DC2626",
            ).pack(side="left", padx=1)

    return entry_frame


def create_simple_list_row(
    parent: ctk.CTkFrame,
    text: str,
    on_remove: Optional[Callable[[], None]] = None,
    font: Tuple[str, int] = ("Segoe UI", 10),
) -> ctk.CTkFrame:
    """
    シンプルなリスト行（テキスト + 削除ボタン）を生成する。

    Args:
        parent: 親フレーム
        text: 表示テキスト
        on_remove: 削除コールバック
        font: テキストのフォント

    Returns:
        作成されたフレームウィジェット
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=1)
    ctk.CTkLabel(row, text=text, font=font).pack(side="left")
    if on_remove:
        ctk.CTkButton(
            row, text="×", width=24, height=24, command=on_remove
        ).pack(side="right")
    return row
