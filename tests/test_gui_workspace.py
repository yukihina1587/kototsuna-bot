"""実ウィジェットの回帰テスト（KOTOTSUNA_GUI_TESTS=1 とディスプレイが必要）。

接続・設定保存・音声・モデル・サーバーは差し替え、ユーザー環境を操作しない。
"""

import os
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("KOTOTSUNA_GUI_TESTS") != "1",
    reason="実画面のテストは KOTOTSUNA_GUI_TESTS=1 で明示的に実行",
)


@pytest.fixture(scope="module")
def tk_root():
    ctk = pytest.importorskip("customtkinter")
    # 実アプリと同じくTkインタープリタは1つだけ使用する。
    # Windowsでは同一プロセス内での生成・破棄の反復がTkの初期化を不安定にする。
    root = ctk.CTk()
    yield root
    root.destroy()


@pytest.fixture(params=["default", "minimal", "gradient", "cyberpunk"])
def app(request, monkeypatch, tmp_path, tk_root):
    pygame = pytest.importorskip("pygame")
    monkeypatch.setattr(pygame.mixer, "init", Mock())
    from src import gui
    from src.config import DEFAULT_CONFIG

    config = {**deepcopy(DEFAULT_CONFIG), "ui_theme": request.param,
              "telemetry_consent_asked": True, "voicevox_auto_start": False,
              "chat_html_path": str(tmp_path / "chat.html")}
    monkeypatch.setattr(gui, "load_config", lambda: deepcopy(config))
    for name in ("save_config", "init_translation_dictionary", "run_server_thread",
                 "register_post_capture_callback"):
        monkeypatch.setattr(gui, name, Mock())
    for name in ("get_tracker", "VoiceTranslator", "get_tts_instance", "get_voicevox_manager", "get_monitor"):
        monkeypatch.setattr(gui, name, Mock(return_value=Mock()))
    tracker = Mock(keywords=[], enabled=True)
    tracker.get_participants.return_value = []
    monkeypatch.setattr(gui, "get_tracker", lambda **_kwargs: tracker)
    dictionary = Mock()
    dictionary.get_all_entries.return_value = []
    monkeypatch.setattr(gui, "get_dictionary", lambda: dictionary)
    viewers = Mock(_viewers={}, _lock=threading.RLock())
    viewers.get_viewers_with_voice.return_value = []
    monkeypatch.setattr(gui, "get_viewer_store", lambda: viewers)
    commands = Mock()
    commands.list_all.return_value = []
    monkeypatch.setattr(gui, "CommandStore", lambda: commands)
    from src import plugin_manager
    monkeypatch.setattr(plugin_manager, "get_plugin_manager", lambda: Mock(plugins=[]))
    monkeypatch.setattr(plugin_manager, "get_plugins_dir", lambda: tmp_path / "plugins")
    monkeypatch.setattr(gui, "get_rollback_info", lambda: None)
    for name in ("_export_chat_html", "_setup_window_icon", "_init_subtitle_overlay", "_init_chat_html",
                 "_check_saved_token", "_init_obs_controller", "_maybe_show_telemetry_consent",
                 "_check_for_updates_on_startup",
                 "_ensure_tts_started", "start_participant_auto_refresh", "_refresh_mic_list",
                 "start_auth", "start_bot", "stop_bot", "disconnect_all"):
        monkeypatch.setattr(gui.KototsunaApp, name, Mock())
    root = tk_root
    root.report_callback_exception = Mock()
    instance = gui.KototsunaApp(root, safe_mode=False)
    root.title("ことつな！ デザイン確認（未接続）")
    root.geometry("1200x800+30+30")
    root.update()
    yield instance
    errors = root.report_callback_exception.call_args_list
    for timer in root.tk.call("after", "info"):
        root.tk.call("after", "cancel", timer)
    for child in list(root.winfo_children()):
        child.destroy()
    assert not errors, errors


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def sample_comment(message="今日はどんな配信ですか？", translated="What are we streaming today?", **kwargs):
    from src.comment_data import CommentData, Platform
    return CommentData(username="demo_viewer", display_name="はる", message=message,
                       platform=Platform.TWITCH, translated=translated, color="#91D5B3", **kwargs)


def test_minimum_window_keeps_controls_and_logs_visible(app):
    app.master.geometry("1000x700")
    app.master.update()
    for widget in (app.auth_btn, app.start_stop_btn, app.disconnect_btn, app.obs_url_label,
                   app.comment_tile_frame, app.event_log):
        assert widget.winfo_ismapped()
        assert widget.winfo_rootx() + widget.winfo_width() <= app.master.winfo_rootx() + app.master.winfo_width()
        assert widget.winfo_rooty() + widget.winfo_height() <= app.master.winfo_rooty() + app.master.winfo_height()
    assert app.comment_tile_frame.winfo_width() >= 300

    app.master.geometry("1200x800")
    app.master.update()
    for button in app.nav_buttons.values():
        assert button.winfo_rooty() + button.winfo_height() < app.obs_url_label.winfo_rooty()


