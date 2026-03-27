"""overlay_server のテスト"""
import pytest
from unittest.mock import Mock, patch


class TestOverlayServer:
    """overlay_serverモジュールのテスト"""

    def test_import_overlay_server(self):
        """overlay_serverモジュールがインポートできることを確認"""
        from src import overlay_server
        assert hasattr(overlay_server, 'start_server')
        assert hasattr(overlay_server, 'stop_server')
        assert hasattr(overlay_server, 'update_translation')

    def test_update_translation_exists(self):
        """update_translation関数が呼び出し可能であることを確認"""
        from src.overlay_server import update_translation
        assert callable(update_translation)

    def test_start_stop_server_exists(self):
        """start_server/stop_server関数が呼び出し可能であることを確認"""
        from src.overlay_server import start_server, stop_server
        assert callable(start_server)
        assert callable(stop_server)

    def test_run_server_thread_exists(self):
        """run_server_thread関数が呼び出し可能であることを確認"""
        from src.overlay_server import run_server_thread
        assert callable(run_server_thread)

    def test_update_subtitle_skips_when_disabled(self):
        """字幕が無効な間は更新を受け付けない"""
        from src import overlay_server

        with overlay_server._subtitle_lock:
            overlay_server._subtitle_state = {
                "id": 0,
                "enabled": False,
                "original": "",
                "translated": "",
                "speaker": "",
                "timestamp": "",
                "config": {},
            }

        overlay_server.update_subtitle("原文", "訳文", "speaker", {"font_size": 32})

        with overlay_server._subtitle_lock:
            assert overlay_server._subtitle_state["id"] == 0
            assert overlay_server._subtitle_state["original"] == ""
            assert overlay_server._subtitle_state["translated"] == ""

    def test_update_subtitle_updates_when_enabled(self):
        """字幕が有効なら内容と設定を更新する"""
        from src import overlay_server

        with overlay_server._subtitle_lock:
            overlay_server._subtitle_state = {
                "id": 0,
                "enabled": False,
                "original": "",
                "translated": "",
                "speaker": "",
                "timestamp": "",
                "config": {},
            }

        overlay_server.set_subtitle_enabled(True)
        overlay_server.update_subtitle("原文", "訳文", "speaker", {"font_size": 32})

        with overlay_server._subtitle_lock:
            assert overlay_server._subtitle_state["id"] == 1
            assert overlay_server._subtitle_state["enabled"] is True
            assert overlay_server._subtitle_state["original"] == "原文"
            assert overlay_server._subtitle_state["translated"] == "訳文"
            assert overlay_server._subtitle_state["speaker"] == "speaker"
            assert overlay_server._subtitle_state["config"] == {"font_size": 32}
            assert overlay_server._subtitle_state["timestamp"]

    def test_blank_overlay_html_is_transparent(self):
        """未準備時はOBSに空の透明HTMLを返せる"""
        from src.overlay_server import _blank_overlay_html

        html = _blank_overlay_html()

        assert "background:transparent" in html
        assert "<body" in html

    def test_load_overlay_html_returns_none_for_missing_file(self):
        """HTML未生成時はNoneを返して空表示へフォールバックできる"""
        from src.overlay_server import _load_overlay_html

        assert _load_overlay_html(None) is None
        assert _load_overlay_html("missing-file.html") is None

    def test_load_overlay_html_reads_existing_file(self, tmp_path):
        """既存HTMLはそのまま読み込む"""
        from src.overlay_server import _load_overlay_html

        html_path = tmp_path / "overlay.html"
        html_path.write_text("<html>ok</html>", encoding="utf-8")

        assert _load_overlay_html(str(html_path)) == "<html>ok</html>"
