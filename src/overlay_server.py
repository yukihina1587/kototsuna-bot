import http.server
import socketserver
import json
import threading
import os
import uuid
from datetime import datetime
from functools import partial
from src.logger import logger

DEFAULT_PORT = 8080
current_translation = {"text": "", "id": 0}
history = []
_httpd_instance = None
_server_thread = None
_overlay_port = DEFAULT_PORT
_chat_html_path = None
_subtitle_html_path = None
_subtitle_state = {
    "id": 0, "enabled": False,
    "original": "", "translated": "", "speaker": "", "timestamp": "",
    "config": {}
}
_subtitle_lock = threading.Lock()

# チャットメッセージのインメモリ状態
# OBSブラウザソースはJSONを /api/chat から取得するため、チャットHTMLファイル自体は
# 起動時と設定変更時にしか書き換えない（書き換え中のファイル読み取り破損を避ける）。
_chat_state = {
    "messages": [],
    "newest_first": False,
    "max_entries": 200,
    "session": uuid.uuid4().hex[:12],
}
_chat_lock = threading.Lock()

# 初見視聴者ウェルカム（Issue #140）
_welcome_state = {
    "id": 0,
    "user": "",
    "text": "",
    "timestamp": "",
}
_welcome_lock = threading.Lock()


def _normalize_subtitle_lines(original: str, translated: str, config: dict | None) -> tuple[str, str]:
    """字幕の原文/翻訳文を設定に応じて正規化する。"""
    original_text = original or ""
    translated_text = translated or ""
    cfg = config or {}

    if (
        cfg.get("show_original", True)
        and cfg.get("show_translated", True)
        and original_text.strip()
        and original_text.strip() == translated_text.strip()
    ):
        translated_text = ""

    return original_text, translated_text


class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # type: ignore[override]
        """アクセスログをアプリのロガーに流す（コンソール非表示）。"""
        logger.debug("overlay: " + (format % args))

    def do_GET(self):
        if self.path == '/api/current':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(current_translation).encode('utf-8'))
        elif self.path == '/api/history':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(history).encode('utf-8'))
        elif self.path.split('?')[0] == '/api/subtitle':
            with _subtitle_lock:
                payload = dict(_subtitle_state)
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        elif self.path == '/api/welcome':
            with _welcome_lock:
                payload = dict(_welcome_state)
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        elif self.path == '/api/giveaway':
            from src.games import get_giveaway_manager
            state = get_giveaway_manager().get_state()
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(state, ensure_ascii=False).encode('utf-8'))
        elif self.path.split('?')[0] == '/api/chat':
            with _chat_lock:
                payload = {
                    "messages": list(_chat_state["messages"]),
                    "newest_first": _chat_state["newest_first"],
                    "max_entries": _chat_state["max_entries"],
                    "session": _chat_state["session"],
                }
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        elif self.path.startswith('/subtitle'):
            self._serve_subtitle_html()
        elif self.path.startswith('/chat'):
            self._serve_chat_html()
        else:
            # Serve static files (overlay.html)
            super().do_GET()

    def _serve_chat_html(self):
        """チャットHTMLを配信"""
        content = _load_overlay_html(_chat_html_path)
        if content is None:
            logger.warning("Chat HTML not available yet; serving blank overlay.")
            content = _blank_overlay_html()
        self._send_html(content)


    def _serve_subtitle_html(self):
        """字幕HTMLを配信"""
        content = _load_overlay_html(_subtitle_html_path)
        if content is None:
            logger.warning("Subtitle HTML not available yet; serving blank overlay.")
            content = _blank_overlay_html()
        self._send_html(content)

    def _send_html(self, content: str) -> None:
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))


def _blank_overlay_html() -> str:
    """OBSでエラーページを見せないための空HTML。"""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:transparent;overflow:hidden;'></body></html>"
    )


def _load_overlay_html(path: str | None) -> str | None:
    """HTMLを読み込めたら返し、未準備や読み込み失敗時はNoneを返す。"""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Failed to read overlay HTML '{path}': {e}")
        return None


def _find_free_port(start_port: int = DEFAULT_PORT, max_tries: int = 10) -> int:
    """Try to find a free port starting from start_port."""
    for i in range(max_tries):
        port = start_port + i
        with socketserver.socket.socket() as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return 0


def start_server():
    global _httpd_instance, _overlay_port
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        handler = partial(RequestHandler, directory=base_dir)
        port = _find_free_port()
        if port == 0:
            logger.error("Overlay server failed to find free port; skipping start.")
            return

        _overlay_port = port
        # Allow quick rebinding if recently closed
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("", port), handler)
        _httpd_instance = httpd
        logger.info(f"Overlay server started on port {port}")
        logger.info(f"  Chat HTML: http://localhost:{port}/chat")
        logger.info(f"  Subtitle:  http://localhost:{port}/subtitle")
        logger.info(f"  Overlay:   http://localhost:{port}/overlay.html")
        httpd.serve_forever()
    except OSError as e:
        logger.error(f"Server error (Port {_overlay_port} maybe in use): {e}", exc_info=True)
    finally:
        _httpd_instance = None


