"""配信ワークスペースの表示。接続・翻訳・保存処理はアプリ側に残す。"""

import tkinter as tk
from collections import deque
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

from src.gui_theme import contrast_ratio, text_on
from src.logger import logger


PANEL_INFO = {
    "settings": ("設定", "接続・音声・見た目を、自分の配信に合わせて。"),
    "dictionary": ("辞書", "読み方や翻訳を、いつもの言葉に。"),
    "participants": ("参加者", "参加の受付と順番を管理します。"),
    "viewers": ("常連管理", "視聴者ごとの声と来訪履歴。"),
    "commands": ("コマンド", "チャットから使える操作を設定します。"),
    "plugins": ("プラグイン", "配信に合わせて機能を追加。"),
    "subtitle": ("字幕設定", "音声翻訳を配信画面に表示します。"),
    "obs": ("OBS連携", "配信画面への表示とシーン連携。"),
    "comment_tester": ("テスト送信", "コメントの表示や動作を確認します。"),
    "resources": ("リソース", "アプリの使用状況を確認します。"),
}


class WorkspaceLayoutMixin:
    """KototsunaApp の変数とコールバックをそのまま使う表示層。"""

    def _font(self, size: int = 13, weight: str = "normal") -> tuple:
        adjusted = max(10, size + self.ui_palette.get("FONT_SIZE_BASE", 13) - 13)
        return (self.ui_palette.get("FONT_FAMILY", "Segoe UI"), adjusted, weight)

    def _surface(self, parent: tk.Misc, palette_role: str = "CARD_BG", **kwargs) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, **{
            "fg_color": self.ui_palette[palette_role], "border_width": 1,
            "border_color": self.ui_palette["BORDER"],
            "corner_radius": self.ui_palette.get("CORNER_RADIUS", 14), **kwargs,
        })
        frame._palette_bindings = {"fg_color": ("palette", palette_role, frame.cget("fg_color"))}
        return frame

    def _button(self, parent: tk.Misc, text: str, command: Callable,
                primary: bool = False, **kwargs) -> ctk.CTkButton:
        palette = self.ui_palette
        button = ctk.CTkButton(parent, **{
            "text": text, "command": command, "height": 34, "font": self._font(12),
            "fg_color": palette["ACCENT"] if primary else palette["PANEL_BG"],
            "text_color": text_on(palette["ACCENT"]) if primary else palette["TEXT_PRIMARY"],
            "hover_color": palette["ACCENT_SECONDARY"] if primary else palette["BORDER"],
            **kwargs,
        })
        # サイバーパンク等で境界とアクセントが同色でも用途を区別する。
        roles = {"fg_color": "ACCENT" if primary else "PANEL_BG",
                 "hover_color": "ACCENT_SECONDARY" if primary else "BORDER"}
        button._palette_bindings = {
            option: ("palette", role, button.cget(option))
            for option, role in roles.items() if button.cget(option) == palette[role]
        }
        return button

    def build_widgets(self) -> None:
        self.main_frame = ctk.CTkFrame(self.master, fg_color=self.ui_palette["APP_BG"], corner_radius=0)
        self.main_frame._palette_bindings = {"fg_color": ("palette", "APP_BG", self.ui_palette["APP_BG"])}
        self.main_frame.pack(fill="both", expand=True)
        if self.safe_mode:
            self._build_safe_mode_banner()
        if self.diag_bundle_path:
            self._build_diag_bundle_banner(self.diag_bundle_path)
        self._build_header()
        self.body_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.body_container.grid_columnconfigure(1, weight=1)
        self.body_container.grid_rowconfigure(0, weight=1)
        self._build_left_sidebar()
        self._build_main_content()
        self.master.bind("<Escape>", self._dismiss_panel, add="+")

    def _build_header(self) -> None:
        p = self.ui_palette
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 12))
        header.grid_columnconfigure(1, weight=1)
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, rowspan=2, sticky="w", padx=(20, 24))
        self._brand_icon_image = None
        try:
            icon_path = Path(self._get_icon_path()).with_name("icon_fullsize.ico")
            with Image.open(icon_path) as source:
                icon = source.copy()
            scale = 40 / max(icon.size)
            size = (max(1, round(icon.width * scale)), max(1, round(icon.height * scale)))
            self._brand_icon_image = ctk.CTkImage(light_image=icon, dark_image=icon, size=size)
        except OSError as exc:
            # 装飾画像が欠けても接続操作まで使えなくしない。
            logger.warning("Header icon could not be loaded (%s)", type(exc).__name__)
        self.brand_icon = ctk.CTkLabel(brand, text="", image=self._brand_icon_image,
                                      width=40, height=40, fg_color="transparent")
        self.brand_icon.pack(side="left", padx=(0, 10))
        wordmark = ctk.CTkFrame(brand, fg_color="transparent")
        wordmark.pack(side="left")
        ctk.CTkLabel(wordmark, text="ことつな！", font=self._font(22, "bold"),
                     height=28, anchor="w").pack(fill="x")
        ctk.CTkLabel(wordmark, text="ことばで、配信をつなぐ。", text_color=p["TEXT_SUBTLE"],
                     font=self._font(10), height=18).pack(anchor="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        self.header_channel_label = self._button(
            actions, "チャンネルを設定  ›", lambda: self._toggle_right_panel("settings"), width=168,
        )
        self.header_channel_label.pack(side="left", padx=(0, 8))
        self.channel.trace_add("write", self._update_channel_display)
        self._update_channel_display()
        self.auth_btn = self._button(actions, "① Twitch認証", self.start_auth, width=112)
        self.auth_btn.pack(side="left", padx=(0, 8))
        self.start_stop_btn = self._button(actions, "② BOT開始", self._toggle_bot_from_header,
                                         primary=True, width=112)
        self.start_stop_btn.pack(side="left", padx=(0, 8))
        self.disconnect_btn = self._button(actions, "全停止", self.disconnect_all, width=72,
                                           text_color=p["ACCENT_WARN"], border_width=1)
        self.disconnect_btn.pack(side="left")

        state = ctk.CTkFrame(header, fg_color="transparent")
        state.grid(row=1, column=1, sticky="e", pady=(6, 0))
        self.connection_badge = ctk.CTkLabel(state, text="● 未接続", font=self._font(11),
                                            text_color=p["TEXT_SUBTLE"], height=22)
        self.connection_badge.pack(side="left", padx=(0, 12))
        self.status_label = ctk.CTkLabel(state, text="Twitch認証から始めましょう", font=self._font(11),
                                        text_color=p["TEXT_SUBTLE"], height=22)
        self.status_label.pack(side="left")

    def _build_left_sidebar(self) -> None:
        p = self.ui_palette
        sidebar = self._surface(self.body_container, palette_role="PANEL_BG", width=220)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(12, 12))
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(0, weight=1)
        top = ctk.CTkScrollableFrame(sidebar, fg_color="transparent", width=188,
                                    scrollbar_button_color=p["BORDER"])
        top.grid(row=0, column=0, sticky="nsew", padx=8, pady=(10, 0))
        self._add_sidebar_section(top, "配信コントロール")
        ctk.CTkLabel(top, text="翻訳モード", text_color=p["TEXT_SUBTLE"],
                     font=self._font(11), anchor="w", height=18).pack(fill="x", pady=(0, 3))
        ctk.CTkOptionMenu(top, variable=self.lang_mode, values=["自動", "英→日", "日→英"],
                          height=34, font=self._font()).pack(fill="x", pady=(0, 10))
        self._add_sidebar_toggle(top, "チャット翻訳", self.chat_translation_enabled, self._on_translation_toggle_changed)
        self._add_sidebar_toggle(top, "名前も読み上げ", self.tts_include_name_var, None)
        self._add_sidebar_toggle(top, "音声翻訳", self.voice_var, self.toggle_voice)
        self._add_sidebar_slider(top, "読み上げ音量", self.tts_volume_var, 0, 100, "%")
        self._add_sidebar_slider(top, "読み上げ速度", self.tts_speed_var, 0.5, 2.0, "x")
        self._add_panel_divider(top)
        self._add_sidebar_section(top, "ワークスペース")
        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.pack(fill="x")
        nav.grid_columnconfigure((0, 1), weight=1, uniform="navigation")
        for index, panel_id in enumerate(("settings", "dictionary", "participants", "viewers", "commands", "plugins",
                                         "subtitle", "obs", "comment_tester")):
            btn = self._button(nav, PANEL_INFO[panel_id][0],
                               lambda selected=panel_id: self._toggle_right_panel(selected),
                               anchor="w", fg_color="transparent", width=80, height=32)
            btn.grid(row=index // 2, column=index % 2, sticky="ew", padx=1, pady=2)
            self.nav_buttons[panel_id] = btn
        self._add_panel_divider(top)
        self._button(top, "ログをテキスト出力", self.export_log_text).pack(fill="x", pady=(0, 6))

        # スクロール領域より外に置き、狭い画面でもコピー操作を残す。
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=14, pady=12)
        self._add_sidebar_section(bottom, "OBSに表示")
        self.obs_url_label = ctk.CTkLabel(bottom, text="表示URLを準備中…", font=self._font(10),
                                         text_color=p["TEXT_SUBTLE"], anchor="w", height=22)
        self.obs_url_label.pack(fill="x")
        self._button(bottom, "表示URLをコピー", self._copy_obs_url, primary=True).pack(fill="x", pady=(4, 4))
        self._button(bottom, "設定方法を見る  ↗", self._open_obs_setup_wiki,
                     fg_color="transparent", height=28).pack(fill="x")

    def _add_sidebar_section(self, parent: tk.Misc, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=self._font(11, "bold"),
                     text_color=self.ui_palette["TEXT_SUBTLE"], height=20).pack(anchor="w", pady=(0, 6))

    def _add_sidebar_toggle(self, parent: tk.Misc, label: str, variable: tk.Variable,
                            command: Callable | None) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        # テキスト自体もクリックできる広い操作領域にする。
        ctk.CTkSwitch(row, text=label, variable=variable, command=command,
                      font=self._font(12), switch_width=32, switch_height=18,
                      onvalue=True, offvalue=False).pack(anchor="w")

    def _add_sidebar_slider(self, parent: tk.Misc, label: str, variable: tk.Variable,
                            min_val: float, max_val: float, unit: str) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(6, 2))
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=label, font=self._font(11), height=20,
                     text_color=self.ui_palette["TEXT_SUBTLE"]).pack(side="left")
        def display(value: float) -> str:
            return f"{float(value):.1f}{unit}" if unit == "x" else f"{int(float(value))}{unit}"
        value_label = ctk.CTkLabel(header, text=display(variable.get()), font=self._font(11), height=20)
        value_label.pack(side="right")
        ctk.CTkSlider(frame, from_=min_val, to=max_val, variable=variable,
                      command=lambda value: value_label.configure(text=display(value)),
                      height=16).pack(fill="x", pady=(0, 3))

    def _build_main_content(self) -> None:
        p = self.ui_palette
        self.workspace = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.workspace.grid(row=0, column=1, sticky="nsew")
        heading = ctk.CTkFrame(self.workspace, fg_color="transparent")
        heading.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(heading, text="ライブチャット", font=self._font(20, "bold")).pack(side="left")
        self.header_stats_label = ctk.CTkLabel(heading, text="翻訳 0   ·   キャッシュ 0   ·   フィルター 0",
                                              font=self._font(11), text_color=p["TEXT_SUBTLE"])
        self.header_stats_label.pack(side="right")
        self.stats_label = self.header_stats_label
        self.main_paned = tk.PanedWindow(self.workspace, orient=tk.HORIZONTAL, sashwidth=10,
                                         sashrelief=tk.FLAT, bg=p["APP_BG"], bd=0)
        self.main_paned.pack(fill="both", expand=True)
        self.left_frame = self._surface(self.main_paned)
        self.event_frame = self._surface(self.main_paned)
        self._build_chat_log_area()
        self._build_event_log_area()
        self.main_paned.add(self.left_frame, minsize=360, stretch="always")
        self.main_paned.add(self.event_frame, minsize=210, width=252, stretch="never")
        self.participant_refresh_timer = None
        self.start_participant_auto_refresh()
        self.master.after(300, self._ensure_tts_started)
        self.master.after(1000, self._update_stats_display)

    def _build_chat_log_area(self) -> None:
        p = self.ui_palette
        self.comment_paned = tk.PanedWindow(self.left_frame, orient=tk.VERTICAL,
                                            sashwidth=8, bg=p["CARD_BG"], bd=0)
        self.comment_paned.pack(fill="both", expand=True, padx=10, pady=10)
        container = ctk.CTkFrame(self.comment_paned, fg_color=p["CARD_BG"])
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(4, 10))
        ctk.CTkLabel(header, text="コメント", font=self._font(14, "bold")).pack(side="left")
        self.comment_count_label = ctk.CTkLabel(header, text="0 件", font=self._font(11),
                                               text_color=p["TEXT_SUBTLE"])
        self.comment_count_label.pack(side="left", padx=10)
        self.follow_comments = tk.BooleanVar(value=True)
        ctk.CTkSwitch(header, text="自動スクロール", variable=self.follow_comments,
                      command=self._scroll_comment_tiles_to_edge, width=112, switch_width=28,
                      switch_height=16, font=self._font(10)).pack(side="right")
        self.comment_tile_frame = ctk.CTkScrollableFrame(container, fg_color=p["CARD_BG"],
                                                         height=400, corner_radius=0)
        self.comment_tile_frame.pack(fill="both", expand=True)
        self.comment_tiles = []
        self.comment_tile_limit = 120
        self._show_comment_empty_state()
        logs = ctk.CTkFrame(self.comment_paned, fg_color=p["CARD_BG"])
        log_header = ctk.CTkFrame(logs, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(6, 4))
        ctk.CTkLabel(log_header, text="システムログ", font=self._font(11, "bold"),
                     text_color=p["TEXT_SUBTLE"]).pack(side="left")
        self._button(log_header, "コピー", self._copy_log_to_clipboard, width=54, height=26).pack(side="right")
        self.log = ctk.CTkTextbox(logs, height=105, font=self._font(11), wrap="word")
        self._apply_log_style(self.log)
        self.log.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.log.insert("0.0", "ことつなの準備ができました。\n")
        self.log.configure(state="disabled")
        self.comment_paned.add(container, minsize=240, stretch="always")
        self.comment_paned.add(logs, minsize=95, height=135, stretch="never")
        self.log_history = deque(maxlen=self._log_history_limit)

    def _show_comment_empty_state(self) -> None:
        self.comment_empty = ctk.CTkFrame(self.comment_tile_frame, fg_color="transparent")
        self.comment_empty.pack(fill="x", pady=44, padx=12)
        ctk.CTkLabel(self.comment_empty, text="ことばが集まる場所", font=self._font(18, "bold"),
                     text_color=self.ui_palette["ACCENT"]).pack(pady=(0, 12))
        ctk.CTkLabel(self.comment_empty, text="Twitchに接続すると、コメントがここに届きます。\n原文も翻訳も、この画面で。",
                     font=self._font(12), text_color=self.ui_palette["TEXT_SUBTLE"],
                     wraplength=260, justify="center").pack()
        self._button(self.comment_empty, "チャンネルを設定  ›", lambda: self._toggle_right_panel("settings"),
                     width=180, border_width=1).pack(pady=(20, 0))

    def _build_event_log_area(self) -> None:
        header = ctk.CTkFrame(self.event_frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(header, text="アクティビティ", font=self._font(14, "bold")).pack(side="left")
        ctk.CTkLabel(self.event_frame, text="フォロー・サブスク・Bits", font=self._font(11),
                     text_color=self.ui_palette["TEXT_SUBTLE"], anchor="w").pack(fill="x", padx=16, pady=(0, 12))
        self.event_log = ctk.CTkTextbox(self.event_frame, width=180, height=150, wrap="word")
        self._apply_log_style(self.event_log)
        self.event_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.event_log.insert("0.0", "配信中のイベントがここに届きます。\n")
        self.event_log.configure(state="disabled")

    def _toggle_right_panel(self, panel_id: str) -> None:
        if self.active_panel == panel_id:
            self._close_right_panel()
            return
        builders = {
            "settings": self._build_settings_panel, "dictionary": self._build_dictionary_panel,
            "participants": self._build_participants_panel, "viewers": self._build_viewers_panel,
            "resources": self._build_resources_panel, "commands": self._build_commands_panel,
            "plugins": self._build_plugins_panel, "subtitle": self._build_subtitle_panel,
            "obs": self._build_obs_panel, "comment_tester": self._build_comment_tester_panel,
        }
        if panel_id not in builders:
            return
        # パネルは保持して切り替える。入力途中の値・スクロール位置・遅延更新先を失わない。
        if self.right_panel_frame:
            self.right_panel_frame.place_forget()
        if not hasattr(self, "_panel_cache"):
            self._panel_cache = {}
        self.active_panel = panel_id
        cached = panel_id in self._panel_cache
        if not cached:
            frame, content = self._create_inspector(panel_id)
            self.right_panel_frame, self.right_panel_content = frame, content
            builders[panel_id](content)
            self._panel_cache[panel_id] = (frame, content)
        self.right_panel_frame, self.right_panel_content = self._panel_cache[panel_id]
        # ログの幅と分割位置を変更せず、必要なときだけ手前に表示する。
        self.right_panel_frame.place(relx=1, rely=0, relheight=1, anchor="ne")
        self.right_panel_frame.lift()
        self._update_nav_button_states()
        if cached:
            # 入力欄は保持し、受信などで変わるリストだけ再取得する。
            refresh = {
                "participants": "_refresh_panel_participants", "viewers": "_refresh_viewers_panel",
                "commands": "_refresh_command_list", "plugins": "_refresh_plugin_list",
                "resources": "_update_resources_panel",
            }.get(panel_id)
            if refresh:
                getattr(self, refresh)()
        self._style_panel_buttons(self.right_panel_frame)

    def _style_panel_buttons(self, parent: tk.Misc) -> None:
        """既存パネルに残る固定色の操作も、明暗両テーマで読めるようにする。"""
        for widget in parent.winfo_children():
            if isinstance(widget, ctk.CTkButton):
                background = widget.cget("fg_color")
                if isinstance(background, str) and background.startswith("#"):
                    foreground = text_on(background)
                    widget.configure(text_color=foreground)
                    hover = widget.cget("hover_color")
                    if isinstance(hover, str) and hover.startswith("#") and contrast_ratio(foreground, hover) < 4.5:
                        widget.configure(hover_color=background)
            self._style_panel_buttons(widget)

    def _create_inspector(self, panel_id: str) -> tuple:
        title, description = PANEL_INFO[panel_id]
        frame = self._surface(self.workspace, width=410)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(header, text=title, font=self._font(19, "bold")).pack(side="left")
        close = self._button(header, "閉じる ×", self._close_right_panel, width=80, height=30)
        close.pack(side="right")
        ctk.CTkLabel(frame, text=description, text_color=self.ui_palette["TEXT_SUBTLE"],
                     font=self._font(11), anchor="w", wraplength=360).pack(fill="x", padx=18, pady=(0, 10))
        self._add_panel_divider(frame)
        content_type = ctk.CTkFrame if panel_id == "settings" else ctk.CTkScrollableFrame
        content = content_type(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        return frame, content

    def _dismiss_panel(self, event: tk.Event) -> None:
        # 子ダイアログ内の Escape で背後のワークスペースを操作しない。
        if event.widget.winfo_toplevel() == self.master:
            self._close_right_panel()

    def _close_right_panel(self) -> None:
        previous = self.active_panel
        if self.right_panel_frame:
            self.right_panel_frame.place_forget()
        self.right_panel_frame = None
        self.right_panel_content = None
        self.active_panel = None
        self._update_nav_button_states()
        if previous in self.nav_buttons:
            self.nav_buttons[previous].focus_set()

    def _update_nav_button_states(self) -> None:
        p = self.ui_palette
        for panel_id, button in self.nav_buttons.items():
            selected = panel_id == self.active_panel
            button.configure(fg_color=p["BORDER"] if selected else "transparent",
                             text_color=p["ACCENT"] if selected else p["TEXT_PRIMARY"],
                             text=f"{'● ' if selected else ''}{PANEL_INFO[panel_id][0]}")

    def _build_settings_pages(self, parent: tk.Misc) -> dict:
        tabs = ctk.CTkTabview(parent, fg_color="transparent", height=200,
                             corner_radius=8, anchor="w")
        tabs.pack(fill="both", expand=True)
        pages = {}
        for name in ("接続", "音声", "表示", "効果音", "管理"):
            tabs.add(name)
            page = ctk.CTkScrollableFrame(tabs.tab(name), fg_color="transparent")
            page.pack(fill="both", expand=True, pady=(8, 0))
            pages[name] = page
        return pages

    def _add_panel_section(self, parent: tk.Misc, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=self._font(13, "bold"),
                     text_color=self.ui_palette["TEXT_PRIMARY"]).pack(anchor="w", pady=(4, 10))

    def _add_panel_divider(self, parent: tk.Misc) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=self.ui_palette["BORDER"],
                     corner_radius=0).pack(fill="x", pady=12)
