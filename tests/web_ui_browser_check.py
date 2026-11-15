"""既存ChromiumでWeb画面を確認する。Twitch・音声・ユーザー設定は使用しない。

python tests/web_ui_browser_check.py --chromium /path/to/chrome
CDPを既存依存aiohttpで操作するため、追加のブラウザテスト依存は不要。
"""

import argparse
import asyncio
import base64
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.web_control import ControlBridge
from src.web_ui import WebUIServer
from src.web_settings import settings_snapshot
from types import SimpleNamespace


class Page:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0
        self.errors = []

    async def call(self, method, params=None):
        self.sequence += 1
        await self.socket.send_json({"id": self.sequence, "method": method, "params": params or {}})
        while True:
            message = await self.socket.receive_json(timeout=10)
            if message.get("method") == "Runtime.exceptionThrown":
                self.errors.append("JavaScript exception")
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(message["error"]["message"])
                return message.get("result", {})

    async def evaluate(self, expression):
        response = await self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        if "exceptionDetails" in response:
            raise AssertionError(response["exceptionDetails"]["text"])
        return response.get("result", {}).get("value")

    async def wait(self, expression):
        for _ in range(100):
            if await self.evaluate(expression):
                return
            await asyncio.sleep(0.05)
        raise AssertionError("Browser condition failed: " + expression)

    async def screenshot(self, path):
        await asyncio.sleep(.25)  # 短い表示アニメーションが終わってから記録する。
        result = await self.call("Page.captureScreenshot", {"format": "png"})
        path.write_bytes(base64.b64decode(result["data"]))