def update_translation(text):
    global current_translation, history
    current_translation["text"] = text or ""
    current_translation["id"] += 1

    # Add to history
    if text:
        history.append(text)
        if len(history) > 50:
            history.pop(0)


def update_subtitle(original: str, translated: str, speaker: str = "", config: dict = None) -> None:
    """字幕状態を更新する（gui.py の on_comment_received / voice_callback から呼ぶ）"""
    global _subtitle_state
    with _subtitle_lock:
        if not _subtitle_state.get("enabled"):
            return
        normalized_original, normalized_translated = _normalize_subtitle_lines(original, translated, config)
        _subtitle_state["id"] += 1
        _subtitle_state["original"] = normalized_original
        _subtitle_state["translated"] = normalized_translated
        _subtitle_state["speaker"] = speaker or ""
        _subtitle_state["timestamp"] = datetime.now().strftime("%H:%M:%S")
        if config is not None:
            _subtitle_state["config"] = config


def set_subtitle_enabled(enabled: bool) -> None:
    """字幕のON/OFFを切り替える"""
    global _subtitle_state
    with _subtitle_lock:
        _subtitle_state["enabled"] = enabled


def set_subtitle_html_path(path: str) -> None:
    """字幕HTMLのファイルパスを設定"""
    global _subtitle_html_path
    _subtitle_html_path = path
    logger.info(f"Subtitle HTML path set to: {path}")


def run_server_thread():
    global _server_thread
    if _httpd_instance:
        return
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    _server_thread = t


def get_overlay_port() -> int:
    """現在のオーバーレイサーバーのポート番号を返す"""
    return _overlay_port


def set_chat_html_path(path: str):
    """チャットHTMLのファイルパスを設定"""
    global _chat_html_path
    _chat_html_path = path
    logger.info(f"Chat HTML path set to: {path}")


def push_welcome_event(*, user: str, text: str) -> None:
    """初見ウェルカムメッセージを overlay へ通知する（Issue #140）。

    オーバーレイ側は ``/api/welcome`` をポーリングして ``id`` 変化で発火する。
    """
    with _welcome_lock:
        _welcome_state["id"] += 1
        _welcome_state["user"] = str(user or "")
        _welcome_state["text"] = str(text or "")
        _welcome_state["timestamp"] = datetime.now().strftime("%H:%M:%S")


def get_welcome_state() -> dict:
    """テスト・GUI 用に現在のウェルカム状態を返す。"""
    with _welcome_lock:
        return dict(_welcome_state)


def add_chat_message(entry: dict) -> None:
    """チャットメッセージを1件追加する（JSONポーリング用）。"""
    with _chat_lock:
        messages = _chat_state["messages"]
        messages.append(entry)
        max_entries = int(_chat_state.get("max_entries", 200) or 200)
        if len(messages) > max_entries:
            _chat_state["messages"] = messages[-max_entries:]


def replace_chat_messages(entries: list) -> None:
    """現在のメッセージ一覧を一括置換する（起動時の復元など用途）。"""
    with _chat_lock:
        max_entries = int(_chat_state.get("max_entries", 200) or 200)
        trimmed = list(entries)[-max_entries:]
        _chat_state["messages"] = trimmed


def clear_chat_messages() -> None:
    """チャットメッセージを全消去してセッションIDを更新する。"""
    with _chat_lock:
        _chat_state["messages"] = []
        _chat_state["session"] = uuid.uuid4().hex[:12]


def set_chat_config(newest_first: bool, max_entries: int, bump_session: bool = False) -> None:
    """チャット表示の設定を更新する。表示順や件数が変わる際は bump_session=True でクライアントDOMをリセットさせる。"""
    with _chat_lock:
        _chat_state["newest_first"] = bool(newest_first)
        try:
            new_max = int(max_entries)
        except (TypeError, ValueError):
            new_max = 200
        _chat_state["max_entries"] = max(1, min(5000, new_max))
        if len(_chat_state["messages"]) > _chat_state["max_entries"]:
            _chat_state["messages"] = _chat_state["messages"][-_chat_state["max_entries"]:]
        if bump_session:
            _chat_state["session"] = uuid.uuid4().hex[:12]


def get_chat_session() -> str:
    """現在のチャットセッションIDを返す（HTML埋め込み用）。"""
    with _chat_lock:
        return _chat_state["session"]


def stop_server():
    """Stop overlay server and free port."""
    global _httpd_instance
    try:
        if _httpd_instance:
            _httpd_instance.shutdown()
            _httpd_instance.server_close()
            logger.info("Overlay server stopped and port released")
    except Exception as e:
        logger.error(f"Failed to stop overlay server: {e}", exc_info=True)
    finally:
        _httpd_instance = None
