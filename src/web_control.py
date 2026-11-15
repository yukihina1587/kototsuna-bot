"""GUIスレッドとWebサーバーをつなぐ、許可した操作だけの境界。"""

from concurrent.futures import Future
from copy import deepcopy
import math
from queue import Empty, Full, Queue
from threading import Lock


class ControlError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def validate_command(data: object) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("action"), str):
        raise ControlError("操作の形式が正しくありません。")
    action = data["action"]
    if action in ("start", "stop", "settings", "authenticate", "logout", "refresh_devices", "test_voice", "check_update", "install_update", "restart") and set(data) == {"action"}:
        return dict(data)
    if set(data) != {"action", "value"}:
        raise ControlError("操作の形式が正しくありません。")
    value = data["value"]
    if action == "save_settings":
        from src.web_settings import validate_settings
        return {"action": action, "value": validate_settings(value)}
    valid = False
    if action in ("translation", "include_name", "voice", "tts"):
        valid = type(value) is bool
    elif action in ("volume", "speed"):
        lower, upper = (0, 100) if action == "volume" else (0.5, 2.0)
        valid = type(value) in (int, float) and lower <= value <= upper and math.isfinite(value)
    elif action == "language":
        valid = isinstance(value, str) and value in ("自動", "英→日", "日→英")
    if not valid:
        raise ControlError("この操作や設定値は使用できません。")
    return dict(data)


class ControlBridge:
    """Web側はキューへ投入し、Tk側だけがdrainで実際の操作を行う。"""

    def __init__(self):
        self._lock = Lock()
        self._snapshot = {}
        self._commands = Queue(maxsize=16)
        self._closed = False

    def publish(self, snapshot: dict) -> None:
        with self._lock:
            self._snapshot = deepcopy(snapshot)

    def snapshot(self) -> dict:
        with self._lock:
            if self._closed:
                raise ControlError("ことつな本体が終了しました。", 503)
            return deepcopy(self._snapshot)

    def submit(self, data: object) -> Future:
        command = validate_command(data)
        future = Future()
        with self._lock:
            if self._closed:
                raise ControlError("ことつな本体が終了しました。", 503)
            try:
                self._commands.put_nowait((command, future))
            except Full:
                raise ControlError("操作が混み合っています。少し待ってください。", 429) from None
        return future

    def drain(self, handler, limit: int = 4) -> None:
        for _ in range(limit):
            try:
                command, future = self._commands.get_nowait()
            except Empty:
                break
            # HTTPがタイムアウトした未実行の操作を後から実行しない。
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = handler(command)
            except ControlError as exc:
                future.set_exception(exc)
            except Exception:
                # 任意の例外文字列に設定やトークンが含まれる可能性がある。
                future.set_exception(ControlError("操作できませんでした。本体の状態を確認してください。", 500))
            else:
                future.set_result(result)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            while True:
                try:
                    _, future = self._commands.get_nowait()
                except Empty:
                    break
                future.cancel()
