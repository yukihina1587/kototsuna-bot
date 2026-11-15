"""既存デスクトップの操作・状態をWeb画面へ渡す段階移行用アダプター。"""

import webbrowser

from src import __version__
from src.web_control import ControlBridge, ControlError
from src.web_ui import WebUIServer


class DesktopWebUI:
    def __init__(self, app):
        self.app = app
        self.bridge = ControlBridge()
        self.server = WebUIServer(self.bridge)
        self._timer = None
        self._closed = False

    def start(self):
        self.bridge.publish(self.snapshot())
        self.server.start()
        self._tick()

    def open(self):
        return webbrowser.open(self.server.launch_url())

    def close(self):
        self._closed = True
        if self._timer is not None:
            self.app.master.after_cancel(self._timer)
            self._timer = None
        self.server.close()

    def _tick(self):
        if self._closed:
            return
        try:
            self.bridge.drain(self.execute)
            self.bridge.publish(self.snapshot())
        finally:
            if not self._closed:
                self._timer = self.app.master.after(250, self._tick)

    def snapshot(self):
        app = self.app
        bot = app.bot_instance
        requested = bool(getattr(app, "_bot_requested_running", False))
        if getattr(app, "_bot_last_failed", False):
            connection = "error"
        elif requested or bot is not None:
            # TwitchIO 2系のreadyイベントは切断時にclearされる。
            link = getattr(bot, "_connection", None)
            ready = getattr(link, "is_ready", None)
            connection = "connected" if ready is not None and ready.is_set() else "connecting"
        else:
            connection = "stopped" if app.token else "needs_auth"
        comments = [
            {key: str(item.get(key) or "")[:4000] for key in ("id", "name", "message", "translated", "time")}
            for item in list(app.chat_history)[-100:]
        ]
        voice = getattr(app, "voice_translator", None)
        result = {
            "version": __version__, "channel": app.channel.get(),
            "authenticated": bool(app.token), "connection": connection,
            "can_stop": bot is not None,
            "translation_enabled": bool(app.chat_translation_enabled.get()),
            "language_mode": app.lang_mode.get(),
            "include_name": bool(app.tts_include_name_var.get()),
            "tts_volume": app.tts_volume_var.get(), "tts_speed": app.tts_speed_var.get(),
            "tts_active": bool(app.tts.enabled), "voice_active": bool(app.voice_var.get()),
            "tts_speaking": bool(getattr(app.tts, "speaking", False)),
            "mic_level": getattr(voice, "input_level", 0.0),
            "voice_processing": bool(getattr(voice, "processing", False)) and bool(app.voice_var.get()),
            "overlay_url": app._current_chat_overlay_url(),
            "comments": comments,
        }

        if hasattr(app, "web_snapshot"):
            result.update(app.web_snapshot())
        return result

    def execute(self, command):
        app = self.app
        action = command["action"]
        value = command.get("value")
        if action == "start":
            if app.bot_instance is not None or getattr(app, "_bot_requested_running", False):
                raise ControlError("BOTは起動中です。接続状態を確認してください。", 409)
            app.start_bot(web_request=True)
        elif action == "stop":
            if app.bot_instance is None and getattr(app, "_bot_requested_running", False):
                raise ControlError("起動を準備しています。少し待ってから停止してください。", 409)
            app.stop_bot()
        elif hasattr(app, "handle_web_action") and action not in ("translation", "include_name", "volume", "speed", "language"):
            app.handle_web_action(action, value)
        elif action == "settings":
            app.master.deiconify()
            app.master.lift()
            if app.active_panel != "settings":
                app._toggle_right_panel("settings")
        elif action == "translation":
            app.chat_translation_enabled.set(value)
            app._on_translation_toggle_changed()
        else:
            variables = {
                "language": app.lang_mode, "include_name": app.tts_include_name_var,
                "volume": app.tts_volume_var, "speed": app.tts_speed_var,
            }
            variables[action].set(value)
        state = self.snapshot()
        self.bridge.publish(state)
        return state
