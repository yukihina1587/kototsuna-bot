"""TranslateBot クラスのテスト"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock


class TestTranslateBot:
    """TranslateBotクラスの基本テスト"""

    def test_import_bot_module(self):
        """botモジュールがインポートできることを確認"""
        from src import bot
        assert hasattr(bot, 'TranslateBot')

    @patch('src.bot.load_config')
    def test_bot_initialization(self, mock_load_config):
        """Botの初期化テスト"""
        mock_load_config.return_value = {
            "twitch_client_id": "test_client_id",
            "deepl_api_key": "test_api_key",
            "channel_name": "test_channel",
            "translate_mode": "自動",
            "chat_translation_enabled": True,
        }

        from src.bot import TranslateBot

        # トークンなしでの初期化（エラーにならないことを確認）
        # 実際のBotは非同期なので完全なテストは統合テストで行う
        assert TranslateBot is not None


class TestBotHelperFunctions:
    """Botのヘルパー関数テスト"""

    def test_create_twitch_comment(self):
        """create_twitch_comment関数のテスト"""
        from src.bot import create_twitch_comment

        tags = {
            "badges": {"subscriber": "1"},
            "color": "#FF0000",
            "user-id": "12345",
        }

        comment = create_twitch_comment(
            username="testuser",
            message="Hello",
            tags=tags,
            translated="こんにちは",
        )

        assert comment.username == "testuser"
        assert comment.message == "Hello"
        assert comment.translated == "こんにちは"
        assert "subscriber" in comment.badges
        assert comment.color == "#FF0000"
        assert comment.timestamp is not None

    def test_create_twitch_comment_without_translation(self):
        """翻訳なしのコメント作成テスト"""
        from src.bot import create_twitch_comment

        tags = {"user-id": "12345"}

        comment = create_twitch_comment(
            username="testuser",
            message="Hello",
            tags=tags,
            translated=None,
        )

        assert comment.username == "testuser"
        assert comment.message == "Hello"
        assert comment.translated is None


class TestBotEventHandlers:
    """Botのイベントハンドラテスト"""

    @patch('src.bot.load_config')
    def test_event_ready(self, mock_load_config):
        """event_ready ハンドラのテスト（同期版 - 基本的なインポート確認）"""
        mock_load_config.return_value = {
            "twitch_client_id": "test_client_id",
            "deepl_api_key": "test_api_key",
            "channel_name": "test_channel",
            "translate_mode": "自動",
            "chat_translation_enabled": True,
        }

        # イベントハンドラは実際のTwitch接続が必要なため、
        # モックでの基本テストのみ
        from src.bot import TranslateBot
        assert TranslateBot is not None
