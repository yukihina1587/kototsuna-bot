"""
Twitch認証プロバイダー

Twitch OAuth 2.0 Implicit Flowを使用した認証。
"""

import http.server
import socketserver
import json
import time
from typing import Optional

import requests

from src.auth.base import AuthProvider, AuthResult, AuthStatus
from src.logger import logger


REDIRECT_URI = 'http://localhost:8787/redirect.html'
SCOPES = ['chat:read', 'chat:edit', 'moderator:read:followers']

REDIRECT_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Twitch Auth Callback</title>
    <script>
        window.onload = function() {
            const hash = window.location.hash.substring(1);
            const params = new URLSearchParams(hash);
            const accessToken = params.get("access_token");

            if (accessToken) {
                fetch("http://localhost:8787/token", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ token: accessToken }),
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


class TwitchAuthProvider(AuthProvider):
    """
    Twitch認証プロバイダー

    Twitch OAuth 2.0 Implicit Flowを使用してアクセストークンを取得する。
    """

    def __init__(self, client_id: str, client_secret: Optional[str] = None):
        super().__init__(client_id, client_secret)
        self._token_result: dict = {}

    def build_auth_url(self) -> str:
        """Twitch OAuth認証URLを生成"""
        return (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={self._client_id}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=token"
            f"&scope={'%20'.join(SCOPES)}"
            f"&force_verify=true"
        )

    def start_auth_server(self) -> AuthResult:
        """ローカル認証サーバーを起動してトークンを取得"""
        self._token_result = {}
        provider = self  # クロージャ用

        class AuthHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect.html":
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(REDIRECT_HTML.encode('utf-8'))
                else:
                    self.send_error(404, "Not Found")

            def do_POST(self):
                if self.path == '/token':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data)

                    token = data.get('token')
                    if token:
                        provider._token_result['access_token'] = f"oauth:{token}"
                        logger.debug(f"✅ access_token extracted")
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'OK')
                        self.server.should_shutdown = True
                    else:
                        self.send_error(400, "Bad Request: Token not found")
                else:
                    self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                return  # ログ出力を抑制

        class StoppableTCPServer(socketserver.TCPServer):
            def __init__(self, server_address, RequestHandlerClass):
                super().__init__(server_address, RequestHandlerClass)
                self.should_shutdown = False

            def serve_forever(self):
                while not self.should_shutdown:
                    self.handle_request()

        try:
            with StoppableTCPServer(("localhost", 8787), AuthHandler) as httpd:
                logger.debug("Starting Twitch auth server on port 8787...")
                httpd.serve_forever()
                logger.debug("Twitch auth server stopped.")
        except Exception as e:
            logger.error(f"Auth server error: {e}", exc_info=True)
            return AuthResult(success=False, error_message=str(e))

        token = self._token_result.get("access_token")
        if token:
            self._access_token = token
            self._status = AuthStatus.AUTHENTICATED
            return AuthResult(success=True, access_token=token)
        else:
            return AuthResult(success=False, error_message="トークンを取得できませんでした")

    def validate_token(self, token: Optional[str] = None, max_retries: int = 2) -> AuthResult:
        """トークンの有効性を検証"""
        check_token = token or self._access_token
        if not check_token:
            return AuthResult(success=False, error_message="トークンがありません")

        # oauth:プレフィックスを除去
        if check_token.startswith("oauth:"):
            check_token = check_token[6:]

        for attempt in range(max_retries + 1):
            try:
                response = requests.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {check_token}"},
                    timeout=15
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Token is valid. User: {data.get('login', 'unknown')}")
                    self._status = AuthStatus.AUTHENTICATED
                    return AuthResult(
                        success=True,
                        access_token=token or self._access_token,
                        user_name=data.get('login', ''),
                        user_id=data.get('user_id', ''),
                        expires_in=data.get('expires_in', 0),
                        scopes=data.get('scopes', [])
                    )
                else:
                    logger.warning(f"Token validation failed: {response.status_code}")
                    self._status = AuthStatus.INVALID
                    return AuthResult(success=False, error_message=f"検証失敗: {response.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"Token validation timeout (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return AuthResult(success=False, error_message="タイムアウト")
            except Exception as e:
                logger.error(f"Failed to validate token: {e}")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return AuthResult(success=False, error_message=str(e))

        return AuthResult(success=False, error_message="検証に失敗しました")

    async def refresh_access_token(self) -> AuthResult:
        """
        アクセストークンを更新

        Note: Twitch Implicit Flowはリフレッシュトークンを提供しないため、
        再認証が必要
        """
        return AuthResult(
            success=False,
            error_message="Twitch Implicit Flowはトークン更新をサポートしていません。再認証が必要です。"
        )


# 後方互換性のための関数
def build_auth_url(client_id: str) -> str:
    """後方互換性のためのヘルパー関数"""
    provider = TwitchAuthProvider(client_id)
    return provider.build_auth_url()


def run_auth_server_and_get_token() -> Optional[str]:
    """後方互換性のためのヘルパー関数"""
    # 注意: この関数はclient_idなしで動作するが、推奨されない
    provider = TwitchAuthProvider("")
    result = provider.start_auth_server()
    return result.access_token if result.success else None


def validate_token(access_token: str, max_retries: int = 2) -> bool:
    """後方互換性のためのヘルパー関数"""
    provider = TwitchAuthProvider("")
    result = provider.validate_token(access_token, max_retries)
    return result.success


def validate_token_with_info(access_token: str, max_retries: int = 2) -> Optional[dict]:
    """後方互換性のためのヘルパー関数"""
    provider = TwitchAuthProvider("")
    result = provider.validate_token(access_token, max_retries)
    if result.success:
        return {
            'login': result.user_name,
            'user_id': result.user_id,
            'expires_in': result.expires_in,
            'scopes': result.scopes
        }
    return None
