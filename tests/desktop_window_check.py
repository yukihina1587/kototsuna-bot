"""Windows実機でWebView起動・画面閉鎖・親からの終了を検証。実アカウント/音声は使用しない。"""
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import tkinter as tk

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.desktop_window import DesktopWindow
from src.web_control import ControlBridge
from src.web_ui import WebUIServer


def owned_windows(pid):
    pids = {pid, *(p.pid for p in psutil.Process(pid).children(recursive=True))}
    result = []
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    @callback_type
    def visit(hwnd, _):
        process_id = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value in pids and user.IsWindowVisible(hwnd):
            result.append(hwnd)
        return True
    user.EnumWindows(visit, 0)
    return result


def main():
    bridge = ControlBridge()
    bridge.publish(dict(version="test", channel="", authenticated=False, connection="needs_auth",
                        can_stop=False, translation_enabled=False, language_mode="自動", include_name=False,
                        tts_volume=80, tts_speed=1, tts_active=False, voice_active=False,
                        overlay_url="http://localhost:8080/chat", comments=[]))
    server = WebUIServer(bridge)
    server.start()
    root = tk.Tk()
    root.withdraw()
    try:
        for close_in_window in (True, False):
            completed, failed = [], []
            window = DesktopWindow(root, server.launch_url(), lambda: completed.append(True), lambda: failed.append(True))
            deadline = time.monotonic() + 35
            while not window._ready and not failed and time.monotonic() < deadline:
                root.update()
                time.sleep(.05)
            assert window._ready and not failed, "WebView did not become ready"
            handles = owned_windows(window.process.pid)
            assert len(handles) == 1, f"Expected one visible window, got {len(handles)}"
            if close_in_window:
                user = ctypes.WinDLL("user32", use_last_error=True)
                user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                user.PostMessageW(handles[0], 0x0010, 0, 0)
                deadline = time.monotonic() + 10
                while not completed and not failed and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.05)
                assert completed and not failed, "Window close did not notify the engine"
            else:
                window.close()
            assert window.process.poll() is not None, "Owned host process remained running"
        print("PASS: single WebView window; window close and parent EOF both stop the host")
    finally:
        if 'window' in locals():
            window.close()
        server.close()
        root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", help="同じ検証をPyInstaller EXEに対して実行")
    args = parser.parse_args()
    if args.executable:
        from unittest.mock import patch
        executable = str(Path(args.executable).resolve())
        with patch("sys.executable", executable), patch("sys.frozen", True, create=True):
            main()
    else:
        main()
