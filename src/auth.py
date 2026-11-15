import http.server, socketserver, urllib.parse, json
from dotenv import load_dotenv
import os
import requests
import time
import secrets
from src.logger import logger

load_dotenv()

REDIRECT_URI = 'http://localhost:8787/redirect.html'
SCOPES = ['chat:read', 'chat:edit', 'moderator:read:followers', 'channel:manage:broadcast', 'clips:edit']


def check_missing_scopes(token_scopes: list[str]) -> list[str]:
    """必要なスコープのうちトークンに含まれないものを返す"""
    return [s for s in SCOPES if s not in token_scopes]


def _get_default_client_id() -> str:
    """デフォルトClient IDを返す。

    優先順位:
    1. 環境変数 TWITCH_CLIENT_ID（.env / 開発環境）
    2. ビルド時に埋め込まれた src/_client_id.py（配布exe）
    """
    env_id = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    if env_id:
        return env_id
    try:
        from src._client_id import TWITCH_CLIENT_ID  # type: ignore[import]
        return TWITCH_CLIENT_ID.strip()
    except ImportError:
        pass
    return ""


# アプリ同梱のデフォルトClient ID
APP_DEFAULT_CLIENT_ID: str = _get_default_client_id()


def get_effective_client_id(user_client_id: str = "") -> str:
    """
    有効なClient IDを返す。
    ユーザーが設定している場合はそちらを優先し、
    空欄の場合はアプリ同梱のデフォルトClient IDにフォールバックする。
    """
    cid = (user_client_id or "").strip()
    return cid if cid else APP_DEFAULT_CLIENT_ID

token_result = {}

REDIRECT_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Twitch Auth Callback</title>
    <script>
        window.onload = function() {
            const hash = window.location.hash.substring(1);
            const params = new URLSearchParams(hash);
            const accessToken = params.get("access_token");
            const state = params.get("state");
            history.replaceState(null, "", location.pathname);

            if (accessToken) {
                fetch("http://localhost:8787/token", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ token: accessToken, state }),
                })
                .then(response => {
                    if (response.ok) {
                        document.getElementById("status").innerText = "✅ 認証に成功しました。このウィンドウを閉じてください。";
                    } else {
                        document.getElementById("status").innerText = "❌ トークンの送信に失敗しました。";
                    }
                })
                .catch(error => {
                    console.error("Error:", error);
                    document.getElementById("status").innerText = "❌ エラーが発生しました。";
                });
            } else {
                document.getElementById("status").innerText = "❌ 認証に失敗しました。アクセストークンが見つかりません。";
            }
        };
    </script>
</head>
<body>
    <h2 id="status">認証処理中...</h2>
</body>
</html>"""

def build_auth_url(client_id, state=None):
    return (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=token"
        f"&scope={'%20'.join(SCOPES)}"
        f"&force_verify=true"
        + ("&state=" + urllib.parse.quote(state, safe="") if state else "")
    )

def run_auth_server_and_get_token(on_ready=None, expected_state=None, timeout=300):
    # 1回の認証だけに有効な結果。以前のトークンを再利用しない。
    result = {}
    origin = "http://localhost:8787"

    class AuthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") != "localhost:8787" or self.path != "/redirect.html":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(REDIRECT_HTML.encode("utf-8"))

        def do_POST(self):
            if (self.path != "/token" or self.headers.get("Host") != "localhost:8787"
                    or self.headers.get("Origin") != origin
                    or self.headers.get("Content-Type", "").split(";")[0] != "application/json"):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                token = data.get("token")
                state = data.get("state")
                if not isinstance(token, str) or not token.isalnum() or len(token) > 512:
                    raise ValueError()
                if expected_state and (not isinstance(state, str) or not secrets.compare_digest(state, expected_state)):
                    raise ValueError()
            except (ValueError, AttributeError, TypeError):
                self.send_error(400)
                return
            result["access_token"] = "oauth:" + token
            logger.debug("Twitch認証トークンを受信しました")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            self.server.should_shutdown = True

        def log_message(self, format, *args):
            return

    class AuthServer(socketserver.TCPServer):
        allow_reuse_address = True
        def get_request(self):
            request, address = super().get_request()
            request.settimeout(5)
            return request, address

    with AuthServer(("127.0.0.1", 8787), AuthHandler) as server:
        server.timeout = .5
        server.should_shutdown = False
        if on_ready:
            on_ready()
        deadline = time.monotonic() + timeout
        while not server.should_shutdown and time.monotonic() < deadline:
            server.handle_request()
    return result.get("access_token")

def validate_token(access_token, max_retries=2):
    """
    Twitch APIでアクセストークンの有効性を検証する
    ネットワークエラー時は自動リトライ

    Returns:
        bool: トークンが有効かどうか
    """
    result = validate_token_with_info(access_token, max_retries)
    return result is not None


def validate_token_with_info(access_token, max_retries=2):
    """
    Twitch APIでアクセストークンの有効性を検証し、ユーザー情報を返す
    ネットワークエラー時は自動リトライ

    Returns:
        dict: 有効な場合はユーザー情報（login, user_id等）
        None: トークンが無効（API応答で確認済み）
        False: ネットワーク/TLSエラーで検証不能（トークン自体は無効とは限らない）
    """
    token = access_token
    if token.startswith("oauth:"):
        token = token[6:]

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {token}"},
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Token is valid. User: {data.get('login', 'unknown')}, Expires in: {data.get('expires_in', 0)}s")
                return {
                    'login': data.get('login', ''),
                    'user_id': data.get('user_id', ''),
                    'expires_in': data.get('expires_in', 0),
                    'scopes': data.get('scopes', [])
                }
            else:
                logger.warning(f"Token validation failed: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"Token validation timeout (attempt {attempt + 1}/{max_retries + 1})")
            if attempt < max_retries:
                time.sleep(1)
                continue
            return False
        except Exception as e:
            logger.error(f"Failed to validate token: {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            return False

    return False