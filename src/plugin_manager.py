"""
Kototsuna プラグインマネージャー

わんコメ互換の JavaScript プラグイン (plugin.js) を Node.js サブプロセスで実行し、
コメントのフィルタリングとイベント通知を行う。

プラグイン配置先:
    Windows: %APPDATA%\\Kototsuna\\plugins\\{plugin-name}\\plugin.js
    その他:   ~/.config/Kototsuna/plugins/{plugin-name}/plugin.js

わんコメ互換フック:
    init(params, initialData)               — 起動時に1回呼ばれる
    filterComment(comment, service, userData) — コメントごとに呼ばれる
    subscribe(type, data)                   — コメントイベント通知
    destroy()                               — 終了時に呼ばれる
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from src.logger import logger


# ─── ディレクトリ解決 ──────────────────────────────────────────────

def get_plugins_dir() -> Path:
    """プラグインディレクトリのパスを返す。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "Kototsuna" / "plugins"


def _get_runner_path() -> Path:
    return Path(__file__).parent / "plugins" / "host_runner.js"


# ─── 単一プラグインプロセス ────────────────────────────────────────

class PluginProcess:
    """Node.js サブプロセスで動作する単一プラグインのラッパー。"""

    def __init__(self, plugin_js: Path) -> None:
        self.path = plugin_js
        self.name: str = ""
        self.uid: str = ""
        self.version: str = ""
        self._proc: Optional[subprocess.Popen] = None
        self._send_lock = threading.Lock()
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, Any] = {}
        self._reader: Optional[threading.Thread] = None

    # ── ライフサイクル ──────────────────────────────────────────────

    def start(self) -> bool:
        """プロセスを起動して init を送信する。成功したら True を返す。"""
        runner = _get_runner_path()
        if not runner.exists():
            logger.error(f"Plugin host runner not found: {runner}")
            return False

        try:
            self._proc = subprocess.Popen(
                ["node", str(runner), str(self.path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
            )
        except FileNotFoundError:
            logger.error("node コマンドが見つかりません。Node.js をインストールしてください。")
            return False
        except Exception as e:
            logger.error(f"Plugin process start failed ({self.path}): {e}")
            return False

        # stderr を捨てるスレッド（ブロック防止）
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        result = self._send_wait({"type": "init", "data": {}}, timeout=5.0)
        if result and result.get("type") == "ready":
            self.name = result.get("name", str(self.path.parent.name))
            self.uid = result.get("uid", "")
            self.version = result.get("version", "")
            logger.info(f"Plugin loaded: {self.name} ({self.uid}) v{self.version}")
            return True

        logger.error(f"Plugin init failed for {self.path}: {result}")
        self.stop()
        return False

    def stop(self) -> None:
        """プロセスを停止する。"""
        if self._proc:
            try:
                self._send_raw({"type": "shutdown"})
                self._proc.wait(timeout=3.0)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None

    # ── API ────────────────────────────────────────────────────────

    def filter_comment(
        self, comment: dict, service: str, user_data: Optional[dict] = None
    ) -> Optional[dict]:
        """filterComment を呼び出す。

        Returns:
            変換済みコメント dict — 通過
            None                  — ブロック（プラグインが false を返した場合）
        """
        msg_id = str(uuid.uuid4())
        result = self._send_wait(
            {
                "type": "comment",
                "id": msg_id,
                "comment": comment,
                "service": service,
                "userData": user_data,
            },
            timeout=3.0,
        )
        if result is None:
            # タイムアウト: 元のコメントをそのまま通す
            return comment
        r = result.get("result")
        if r is False:
            return None
        return r if isinstance(r, dict) else comment

    def notify_subscribe(self, event: str, data: Any) -> None:
        """subscribe を非同期で呼び出す（戻り値は使わない）。"""
        self._send_raw(
            {"type": "subscribe", "id": str(uuid.uuid4()), "event": event, "data": data}
        )

    # ── 内部通信 ───────────────────────────────────────────────────

    def _send_raw(self, obj: dict) -> None:
        if self._proc and self._proc.stdin:
            try:
                with self._send_lock:
                    self._proc.stdin.write(json.dumps(obj) + "\n")
                    self._proc.stdin.flush()
            except Exception as e:
                logger.debug(f"Plugin send error ({self.name}): {e}")

    def _send_wait(self, obj: dict, timeout: float = 5.0) -> Optional[dict]:
        msg_id = obj.setdefault("id", str(uuid.uuid4()))
        ev = threading.Event()
        self._pending[msg_id] = ev
        self._send_raw(obj)
        ev.wait(timeout=timeout)
        return self._results.pop(msg_id, None)

    def _read_loop(self) -> None:
        while self._proc:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                msg = json.loads(line.strip())
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    self._results[msg_id] = msg
                    self._pending.pop(msg_id).set()
                elif msg.get("type") == "log":
                    level = msg.get("level", "info")
                    getattr(logger, level, logger.info)(
                        f"[Plugin:{self.name}] {msg.get('message', '')}"
                    )
                elif msg.get("type") == "error":
                    logger.error(f"[Plugin:{self.name}] {msg.get('message', '')}")
            except Exception:
                break

    def _drain_stderr(self) -> None:
        if self._proc and self._proc.stderr:
            for line in self._proc.stderr:
                line = line.strip()
                if line:
                    logger.debug(f"[Plugin:{self.path.parent.name}] {line}")


# ─── プラグインマネージャー ────────────────────────────────────────

class PluginManager:
    """わんコメ互換 JavaScript プラグインの読み込み・管理クラス。"""

    def __init__(self) -> None:
        self._plugins: list[PluginProcess] = []
        self._lock = threading.Lock()

    @property
    def plugins(self) -> list[PluginProcess]:
        return list(self._plugins)

    @property
    def count(self) -> int:
        return len(self._plugins)

    def load_plugins(self, plugins_dir: Optional[Path] = None) -> int:
        """plugins_dir 以下の全プラグインを読み込む。起動できた数を返す。"""
        if plugins_dir is None:
            plugins_dir = get_plugins_dir()
        if not plugins_dir.exists():
            logger.info(f"Plugin directory not found (skipping): {plugins_dir}")
            return 0

        loaded = 0
        for subdir in sorted(plugins_dir.iterdir()):
            if not subdir.is_dir():
                continue
            plugin_js = subdir / "plugin.js"
            if not plugin_js.exists():
                continue
            proc = PluginProcess(plugin_js)
            if proc.start():
                with self._lock:
                    self._plugins.append(proc)
                loaded += 1
            else:
                logger.warning(f"Failed to load plugin: {plugin_js}")

        logger.info(f"Plugins loaded: {loaded}")
        return loaded

    def filter_comment(self, comment: dict, service: str) -> Optional[dict]:
        """全プラグインの filterComment を順番に通す。

        Returns:
            変換済みコメント dict — 通過
            None                  — いずれかのプラグインがブロックした
        """
        current = comment
        with self._lock:
            procs = list(self._plugins)
        for proc in procs:
            result = proc.filter_comment(current, service)
            if result is None:
                return None
            current = result
        return current

    def notify_comments(self, comments: list[dict]) -> None:
        """全プラグインの subscribe('comments', ...) を非同期で呼び出す。"""
        if not comments:
            return
        data = {"comments": comments}
        with self._lock:
            procs = list(self._plugins)
        for proc in procs:
            try:
                proc.notify_subscribe("comments", data)
            except Exception as e:
                logger.debug(f"Plugin notify error ({proc.name}): {e}")

    def unload_all(self) -> None:
        """全プラグインを停止する。"""
        with self._lock:
            procs = list(self._plugins)
            self._plugins.clear()
        for proc in procs:
            try:
                proc.stop()
            except Exception as e:
                logger.error(f"Error unloading plugin {proc.name}: {e}")
        logger.info("All plugins unloaded")


# ─── シングルトン ─────────────────────────────────────────────────

_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """グローバルな PluginManager インスタンスを返す。"""
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
