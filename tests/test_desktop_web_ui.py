"""Tk・Twitch・音声に接続しないアダプターの検証。"""

from collections import deque
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.desktop_web_ui import DesktopWebUI
from src.web_control import ControlError


class Variable:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


@pytest.fixture
def adapter():
    app = SimpleNamespace(
        bot_instance=None, token=None, channel=Variable("test_channel"),
        chat_translation_enabled=Variable(False), lang_mode=Variable("自動"),
        tts_include_name_var=Variable(False), tts_volume_var=Variable(80),
        tts_speed_var=Variable(1), tts=SimpleNamespace(enabled=False), voice_var=Variable(False),
        _current_chat_overlay_url=lambda: "http://localhost:8080/chat", chat_history=deque(),
        master=Mock(), active_panel=None, _toggle_right_panel=Mock(),
        start_bot=Mock(), stop_bot=Mock(), _on_translation_toggle_changed=Mock(),
        config={"private_setting": "never expose config"},
    )
    return DesktopWebUI(app)


def test_snapshot_exposes_only_public_fields_and_bounds_comments(adapter):
    adapter.app.token = "not-a-real-credential"
    for index in range(120):
        adapter.app.chat_history.append({"id": str(index), "name": "sample", "message": "x" * 5000,
                                         "translated": None, "raw": {"private": "excluded"}})
    state = adapter.snapshot()
    assert state["authenticated"] is True
    assert len(state["comments"]) == 100
    assert state["comments"][0]["id"] == "20"
    assert len(state["comments"][0]["message"]) == 4000
    assert state["comments"][0]["translated"] == ""
    assert "not-a-real-credential" not in str(state)
    assert "private" not in str(state)
    assert "token" not in state and "config" not in state


def test_connection_states_follow_ready_and_disconnect(adapter):
    assert adapter.snapshot()["connection"] == "needs_auth"
    adapter.app.token = "not-a-real-credential"
    assert adapter.snapshot()["connection"] == "stopped"
    adapter.app._bot_requested_running = True
    assert adapter.snapshot()["connection"] == "connecting"
    ready = Event()
    adapter.app.bot_instance = SimpleNamespace(_connection=SimpleNamespace(is_ready=ready))
    ready.set()
    assert adapter.snapshot()["connection"] == "connected"
    ready.clear()
    assert adapter.snapshot()["connection"] == "connecting"
    adapter.app._bot_last_failed = True
    assert adapter.snapshot()["connection"] == "error"


def test_audio_state_is_derived_from_engine_and_stops_when_mic_is_off(adapter):
    adapter.app.voice_translator = SimpleNamespace(input_level=42.0, processing=True)
    adapter.app.tts.speaking = True
    adapter.app.voice_var.set(True)
    state = adapter.snapshot()
    assert state["mic_level"] == 42.0 and state["voice_processing"]
    assert state["tts_speaking"]
    adapter.app.voice_var.set(False)
    assert not adapter.snapshot()["voice_processing"]


@pytest.mark.parametrize("action,value,variable", [
    ("volume", 23, "tts_volume_var"), ("speed", 1.4, "tts_speed_var"),
    ("include_name", True, "tts_include_name_var"), ("language", "日→英", "lang_mode"),
    ("translation", True, "chat_translation_enabled"),
])
def test_actions_update_shared_variables_and_publish(adapter, action, value, variable):
    future = adapter.bridge.submit({"action": action, "value": value})
    assert not future.done()
    adapter.bridge.drain(adapter.execute)
    assert getattr(adapter.app, variable).get() == value
    assert future.result() == adapter.bridge.snapshot()
    if action == "translation":
        adapter.app._on_translation_toggle_changed.assert_called_once()


def test_start_does_not_launch_a_second_bot(adapter):
    def started(**kwargs):
        adapter.app._bot_requested_running = True
    adapter.app.start_bot.side_effect = started
    adapter.execute({"action": "start"})
    adapter.app.start_bot.assert_called_once_with(web_request=True)
    with pytest.raises(ControlError):
        adapter.execute({"action": "start"})
    adapter.app.start_bot.assert_called_once()


def test_stop_and_settings_use_existing_controls(adapter):
    adapter.execute({"action": "stop"})
    adapter.app.stop_bot.assert_called_once()
    adapter.execute({"action": "settings"})
    adapter.app._toggle_right_panel.assert_called_once_with("settings")
    adapter.app.master.deiconify.assert_called_once()


def test_stop_while_instance_is_not_created_returns_retry_message(adapter):
    adapter.app._bot_requested_running = True
    with pytest.raises(ControlError):
        adapter.execute({"action": "stop"})
    adapter.app.stop_bot.assert_not_called()


def test_refresh_uses_desktop_changes_and_close_cancels_timer(adapter):
    adapter.app.tts_volume_var.set(42)
    adapter._tick()
    assert adapter.bridge.snapshot()["tts_volume"] == 42
    adapter.app.master.after.assert_called_once_with(250, adapter._tick)
    adapter.close()
    adapter.app.master.after_cancel.assert_called_once()
    adapter.app.stop_bot.assert_not_called()
