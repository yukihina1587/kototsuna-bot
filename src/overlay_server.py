import http.server
import socketserver
import json
import threading
import os
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


class RequestHandler(http.server.SimpleHTTPRequestHandler):
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
        elif self.path == '/api/subtitle':
            with _subtitle_lock:
                payload = dict(_subtitle_state)
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
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
        _subtitle_state["id"] += 1
        _subtitle_state["original"] = original or ""
        _subtitle_state["translated"] = translated or ""
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
