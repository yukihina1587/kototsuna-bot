"""明示的に開いたときだけ動く、loopback限定のWeb操作画面。"""

import asyncio
from pathlib import Path
import secrets
from threading import Event, Thread

from aiohttp import web

from src.web_control import ControlBridge, ControlError


ASSET_DIR = Path(__file__).with_name("web_ui_assets")
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


class WebUIServer:
    def __init__(self, bridge: ControlBridge, command_timeout: float = 10):
        self.bridge = bridge
        self._token = secrets.token_urlsafe(32)
        self.command_timeout = command_timeout
        self.origin = ""
        self._ready = Event()
        self._thread = None
        self._loop = None
        self._stop = None
        self._startup_failed = False

    def launch_url(self, dock: bool = False) -> str:
        # fragmentはHTTPリクエストやRefererに送られない。
        return f"{self.origin}/{'dock' if dock else ''}#session={self._token}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="kototsuna-web-ui", daemon=True)
        self._thread.start()
        if not self._ready.wait(5) or self._startup_failed:
            self.close()
            raise RuntimeError("Web画面を開始できませんでした。")

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception:
            self._startup_failed = True
        finally:
            self._ready.set()

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        runner = web.AppRunner(self.create_app(), access_log=None, shutdown_timeout=1)
        try:
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = runner.addresses[0][1]
            self.origin = f"http://127.0.0.1:{port}"
            self._ready.set()
            await self._stop.wait()
        finally:
            await runner.cleanup()

    def close(self) -> None:
        self.bridge.close()
        if self._loop and not self._loop.is_closed() and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=3)

    def create_app(self) -> web.Application:
        @web.middleware
        async def boundary(request, handler):
            try:
                hosts = request.headers.getall("Host", [])
                origins = request.headers.getall("Origin", [])
                if hosts != [self.origin.removeprefix("http://")]:
                    raise ControlError("接続先が正しくありません。", 403)
                if origins and origins != [self.origin]:
                    raise ControlError("この画面からの接続は許可されていません。", 403)
                if request.headers.get("Sec-Fetch-Site") == "cross-site":
                    raise ControlError("この画面からの接続は許可されていません。", 403)
                if request.path.startswith("/api/"):
                    auth = request.headers.get("Authorization", "")
                    expected = f"Bearer {self._token}"
                    if not auth.isascii() or not secrets.compare_digest(auth, expected):
                        raise ControlError("本体の「Web画面を開く」から接続し直してください。", 401)
                    if request.method == "POST" and origins != [self.origin]:
                        raise ControlError("操作元を確認できません。", 403)
                response = await handler(request)
            except ControlError as exc:
                response = web.json_response({"error": str(exc)}, status=exc.status)
            except web.HTTPException as exc:
                response = web.json_response({"error": "このリクエストは使用できません。"}, status=exc.status)
            except Exception:
                response = web.json_response({"error": "画面を読み込めませんでした。"}, status=500)
            response.headers.update(SECURITY_HEADERS)
            return response

        app = web.Application(middlewares=[boundary], client_max_size=16384)
        app.router.add_get("/api/state", self._state)
        app.router.add_post("/api/command", self._command)
        app.router.add_get("/", self._asset)
        app.router.add_get("/dock", self._asset)
        for name in ("app.js", "app.css", "icon.ico"):
            app.router.add_get("/" + name, self._asset)
        return app

    async def _state(self, request):
        return web.json_response(self.bridge.snapshot())

    async def _command(self, request):
        if request.content_type != "application/json":
            raise ControlError("JSON形式で操作してください。", 415)
        try:
            data = await request.json()
        except (ValueError, UnicodeError):
            raise ControlError("操作の形式が正しくありません。") from None
        future = self.bridge.submit(data)
        try:
            result = await asyncio.wait_for(asyncio.wrap_future(future), self.command_timeout)
        except asyncio.TimeoutError:
            future.cancel()
            raise ControlError("応答を待っています。本体の状態を確認してから操作してください。", 504) from None
        except asyncio.CancelledError:
            raise ControlError("操作は中止されました。本体の状態を確認してください。", 503) from None
        return web.json_response(result)

    async def _asset(self, request):
        if request.path == "/icon.ico":
            path = Path(__file__).resolve().parent.parent / "assets" / "icon_fullsize.ico"
            mime = "image/x-icon"
        else:
            name = "index.html" if request.path in ("/", "/dock") else request.path[1:]
            path = ASSET_DIR / name
            mime = {"index.html": "text/html", "app.js": "text/javascript", "app.css": "text/css"}[name]
        return web.Response(body=path.read_bytes(), content_type=mime)