async def check(browser_port, server, bridge, output):
    async with aiohttp.ClientSession() as session:
        async def open_page(url, width, height):
            async with session.put(f"http://127.0.0.1:{browser_port}/json/new?about:blank") as response:
                target = await response.json()
            page = Page(await session.ws_connect(target["webSocketDebuggerUrl"]))
            await page.call("Page.enable")
            await page.call("Runtime.enable")
            await page.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
            await page.call("Page.navigate", {"url": url})
            await page.wait("document.getElementById('connection-alert')?.hidden === true")
            return page

        page = await open_page(server.launch_url(), 1180, 850)
        assert await page.evaluate("document.querySelectorAll('.comment').length") == 3
        assert await page.evaluate("location.hash") == ""
        assert not await page.evaluate("window.untrustedCommentExecuted || false")
        assert await page.evaluate("document.getElementById('comments').textContent.includes('<img')")
        assert not await page.evaluate("document.getElementById('comments').querySelector('img') !== null")
        state = bridge.snapshot()
        state["comments"][2].update(name="みなと", message="翻訳があると、みんなのコメントが分かってうれしい！", translated="I'm glad the translations help me understand everyone's comments!")
        bridge.publish(state)
        await page.wait("document.getElementById('comments').textContent.includes('みなと')")
        await page.screenshot(output / "web-dark.png")
        await page.evaluate("document.getElementById('theme').click()")
        await page.wait("document.documentElement.dataset.theme === 'light'")
        await page.screenshot(output / "web-light.png")
        await page.call("Page.reload")
        await page.wait("document.getElementById('connection-alert')?.hidden === true")
        await page.wait("document.documentElement.dataset.theme === 'light'")

        await page.evaluate("document.getElementById('translation').click()")
        await page.wait("document.getElementById('action-message').textContent === '操作を受け付けました。'")
        assert bridge.snapshot()["translation_enabled"] is False
        await page.evaluate("document.getElementById('volume').value = '37'; document.getElementById('volume').dispatchEvent(new Event('change'))")
        await page.wait("!document.getElementById('controls').disabled")
        assert bridge.snapshot()["tts_volume"] == 37
        await page.evaluate("document.getElementById('speed').value = '1.4'; document.getElementById('speed').dispatchEvent(new Event('change'))")
        await page.wait("!document.getElementById('controls').disabled")
        assert bridge.snapshot()["tts_speed"] == 1.4
        await page.evaluate("document.getElementById('start-stop').click()")
        await page.wait("document.getElementById('bot-status').textContent === '停止中'")
        assert bridge.snapshot()["connection"] == "stopped"
        await page.evaluate("document.getElementById('start-stop').click()")
        await page.wait("document.getElementById('bot-status').textContent === '接続済み'")

        await page.evaluate("document.getElementById('settings').click()")
        await page.wait("!document.getElementById('settings-panel').hidden")
        # 従来画面で保存したスタイルを空欄にせず、未編集として引き継ぐ。
        assert await page.evaluate("document.getElementById('setting-comment_bubble_style').value") == 'cute'
        assert not await page.evaluate("document.getElementById('authenticate').disabled")
        await page.evaluate("document.getElementById('setting-channel_name').value = 'edited_channel'; document.getElementById('setting-channel_name').dispatchEvent(new Event('input'))")
        # ポーリングがフォームの入力途中を上書きしない。
        await asyncio.sleep(1.2)
        assert await page.evaluate("document.getElementById('setting-channel_name').value") == 'edited_channel'
        assert await page.evaluate("document.getElementById('authenticate').disabled")
        await page.evaluate("document.getElementById('settings-form').requestSubmit()")
        await page.wait("document.getElementById('settings-dirty').textContent === '保存済み'")
        assert bridge.snapshot()['settings']['values']['channel_name'] == 'edited_channel'
        assert bridge.snapshot()['settings']['values']['comment_bubble_style'] == 'cute'
        assert await page.evaluate("document.getElementById('setting-obs_password').value") == ''
        await page.screenshot(output / "web-settings.png")
        # 従来の全スタイルを新画面でも保存でき、再度開いても選択を保持する。
        for style in ('classic', 'modern', 'box', 'bubble', 'neon', 'minimal', 'cute'):
            await page.evaluate(f"document.getElementById('setting-comment_bubble_style').value = '{style}'; document.getElementById('settings-form').requestSubmit()")
            await page.wait("!document.getElementById('settings-fields').disabled")
            assert bridge.snapshot()['settings']['values']['comment_bubble_style'] == style
            await page.evaluate("document.getElementById('close-settings').click(); document.getElementById('settings').click()")
            assert await page.evaluate("document.getElementById('setting-comment_bubble_style').value") == style
            assert not await page.evaluate("document.getElementById('authenticate').disabled")
        # 全テーマが実際の配色へ反映される。
        colors = set()
        for theme in ('default', 'minimal', 'gradient', 'cyberpunk'):
            await page.evaluate(f"document.getElementById('setting-ui_theme').value = '{theme}'; document.getElementById('settings-form').requestSubmit()")
            expected = {'default': 'dark', 'minimal': 'light'}.get(theme, theme)
            await page.wait(f"document.documentElement.dataset.theme === '{expected}'")
            await page.wait("!document.getElementById('settings-fields').disabled")
            colors.add(await page.evaluate("getComputedStyle(document.body).backgroundColor"))
        assert len(colors) == 4
        await page.evaluate("document.getElementById('close-settings').click()")
        assert not await page.evaluate("!document.getElementById('settings-panel').hidden")

        # 設定はモーダルではなく、チャットを隠さずに編集する。
        await page.evaluate("document.querySelector('[data-settings-target=音声]').click()")
        await page.wait("document.getElementById('settings-title').textContent === '音声の設定'")
        assert not await page.evaluate("document.querySelector('dialog[open]') !== null")
        await page.evaluate("document.getElementById('setting-edge_tts_voice').value = 'ja-JP-KeitaNeural'; document.getElementById('setting-edge_tts_voice').dispatchEvent(new Event('input'))")
        await page.evaluate("document.querySelector('[data-settings-target=字幕]').click()")
        await page.wait("document.getElementById('settings-title').textContent === '字幕の設定'")
        await page.evaluate("document.getElementById('setting-subtitle_enabled').click(); document.getElementById('setting-subtitle_text_color').value = '#aaffcc'; document.getElementById('setting-subtitle_text_color').dispatchEvent(new Event('input'))")
        assert await page.evaluate("getComputedStyle(document.getElementById('subtitle-sample')).color") == "rgb(170, 255, 204)"
        assert await page.evaluate("document.getElementById('setting-edge_tts_voice').value") == 'ja-JP-KeitaNeural'
        await page.evaluate("document.getElementById('settings-form').requestSubmit()")
        await page.wait("document.getElementById('settings-dirty').textContent === '保存済み'")
        await page.screenshot(output / "web-subtitles.png")
        # Escapeは閉じて、呼び出したナビゲーションにフォーカスを戻す。
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.wait("document.getElementById('settings-panel').hidden")
        assert await page.evaluate("document.activeElement.dataset.settingsTarget") == '字幕'

        await page.evaluate("document.querySelector('[data-layout-choice=focus]').click()")
        await page.wait("document.body.dataset.layout === 'focus'")
        await page.wait("!document.getElementById('controls').disabled")
        assert bridge.snapshot()['settings']['values']['web_workspace_layout'] == 'focus'
        await page.screenshot(output / "web-focus.png")
        await page.call("Page.reload")
        await page.wait("document.getElementById('connection-alert')?.hidden === true")
        await page.wait("document.body.dataset.layout === 'focus'")
        # 最小ウィンドウでも日常の操作がスクロールに埋もれない。
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 780, "height": 620, "deviceScaleFactor": 1, "mobile": False})
        for layout in ('focus', 'studio'):
            await page.evaluate(f"document.querySelector('[data-layout-choice={layout}]').click()")
            await page.wait(f"document.body.dataset.layout === '{layout}'")
            await page.wait("!document.getElementById('controls').disabled")
            assert await page.evaluate("['start-stop','translation','volume','speed','tts','voice'].every(id => { const r = document.getElementById(id).getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })")
            assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight")
            await page.screenshot(output / f"web-{layout}-minimum.png")
        await page.call("Emulation.setDeviceMetricsOverride", {"width": 1180, "height": 850, "deviceScaleFactor": 1, "mobile": False})

        # 音声の実測状態を表示し、OFF・通信断で古いメーターを残さない。
        snapshot = bridge.snapshot()
        snapshot.update(voice_active=True, mic_level=75, voice_processing=True, tts_speaking=True)
        bridge.publish(snapshot)
        await page.wait("document.getElementById('mic-level').value === 75")
        assert await page.evaluate("document.getElementById('mic-status').textContent") == '音声を翻訳中…'
        assert await page.evaluate("document.getElementById('tts-status').textContent") == '読み上げ中'
        await page.evaluate("document.getElementById('voice').click()")
        await page.wait("document.getElementById('mic-level').value === 0")

        dock = await open_page(server.launch_url(dock=True), 360, 800)
        assert await dock.evaluate("getComputedStyle(document.querySelector('.chat-panel')).display") == "none"
        assert not await dock.evaluate("document.documentElement.scrollWidth > innerWidth")
        assert await dock.evaluate("document.getElementById('volume').value") == "37"
        await dock.screenshot(output / "web-dock.png")
        await dock.evaluate("document.getElementById('translation').click()")
        await page.wait("document.getElementById('translation').checked === true")

        await page.evaluate("document.getElementById('autoscroll').click()")
        state = bridge.snapshot()
        state["comments"].append({"id": "4", "name": "新しいコメント", "time": "20:42", "message": "表示を一時停止", "translated": "Paused"})
        bridge.publish(state)
        await page.wait("document.getElementById('feed-status').textContent.includes('新しいコメント')")
        assert await page.evaluate("document.querySelectorAll('.comment').length") == 3
        await page.evaluate("document.getElementById('autoscroll').click()")
        await page.wait("document.querySelectorAll('.comment').length === 4")

        await page.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False})
        assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth")
        await page.screenshot(output / "web-narrow.png")
        await page.call("Page.bringToFront")
        await page.evaluate("document.getElementById('help').focus()")
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "unmodifiedText": "\r", "windowsVirtualKeyCode": 13})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
        await page.wait("document.getElementById('help-dialog').open")
        await page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        await page.wait("!document.getElementById('help-dialog').open")

        await dock.call("Page.close")
        assert bridge.snapshot()["connection"] == "connected"
        await asyncio.to_thread(server.close)
        await page.wait("!document.getElementById('connection-alert').hidden")
        assert await page.evaluate("document.getElementById('controls').disabled")
        assert await page.evaluate("document.getElementById('mic-level').value") == 0
        assert await page.evaluate("document.querySelectorAll('.comment').length") == 4
        assert not page.errors and not dock.errors
        await page.socket.close()
        await dock.socket.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", default="build/web-ui-previews")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bridge = ControlBridge()
    bridge.publish({
        "version": "1.9.3 / UI検証", "channel": "demo_channel", "authenticated": True,
        "connection": "connected", "can_stop": True, "translation_enabled": True,
        "language_mode": "自動", "include_name": False, "tts_volume": 80,
        "tts_speed": 1, "tts_active": True, "voice_active": False,
        "overlay_url": "http://localhost:8080/chat",
        "comments": [
            {"id": "1", "name": "はる", "time": "20:40", "message": "こんばんは！今日の配信も楽しみです 🌿", "translated": "Good evening! Looking forward to today's stream."},
            {"id": "2", "name": "Alex", "time": "20:41", "message": "The atmosphere here is so cozy. Hello from overseas!", "translated": "とても居心地がいいですね。海外からこんにちは！"},
            {"id": "3", "name": "表示テスト", "time": "20:41", "message": '<img src=x onerror="window.untrustedCommentExecuted=true"> も文字として表示', "translated": "This is a display test, not a live Twitch session."},
        ],
    })
    initial = bridge.snapshot()
    initial.update(desktop=True, settings=settings_snapshot(SimpleNamespace(config={"comment_bubble_style": "cute"})),
                   jobs=[], devices={"microphones": [{"index": 2, "name": "検証用マイク"}], "voices": []})
    bridge.publish(initial)
    stop = Event()
    def apply(command):
        state = bridge.snapshot()
        action = command["action"]
        mapping = {"voice": "voice_active", "tts": "tts_active", "volume": "tts_volume", "speed": "tts_speed", "translation": "translation_enabled", "include_name": "include_name", "language": "language_mode"}
        if action in mapping:
            state[mapping[action]] = command["value"]
        elif action == "save_settings":
            state["settings"]["values"].update(command["value"])
            if "channel_name" in command["value"]:
                state["channel"] = command["value"]["channel_name"]
        elif action in ("start", "stop"):
            state["connection"] = "connected" if action == "start" else "stopped"
            state["can_stop"] = action == "start"
        bridge.publish(state)
        return state
    def owner():
        while not stop.wait(0.01):
            bridge.drain(apply)
    server = WebUIServer(bridge)
    server.start()
    thread = Thread(target=owner, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="kototsuna-browser-") as profile:
            process = subprocess.Popen([
                args.chromium, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
                "--disable-background-networking", "--no-first-run", "--no-default-browser-check",
                "--user-data-dir=" + profile, "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                port_file = Path(profile) / "DevToolsActivePort"
                for _ in range(100):
                    if port_file.exists():
                        break
                    time.sleep(0.05)
                port = int(port_file.read_text().splitlines()[0])
                asyncio.run(check(port, server, bridge, output))
            finally:
                process.terminate()
                process.wait(timeout=10)
    finally:
        stop.set()
        thread.join(timeout=2)
        server.close()
    print("Browser checks passed: controls, themes, reload, dock sync, pause, keyboard, XSS, offline.")
    print("Screenshots: " + str(output.resolve()))


if __name__ == "__main__":
    main()
