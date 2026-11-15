"""WebViewの寿命をアプリに結び付ける。TkとWebViewのメインループは別プロセス。"""

from pathlib import Path
import json
import os
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
import time
from urllib.parse import urlsplit


def validate_launch_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "http" or parts.hostname != "127.0.0.1"
            or not parts.port or parts.path != "/" or parts.query
            or parts.username or parts.password or not parts.fragment.startswith("session=")):
        raise ValueError("Invalid desktop endpoint")
    return url


class DesktopWindow:
    """起動した画面だけを所有する。URL/トークンを引数・ファイルへ書き出さない。"""

    def __init__(self, master, url, on_closed, on_failed):
        self.master = master
        self.on_closed = on_closed
        self.on_failed = on_failed
        self._closed = False
        self._ready = False
        self._messages = Queue()
        self._timer = None
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command += [str(Path(__file__).resolve().parent.parent / "main.py")]
        command += ["--webview-host"]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            self.process.stdin.write(json.dumps({"url": validate_launch_url(url)}) + "\n")
            self.process.stdin.flush()
        except Exception:
            self.close()
            raise
        self._started_at = time.monotonic()
        Thread(target=self._read_status, daemon=True).start()
        self._poll()

    def _read_status(self):
        try:
            for line in self.process.stdout:
                if line.strip() == "READY":
                    self._messages.put("READY")
        except (OSError, ValueError):
            pass
        finally:
            self.process.stdout.close()

    def _poll(self):
        if self._closed:
            return
        try:
            while self._messages.get_nowait() == "READY":
                self._ready = True
        except Empty:
            pass
        code = self.process.poll()
        if code is not None:
            self.close()
            (self.on_closed if self._ready and code == 0 else self.on_failed)()
        elif not self._ready and time.monotonic() - self._started_at > 45:
            self.close()
            self.on_failed()
        else:
            self._timer = self.master.after(250, self._poll)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            self.master.after_cancel(self._timer)
            self._timer = None
        # EOFは画面側への終了通知。親が異常終了した場合も同じ通知になる。
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()  # 自分が起動したプロセスだけを終了
            self.process.wait(timeout=5)


def run_host():
    """main.pyがGUI/音声をimportする前に呼ぶ、WebView専用のエントリーポイント。"""
    try:
        message = json.loads(sys.stdin.readline(4096))
        url = validate_launch_url(message["url"])
        import webview
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.settings["ALLOW_DOWNLOADS"] = False
        webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
        window = webview.create_window(
            "ことつな！", url, width=1180, height=850, min_size=(780, 620),
            background_color="#0b1412", text_select=True,
        )

        def ready():
            # loadedはDOM構築だけを示すため、JSと管理APIの接続完了まで確認する。
            for _ in range(150):
                try:
                    connected = window.evaluate_js(
                        "Boolean(document.getElementById('connection-alert')?.hidden)"
                    )
                except Exception:
                    return  # 閉じた画面を再操作しない
                if connected:
                    print("READY", flush=True)
                    return
                time.sleep(.1)

        def watch_parent():
            # 親からの追加操作は受け付けず、パイプが閉じるまで待つ。
            while sys.stdin.read(1):
                pass
            window.destroy()

        window.events.loaded += ready
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon_fullsize.ico"
        webview.start(lambda: Thread(target=watch_parent, daemon=True).start(),
                      gui="edgechromium", private_mode=True, icon=str(icon))
        return 0
    except Exception:
        # 例外には認証URLが含まれ得るため標準出力/エラーログへ出さない。
        return 1
