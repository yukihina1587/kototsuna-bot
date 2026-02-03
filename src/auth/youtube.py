"""
YouTube認証プロバイダー

Google OAuth 2.0 Authorization Code Flowを使用した認証。
"""

import http.server
import socketserver
import json
import urllib.parse
from typing import Optional

import aiohttp

from src.auth.base import AuthProvider, AuthResult, AuthStatus
from src.logger import logger


REDIRECT_URI = 'http://localhost:8787/youtube_callback'
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]

REDIRECT_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>YouTube Auth Callback</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #ff0000 0%, #cc0000 100%);
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            text-align: center;
        }
        h2 {
            color: #333;
            margin-bottom: 10px;
        }
        .icon {
            font-size: 48px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon" id="icon">⏳</div>
        <h2 id="status">認証処理中...</h2>
    </div>
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        const error = urlParams.get('error');

        if (error) {
            document.getElementById('status').innerText = '❌ 認証がキャンセルされました';
            document.getElementById('icon').innerText = '❌';
        } else if (code) {
            fetch('http://localhost:8787/youtube_token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ code: code }),
            })
            .then(response => {
                if (response.ok) {
                    document.getElementById('status').innerText = '✅ 認証に成功しました。このウィンドウを閉じてください。';
                    document.getElementById('icon').innerText = '✅';
                } else {
                    document.getElementById('status').innerText = '❌ トークンの取得に失敗しました';
                    document.getElementById('icon').innerText = '❌';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('status').innerText = '❌ エラーが発生しました';
                document.getElementById('icon').innerText = '❌';
            });
        } else {
            document.getElementById('status').innerText = '❌ 認証コードが見つかりません';
            document.getElementById('icon').innerText = '❌';
        }
    </script>
</body>
</html>"""


class YouTubeAuthProvider(AuthProvider):
    """
    YouTube認証プロバイダー

    Google OAuth 2.0 Authorization Code Flowを使用してアクセストークンを取得する。
    リフレッシュトークンによるトークン更新をサポート。
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, client_id: str, client_secret: str):
        super().__init__(client_id, client_secret)
        self._auth_code: Optional[str] = None

    def build_auth_url(self) -> str:
        """Google OAuth認証URLを生成"""
        params = {
            'client_id': self._client_id,
            'redirect_uri': REDIRECT_URI,
            'response_type': 'code',
            'scope': ' '.join(SCOPES),
            'access_type': 'offline',  # リフレッシュトークンを取得
            'prompt': 'consent',  # 常に同意画面を表示（リフレッシュトークン取得のため）
        }
        query_string = urllib.parse.urlencode(params)
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"

    def start_auth_server(self) -> AuthResult:
        """ローカル認証サーバーを起動して認証コードを取得"""
        self._auth_code = None
        provider = self

        class AuthHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                parsed_path = urllib.parse.urlparse(self.path)

                if parsed_path.path == "/youtube_callback":
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(REDIRECT_HTML.encode('utf-8'))
                else:
                    self.send_error(404, "Not Found")

            def do_POST(self):
                if self.path == '/youtube_token':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data)

                    code = data.get('code')
                    if code:
                        provider._auth_code = code
                        logger.debug("✅ Authorization code received")
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'OK')
                        self.server.should_shutdown = True
                    else:
                        self.send_error(400, "Bad Request: Code not found")
                else:
                    self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                return

        class StoppableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

            def __init__(self, server_address, RequestHandlerClass):
                super().__init__(server_address, RequestHandlerClass)
                self.should_shutdown = False

            def serve_forever(self):
                while not self.should_shutdown:
                    self.handle_request()

        try:
            with StoppableTCPServer(("localhost", 8787), AuthHandler) as httpd:
                logger.debug("Starting YouTube auth server on port 8787...")
                httpd.serve_forever()
                logger.debug("YouTube auth server stopped.")
        except Exception as e:
            logger.error(f"Auth server error: {e}", exc_info=True)
            return AuthResult(success=False, error_message=str(e))

        # 認証コードをトークンに交換
        if self._auth_code:
            return self._exchange_code_for_token(self._auth_code)
        else:
            return AuthResult(success=False, error_message="認証コードを取得できませんでした")

    def _exchange_code_for_token(self, code: str) -> AuthResult:
        """認証コードをアクセストークンに交換"""
        import requests

        data = {
            'code': code,
            'client_id': self._client_id,
            'client_secret': self._client_secret,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code',
        }

        try:
            response = requests.post(self.TOKEN_URL, data=data, timeout=30)

            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data.get('access_token')
                self._refresh_token = token_data.get('refresh_token')
                expires_in = token_data.get('expires_in', 3600)

                logger.info("YouTube access token obtained successfully")
                self._status = AuthStatus.AUTHENTICATED

                # ユーザー情報を取得
                user_info = self._get_user_info()

                return AuthResult(
                    success=True,
                    access_token=self._access_token,
                    refresh_token=self._refresh_token,
                    expires_in=expires_in,
                    user_name=user_info.get('name') if user_info else None,
                    user_id=user_info.get('id') if user_info else None,
                )
            else:
                error_data = response.json()
                error_msg = error_data.get('error_description', error_data.get('error', 'Unknown error'))
                logger.error(f"Token exchange failed: {error_msg}")
                return AuthResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Token exchange error: {e}", exc_info=True)
            return AuthResult(success=False, error_message=str(e))

    def _get_user_info(self) -> Optional[dict]:
        """ユーザー情報を取得"""
        import requests

        if not self._access_token:
            return None

        try:
            response = requests.get(
                self.USERINFO_URL,
                headers={'Authorization': f'Bearer {self._access_token}'},
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")

        return None

    def validate_token(self, token: Optional[str] = None) -> AuthResult:
        """トークンの有効性を検証"""
        import requests

        check_token = token or self._access_token
        if not check_token:
            return AuthResult(success=False, error_message="トークンがありません")

        try:
            # Google Token Info APIを使用して検証
            response = requests.get(
                f"https://oauth2.googleapis.com/tokeninfo?access_token={check_token}",
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                self._status = AuthStatus.AUTHENTICATED
                return AuthResult(
                    success=True,
                    access_token=check_token,
                    expires_in=int(data.get('expires_in', 0)),
                    scopes=data.get('scope', '').split(' '),
                )
            else:
                self._status = AuthStatus.INVALID
                return AuthResult(success=False, error_message="トークンが無効です")

        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return AuthResult(success=False, error_message=str(e))

    async def refresh_access_token(self) -> AuthResult:
        """リフレッシュトークンを使用してアクセストークンを更新"""
        if not self._refresh_token:
            return AuthResult(
                success=False,
                error_message="リフレッシュトークンがありません"
            )

        data = {
            'client_id': self._client_id,
            'client_secret': self._client_secret,
            'refresh_token': self._refresh_token,
            'grant_type': 'refresh_token',
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.TOKEN_URL, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self._access_token = token_data.get('access_token')
                        expires_in = token_data.get('expires_in', 3600)

                        logger.info("YouTube access token refreshed successfully")
                        self._status = AuthStatus.AUTHENTICATED

                        return AuthResult(
                            success=True,
                            access_token=self._access_token,
                            refresh_token=self._refresh_token,
                            expires_in=expires_in,
                        )
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error_description', 'Token refresh failed')
                        logger.error(f"Token refresh failed: {error_msg}")
                        self._status = AuthStatus.EXPIRED
                        return AuthResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Token refresh error: {e}", exc_info=True)
            return AuthResult(success=False, error_message=str(e))