def test_settings_can_close_and_reopen_without_losing_drafts_or_log_width(app):
    before = app.main_paned.sash_coord(0)
    app._toggle_right_panel("settings")
    app.master.update()
    panel = app.right_panel_frame
    app.channel.set("preview_channel")
    assert app.main_paned.sash_coord(0) == before
    app._close_right_panel()
    app._toggle_right_panel("settings")
    app.master.update()
    assert app.right_panel_frame is panel
    assert app.channel_entry.get() == "preview_channel"
    assert app.translate_mode_2_menu.cget("state") == "disabled"
    app.chat_translation_post_to_twitch.set(True)
    app._on_chat_translation_post_changed()
    assert app.translate_mode_2_menu.cget("state") == "normal"
    assert not app.chat_translation_enabled.get()


def test_comment_wrap_resize_order_and_history_limit(app):
    app.comment_tile_limit = 3
    app._add_comment_tile(sample_comment(message="長いコメントも読みやすく折り返して表示します。" * 12))
    app.master.update()
    assert app.comment_empty is None
    initial_height = app.comment_tiles[0].winfo_height()
    app.master.geometry("1000x700")
    app.master.update()
    assert app.comment_tiles[0].winfo_height() >= initial_height
    for index in range(4):
        app._add_comment_tile(sample_comment(message=f"コメント {index}"))
    app.master.update()
    assert len(app.comment_tiles) == 3
    app.chat_html_newest_first.set(True)
    app._sync_comment_tile_order()
    app.master.update()
    assert app.comment_tiles[-1].winfo_y() < app.comment_tiles[0].winfo_y()
    assert app.comment_count_label.cget("text") == "3 件"


def test_emote_fallback_keeps_wrapped_lines_visible(app):
    import tkinter as tk
    message = "とても長いコメントです。" * 12 + " Kappa"
    start = message.index("Kappa")
    app._get_emote_tk_image = lambda _emote: None
    app._add_comment_tile(sample_comment(message=message, emotes=[{"start": start, "end": start + 4}]))
    app.master.update()
    text = next(w for w in descendants(app.comment_tiles[0]) if isinstance(w, tk.Text))
    assert text.get("1.0", "end-1c") == message
    assert int(text.cget("height")) > 1


def test_all_panels_open_and_refresh_without_callback_errors(app, caplog):
    for panel_id in app.nav_buttons:
        app._toggle_right_panel(panel_id)
        app.master.update()
        assert app.active_panel == panel_id
        assert app.right_panel_frame.winfo_ismapped()
        app._close_right_panel()
        app._toggle_right_panel(panel_id)
        app.master.update()
        app._close_right_panel()
    assert not [record.message for record in caplog.records if record.levelno >= 40]


def test_short_translation_does_not_expand_card_to_frame_default_height(app):
    app._add_comment_tile(sample_comment())
    app.master.update()
    assert app.comment_tiles[0].winfo_height() < 180


def test_pausing_follow_keeps_manual_scroll(app):
    app.follow_comments.set(False)
    canvas = Mock()
    app.comment_tile_frame = Mock(_parent_canvas=canvas)
    app._scroll_comment_tiles_to_edge()
    app.comment_tile_frame.after.assert_not_called()


def test_header_actions_keep_original_callbacks(app):
    app.auth_btn.configure(state="normal")
    app.start_stop_btn.configure(state="normal")
    app.disconnect_btn.configure(state="normal")
    app.auth_btn.invoke()
    app.start_stop_btn.invoke()
    app.disconnect_btn.invoke()
    app.start_auth.assert_called_once()
    app.start_bot.assert_called_once()
    app.disconnect_all.assert_called_once()


