"""単一Web画面用の処理エンジン。移行期間中は既存のTk状態管理を非表示で再利用。"""

from copy import deepcopy
from queue import Empty, Queue
from threading import Thread
import sys
import secrets
import webbrowser

from src import __version__
from src.auth import (build_auth_url, check_missing_scopes, get_effective_client_id,
                      run_auth_server_and_get_token, validate_token_with_info)
from src.config import save_config
from src.desktop_web_ui import DesktopWebUI
from src.desktop_window import DesktopWindow
from src.gui import KototsunaApp
from src.web_control import ControlError
from src.web_settings import VARIABLES, settings_snapshot, validate_settings


class WebDesktopApp(KototsunaApp):
    def __init__(self, *args, **kwargs):
        self._web_events = Queue()
        self._web_jobs = set()
        self._web_closed = False
        self._web_notice = "設定からTwitchに接続してください。"
        self._web_devices = {"microphones": [], "voices": []}
        self._web_update = {"status": "idle", "message": "", "version": ""}
        self._web_release = None
        self._desktop_window = None
        super().__init__(*args, **kwargs)
        self._event_timer = self.master.after(100, self._drain_web_events)

    def open_desktop_window(self, on_closed):
        self._web_ui = DesktopWebUI(self)
        self._web_ui.start()

        def failed():
            from tkinter import messagebox
            messagebox.showerror(
                "画面を開けませんでした",
                "WebView2 Runtimeとアプリの依存関係を確認してください。\n"
                "復旧用の従来画面は --legacy-ui で起動できます。", parent=self.master,
            )
            on_closed()

        self._desktop_window = DesktopWindow(
            self.master, self._web_ui.server.launch_url(), on_closed, failed,
        )

    def _drain_web_events(self):
        if self._web_closed:
            return
        try:
            for _ in range(16):
                callback, value = self._web_events.get_nowait()
                callback(value)
        except Empty:
            pass
        finally:
            if not self._web_closed:
                self._event_timer = self.master.after(100, self._drain_web_events)

    def _job(self, name, work, done):
        if name in self._web_jobs:
            raise ControlError("処理中です。完了までお待ちください。", 409)
        self._web_jobs.add(name)

        def complete(result):
            self._web_jobs.discard(name)
            ok, value = result
            if ok:
                done(value)
            else:
                self._web_notice = "処理できませんでした。接続先や設定を確認して再試行してください。"
                if name == "update":
                    self._web_update = {"status": "error", "message": self._web_notice, "version": ""}

        def run():
            try:
                result = (True, work())
            except Exception:
                result = (False, None)  # 任意の例外や認証情報を画面へ返さない
            if not self._web_closed:
                self._web_events.put((complete, result))

        Thread(target=run, name=f"kototsuna-{name}", daemon=True).start()

    def web_snapshot(self):
        return {"desktop": True, "settings": settings_snapshot(self),
                "notice": self._web_notice, "jobs": sorted(self._web_jobs),
                "devices": self._web_devices, "update": dict(self._web_update),
                "auth_username": self.auth_username.get()}

    def _set_status(self, text, tone="info"):
        self._web_notice = text
        super()._set_status(text, tone)

    def _maybe_show_telemetry_consent(self):
        # 同意は設定の明示的なスイッチで受け付ける。初期値は送信しない。
        pass

    def _on_sentry_event_captured(self, event_id):
        self._web_notice = "クラッシュレポートを記録しました。"

    def _check_saved_token(self):
        token = self.config.get("twitch_access_token", "")
        if token and "auth" not in self._web_jobs:
            self._web_notice = "保存されたTwitch認証を確認しています…"
            self._job("auth", lambda: (token, validate_token_with_info(token)), self._finish_auth)

    def _finish_auth(self, result):
        token, info = result
        if isinstance(info, dict) and not check_missing_scopes(info.get("scopes", [])):
            self.token = token
            self.auth_username.set(info.get("login", ""))
            self.config["twitch_access_token"] = token
            if self.channel_mode.get() == "auto":
                self.channel.set(self.auth_username.get())
            save_config(self.config)
            self._update_auth_button_states(True)
            self._web_notice = "Twitchに接続しました。BOTを開始できます。"
        else:
            self.token = None
            self._update_auth_button_states(False)
            self._web_notice = "認証を確認できませんでした。ネット接続を確認し、Twitchに接続し直してください。"
            if info is None:
                self.config["twitch_access_token"] = ""
                save_config(self.config)

    def _authenticate(self):
        client_id = get_effective_client_id(self.client_id.get())
        if not client_id:
            raise ControlError("接続設定にTwitch Client IDを入力して保存してください。")
        if self.bot_instance is not None or getattr(self, "_bot_requested_running", False):
            raise ControlError("認証を変更する前にBOTを停止してください。", 409)
        self._web_notice = "ブラウザでTwitchの認証を完了してください。"

        def authenticate():
            nonce = secrets.token_urlsafe(24)
            token = run_auth_server_and_get_token(
                on_ready=lambda: webbrowser.open(build_auth_url(client_id, state=nonce)),
                expected_state=nonce,
            )
            return token, validate_token_with_info(token) if token else None

        self._job("auth", authenticate, self._finish_auth)

    def _save_web_settings(self, values):
        patch = validate_settings(values)
        if ({"channel_name", "channel_mode", "twitch_client_id"} & patch.keys()
                and (self.bot_instance is not None or getattr(self, "_bot_requested_running", False))):
            raise ControlError("接続先を変更する前にBOTを停止してください。", 409)
        if "mic_device_index" in patch and self.voice_var.get():
            raise ControlError("マイクを変更する前にマイク翻訳をOFFにしてください。", 409)
        if "tts" in self._web_jobs:
            raise ControlError("音声設定を反映中です。少し待ってください。", 409)
        previous = deepcopy(self.config)
        previous_vars = {name: getattr(self, name).get() for name in set(VARIABLES.values())}
        self._web_settings_batch = True
        try:
            for key, value in patch.items():
                if key in VARIABLES:
                    getattr(self, VARIABLES[key]).set("オフ" if key == "translate_mode_2" and not value else value)
            self.config.update({key: value for key, value in patch.items() if key != "tts_engine_url"})
            if "tts_engine_url" in patch:
                urls = dict(self.config.get("tts_engine_urls", {}))
                urls[self.tts_engine_var.get()] = patch["tts_engine_url"]
                self.config["tts_engine_urls"] = urls
            if self.channel_mode.get() == "auto" and self.auth_username.get():
                self.channel.set(self.auth_username.get())
            if "telemetry_crash_reporting" in patch:
                self.config["telemetry_consent_asked"] = True
        finally:
            self._web_settings_batch = False
        if not self._auto_save_settings():
            self._web_settings_batch = True
            try:
                self.config = previous
                for name, value in previous_vars.items():
                    getattr(self, name).set(value)
            finally:
                self._web_settings_batch = False
            raise ControlError("設定ファイルを保存できませんでした。保存先の権限を確認してください。", 500)
        if "mic_device_index" in patch:
            self.voice_translator.device_index = patch["mic_device_index"]
            self.voice_translator.mic = None
        if {"tts_engine", "tts_engine_url", "voicevox_speaker_id", "edge_tts_voice"} & patch.keys():
            engine = self.config["tts_engine"]
            url = self.config.get("tts_engine_urls", {}).get(engine) or None
            voice = self.config.get("edge_tts_voice") if engine == "edge-tts" else self.config.get("voicevox_speaker_id", 14)
            self._web_devices["voices"] = []
            def apply_tts():
                self.tts.switch_engine(engine, url)
                self.tts.set_speaker(voice)
            self._job("tts", apply_tts, lambda _: self._set_status("音声設定を反映しました。"))
        if any(key.startswith("subtitle_") for key in patch):
            self._init_subtitle_overlay()
        if any(key.startswith("comment_") for key in patch):
            self._export_chat_html(force=True)
        if any(key.startswith("obs_") for key in patch) and self.obs_controller is not None:
            self.obs_controller.stop()
            if self.config.get("obs_enabled") and not self.safe_mode:
                self.obs_controller.start()
        if "log_level" in patch:
            from src.logger import set_log_level
            set_log_level(patch["log_level"])
        if "telemetry_crash_reporting" in patch:
            self._web_notice = "保存しました。クラッシュレポートの設定は次回起動時に反映されます。"
        else:
            self._web_notice = "設定を保存しました。"

    def _refresh_web_devices(self):
        from src.voice_listener import VoiceTranslator
        def fetch():
            return {"microphones": VoiceTranslator.get_microphone_devices(),
                    "voices": self.tts.get_speakers_list() or []}
        self._job("devices", fetch, lambda devices: setattr(self, "_web_devices", devices))

    def _do_update_check(self, is_manual):
        # 親の起動時チェックはワーカースレッドから呼ばれるためキュー経由で開始する。
        self._web_events.put((lambda _: self._check_web_update(), None))

    def _check_web_update(self):
        from src.updater import check_for_updates
        if "update" in self._web_jobs:
            return
        preview = self.include_prerelease.get()
        self._web_update = {"status": "checking", "message": "更新を確認しています…", "version": ""}
        def complete(release):
            self._web_release = release
            self._web_update = {"status": "available" if release else "current",
                                "message": "新しいバージョンがあります。" if release else "最新バージョンです。",
                                "version": release.version if release else ""}
        self._job("update", lambda: check_for_updates(__version__, include_prerelease=preview), complete)

    def _install_web_update(self):
        from src.updater import apply_update, download_update, save_rollback_info
        if not getattr(sys, "frozen", False):
            raise ControlError("ソース実行中です。自動更新は配布版で利用できます。")
        if not self._web_release:
            raise ControlError("先に更新を確認してください。")
        release = self._web_release
        self._web_update["status"] = "downloading"
        self._web_update["message"] = "更新をダウンロードしています…"
        def download():
            save_rollback_info(__version__)
            apply_update(download_update(release))
        def complete(_):
            self._web_update.update(status="ready", message="更新の準備ができました。再起動して適用できます。")
        self._job("update", download, complete)

    def handle_web_action(self, action, value):
        if action == "save_settings":
            self._save_web_settings(value)
        elif action == "authenticate":
            self._authenticate()
        elif action == "logout":
            if "auth" in self._web_jobs or self.bot_instance or getattr(self, "_bot_requested_running", False):
                raise ControlError("BOTと認証処理が終了してからログアウトしてください。", 409)
            self.token = None
            self.auth_username.set("")
            self.config["twitch_access_token"] = ""
            save_config(self.config)
            self._update_auth_button_states(False)
            self._web_notice = "ログアウトしました。"
        elif action == "voice":
            self.voice_var.set(value)
            self.toggle_voice()
            if value and not self.voice_var.get():
                raise ControlError("マイク翻訳を開始できません。マイクと音声・翻訳モデルを確認してください。")
        elif action == "tts":
            if value:
                self.tts.enabled = True
                self._ensure_tts_started()
            else:
                self.tts.enabled = False
        elif action == "refresh_devices":
            self._refresh_web_devices()
        elif action == "test_voice":
            self._ensure_tts_started()
            self.tts.test_voice()
        elif action == "check_update":
            self._check_web_update()
        elif action == "install_update":
            self._install_web_update()
        elif action == "restart":
            if self._web_update["status"] != "ready":
                raise ControlError("更新の準備が完了していません。")
            from src.updater import restart_app
            def restart():
                self.cleanup_resources()
                restart_app()
            self.master.after(300, restart)
        elif action != "settings":
            raise ControlError("この操作は使用できません。")

    def cleanup_resources(self):
        if self._web_closed:
            return
        self._web_closed = True
        if getattr(self, "_event_timer", None):
            self.master.after_cancel(self._event_timer)
        try:
            if self._desktop_window:
                self._desktop_window.close()
        finally:
            try:
                self.tts.stop()
            finally:
                super().cleanup_resources()