def test_theme_changes_recolor_existing_widgets_and_keep_session(app):
    import customtkinter as ctk
    import tkinter as tk
    from src import gui
    from src.gui_theme import contrast_ratio

    app._toggle_right_panel("dictionary")
    hidden_panel = app.right_panel_frame
    app._toggle_right_panel("settings")
    panel = app.right_panel_frame
    app.channel.set("unsaved_channel")
    app.follow_comments.set(False)
    app._get_emote_tk_image = lambda _emote: None
    app._add_comment_tile(sample_comment(message="Kappa", emotes=[{"start": 0, "end": 4}]))
    tile = app.comment_tiles[0]
    emote_text = next(w for w in descendants(tile) if isinstance(w, tk.Text))
    app.event_log.configure(state="normal")
    app.event_log.insert("end", "keep this event\n")
    app.event_log.configure(state="disabled")
    app.master.update()
    sash = app.main_paned.sash_coord(0)
    session = object()
    app.bot_instance = session
    app._update_header_bot_button(True)
    button = app.start_stop_btn
    tabs = next(w for w in descendants(panel) if isinstance(w, ctk.CTkTabview))
    tabs.set("表示")

    for key in ("minimal", "gradient", "cyberpunk", "default", "minimal"):
        app.ui_theme_menu._dropdown_callback(gui.THEMES[key]["name"])
        app.master.update()
        palette = gui.THEMES[key]
        assert app.main_frame.cget("fg_color") == palette["APP_BG"]
        assert app.left_frame.cget("fg_color") == palette["CARD_BG"]
        assert app.comment_tile_frame.cget("fg_color") == palette["CARD_BG"]
        assert app.main_paned.cget("background") == palette["APP_BG"]
        assert tile.cget("fg_color") == palette["PANEL_BG"]
        assert emote_text.cget("background") == palette["PANEL_BG"]
        name = next(w for w in descendants(tile) if isinstance(w, ctk.CTkLabel) and w.cget("text").startswith("はる"))
        assert contrast_ratio(name.cget("text_color"), palette["PANEL_BG"]) >= 4.5
        assert hidden_panel.cget("fg_color") == palette["CARD_BG"]
        assert app.ui_theme_menu.cget("dropdown_fg_color") == palette["PANEL_BG"]
        assert tabs._segmented_button.cget("selected_color") == palette["BORDER"]
        assert app.config["ui_theme"] == key
        assert app.right_panel_frame is panel
        assert app.start_stop_btn is button
        assert app.bot_instance is session
        assert button.cget("text") == "■ BOT停止"
        assert button.cget("fg_color") == "#EF4444"
        assert app.channel_entry.get() == "unsaved_channel"
        assert tabs.get() == "表示"
        assert app.main_paned.sash_coord(0) == sash
        assert "keep this event" in app.event_log.get("1.0", "end")
        assert emote_text.get("1.0", "end-1c") == "Kappa"
        assert not app.follow_comments.get()
    app.start_bot.assert_not_called()
    app.stop_bot.assert_not_called()


def test_custom_theme_reloads_and_preserves_explicit_log_colors(app, monkeypatch):
    from src import gui

    app._toggle_right_panel("settings")
    app.comment_bg.set("#123456")
    app.comment_fg.set("#FEDCBA")
    custom = {**gui.THEMES["minimal"], "name": "カスタム検証", "APP_BG": "#ECE0D0",
              "CARD_BG": "#ECE0D0", "PANEL_BG": "#ECE0D0"}
    monkeypatch.setitem(gui.THEMES, "custom_test", custom)
    for color in ("#ECE0D0", "#D0E0EC"):
        custom["APP_BG"] = color
        app._on_theme_changed(custom["name"])
        app.master.update()
        assert app.main_frame.cget("fg_color") == color
        assert app.log.cget("fg_color") == "#123456"
        assert app.log.cget("text_color") == "#FEDCBA"
    app._on_theme_changed(gui.THEMES["default"]["name"])
    assert app.left_frame.cget("fg_color") == gui.THEMES["default"]["CARD_BG"]
    assert app.ui_palette == gui.THEMES["default"]


def test_saving_theme_in_editor_applies_loaded_palette_immediately(app, monkeypatch, tmp_path):
    import json
    from src import gui, theme_editor, theme_loader

    app._toggle_right_panel("settings")
    custom_file = tmp_path / "saved_theme.json"
    custom_file.write_text(json.dumps({"base": "minimal", "name": "保存したテーマ", "APP_BG": "#F8E8D8"}))
    monkeypatch.setattr(theme_loader, "get_themes_dir", lambda: str(tmp_path))
    monkeypatch.setattr(gui, "THEMES", deepcopy(gui.THEMES))
    dialog = Mock()
    monkeypatch.setattr(theme_editor, "ThemeEditorDialog", dialog)
    app._open_theme_editor()
    dialog.call_args.kwargs["on_saved"]("saved_theme")
    app.master.update()
    assert app.config["ui_theme"] == "saved_theme"
    assert app.main_frame.cget("fg_color") == "#F8E8D8"
    assert app.ui_theme_var.get() == "保存したテーマ"


def test_capture_preview(app):
    directory = os.environ.get("KOTOTSUNA_SCREENSHOT_DIR")
    if not directory or app.config["ui_theme"] not in ("default", "minimal"):
        return
    from gui_capture import capture_window

    app._add_comment_tile(sample_comment())
    app._add_comment_tile(sample_comment("Hello from the other side of the world!", "世界の反対側から、こんにちは！"))
    app._add_comment_tile(sample_comment("ことばが違っても、一緒に楽しめるのがいいね。", "I love that we can enjoy this together, whatever language we speak."))
    app.master.update()
    app.master.lift()
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)

    def capture(suffix):
        capture_window(app.master).save(path / f"{app.config['ui_theme']}{suffix}.png")

    capture("")
    app._toggle_right_panel("settings")
    capture("-settings")
