"""TranslateBot クラスのテスト"""
import asyncio
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock


def _make_author(
    name: str = "testuser",
    display_name: str = "TestUser",
    is_mod: bool = False,
) -> Mock:
    author = Mock()
    author.name = name
    author.display_name = display_name
    author.is_mod = is_mod
    author.is_subscriber = False
    author.badges = {}
    return author


def _make_message(content: str, author: Mock) -> Mock:
    message = Mock()
    message.content = content
    message.author = author
    message.channel = Mock()
    message.channel.send = AsyncMock()
    return message


def _make_bot():
    from src.bot import TranslateBot

    command_store = Mock()
    command_store.get.return_value = None
    command_store.list_all.return_value = []
    tracker = Mock()
    tracker.check_message.return_value = False
    emote_provider = Mock()
    emote_provider.detect_emotes.return_value = []
    plugin_manager = Mock()
    plugin_manager.count = 0
    viewer_store = Mock()

    with patch("src.bot.commands.Bot.__init__", return_value=None), \
         patch("src.bot.get_tts_instance", return_value=Mock()), \
         patch("src.bot.get_tracker", return_value=tracker), \
         patch("src.bot.CommandStore", return_value=command_store), \
         patch("src.bot.EmoteProvider", return_value=emote_provider), \
         patch("src.bot.get_viewer_store", return_value=viewer_store), \
         patch("src.bot.get_plugin_manager", return_value=plugin_manager), \
         patch("src.bot.load_config", return_value={"commands_enabled": True}):
        bot = TranslateBot(
            token="oauth:test-token",
            channel="testchannel",
            get_lang_mode=lambda: "自動",
            gui_ref=Mock(),
            tts_enabled_getter=lambda: False,
            tts_include_name_getter=lambda: False,
            client_id=None,
        )

    return bot


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
            "channel_name": "test_channel",
            "translate_mode": "自動",
            "chat_translation_enabled": True,
        }

        # イベントハンドラは実際のTwitch接続が必要なため、
        # モックでの基本テストのみ
        from src.bot import TranslateBot
        assert TranslateBot is not None


class TestBotCommands:
    """TranslateBot のビルトインコマンドを検証する。"""

    def test_help_includes_dict_command(self):
        bot = _make_bot()
        message = _make_message("!help", _make_author())

        consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        sent_message = message.channel.send.await_args.args[0]
        assert "!dict" in sent_message

    def test_dict_add_command_persists_entry_for_moderator(self, tmp_path):
        bot = _make_bot()
        author = _make_author(is_mod=True)
        message = _make_message("!dict add 漢字 かんじ", author)

        from src.tts_dictionary import TTSDictionary

        dictionary_path = tmp_path / "tts_dictionary.json"
        dictionary = TTSDictionary(str(dictionary_path))

        with patch("src.bot.get_dictionary", return_value=dictionary):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        assert dictionary.apply_dictionary("漢字の読み上げ") == "かんじの読み上げ"
        saved = json.loads(dictionary_path.read_text(encoding="utf-8"))
        assert saved == {"漢字": "かんじ"}
        message.channel.send.assert_awaited_once_with(
            "辞書に追加しました: 漢字 → かんじ" + '\u200B'
        )

    def test_dict_add_command_requires_moderator(self):
        bot = _make_bot()
        message = _make_message("!dict add 漢字 かんじ", _make_author(is_mod=False))

        with patch("src.bot.get_dictionary") as mock_get_dictionary:
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        mock_get_dictionary.assert_not_called()
        message.channel.send.assert_awaited_once_with(
            "このコマンドはモデレーター以上が必要です" + '\u200B'
        )

    def test_dict_add_command_requires_word_and_reading(self):
        bot = _make_bot()
        message = _make_message("!dict add 漢字", _make_author(is_mod=True))

        with patch("src.bot.get_dictionary") as mock_get_dictionary:
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        mock_get_dictionary.assert_not_called()
        message.channel.send.assert_awaited_once_with(
            "使い方: !dict add <単語> <読み>" + '\u200B'
        )

    def test_dict_list_command_shows_entries(self, tmp_path):
        bot = _make_bot()
        author = _make_author(is_mod=True)
        message = _make_message("!dict list", author)

        from src.tts_dictionary import TTSDictionary

        dictionary_path = tmp_path / "tts_dictionary.json"
        dictionary = TTSDictionary(str(dictionary_path))
        dictionary.add_word("漢字", "かんじ")
        dictionary.add_word("英語", "えいご")

        with patch("src.bot.get_dictionary", return_value=dictionary):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "漢字→かんじ" in sent or "英語→えいご" in sent

    def test_process_test_message_runs_command_and_hides_invocation(self):
        bot = _make_bot()

        with patch("src.bot.load_config", return_value={"chat_translation_enabled": False}), \
             patch("src.bot.fortune", return_value="大吉"):
            asyncio.run(
                bot.process_test_message(
                    username="testuser",
                    content="!fortune",
                    tags={"id": "test-1", "badges": {}},
                    display_name="TestUser",
                )
            )

        bot.gui.on_comment_received.assert_called_once()
        response = bot.gui.on_comment_received.call_args.args[0]
        assert response.message == "@TestUser 大吉"
        assert response.raw_data["suppress_subtitle"] is True
        assert response.raw_data["tester_generated"] is True

    def test_process_test_message_uses_normal_chat_path_for_plain_text(self):
        bot = _make_bot()

        with patch("src.bot.load_config", return_value={"chat_translation_enabled": False}):
            asyncio.run(
                bot.process_test_message(
                    username="testuser",
                    content="こんにちは",
                    tags={"id": "test-2", "badges": {}},
                    display_name="TestUser",
                )
            )

        bot.gui.on_comment_received.assert_called_once()
        comment = bot.gui.on_comment_received.call_args.args[0]
        assert comment.message == "こんにちは"
        assert comment.display_name == "TestUser"
        assert comment.raw_data.get("tester_generated") is None
        assert comment.raw_data.get("suppress_subtitle") is None

    def test_dict_list_command_empty(self, tmp_path):
        bot = _make_bot()
        author = _make_author(is_mod=True)
        message = _make_message("!dict list", author)

        from src.tts_dictionary import TTSDictionary

        dictionary_path = tmp_path / "tts_dictionary.json"
        dictionary = TTSDictionary(str(dictionary_path))

        with patch("src.bot.get_dictionary", return_value=dictionary):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        message.channel.send.assert_awaited_once_with("辞書は空です" + '\u200B')

    def test_dict_remove_command_removes_entry(self, tmp_path):
        bot = _make_bot()
        author = _make_author(is_mod=True)
        message = _make_message("!dict remove 漢字", author)

        from src.tts_dictionary import TTSDictionary

        dictionary_path = tmp_path / "tts_dictionary.json"
        dictionary = TTSDictionary(str(dictionary_path))
        dictionary.add_word("漢字", "かんじ")

        with patch("src.bot.get_dictionary", return_value=dictionary):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        message.channel.send.assert_awaited_once_with("辞書から削除しました: 漢字" + '\u200B')
        assert dictionary.apply_dictionary("漢字") == "漢字"

    def test_dict_remove_command_not_found(self, tmp_path):
        bot = _make_bot()
        author = _make_author(is_mod=True)
        message = _make_message("!dict remove 存在しない", author)

        from src.tts_dictionary import TTSDictionary

        dictionary_path = tmp_path / "tts_dictionary.json"
        dictionary = TTSDictionary(str(dictionary_path))

        with patch("src.bot.get_dictionary", return_value=dictionary):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "登録されていません" in sent

    def test_dict_unknown_subcommand_shows_usage(self):
        bot = _make_bot()
        message = _make_message("!dict foo", _make_author(is_mod=True))

        with patch("src.bot.get_dictionary"):
            consumed = asyncio.run(bot._handle_command(message))

        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "!dict add" in sent and "!dict list" in sent and "!dict remove" in sent


class TestParticipantCommands:
    """参加者管理コマンドのテスト"""

    def _make_tracker(self):
        from src.participant_tracker import ParticipantTracker
        t = ParticipantTracker()
        t.enable()
        return t

    def test_leave_removes_self_from_list(self):
        tracker = self._make_tracker()
        tracker.add_participant("Alice", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!leave", _make_author(name="alice", display_name="Alice"))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        assert "Alice" not in tracker.get_participant_names()
        sent = message.channel.send.await_args.args[0]
        assert "退出" in sent

    def test_leave_when_not_in_list(self):
        tracker = self._make_tracker()
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!leave", _make_author(name="nobody", display_name="Nobody"))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "登録されていません" in sent

    def test_remove_requires_mod(self):
        bot = _make_bot()
        bot.tracker = self._make_tracker()
        message = _make_message("!remove alice", _make_author(is_mod=False))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "モデレーター" in sent

    def test_remove_removes_user(self):
        tracker = self._make_tracker()
        tracker.add_participant("alice", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!remove alice", _make_author(is_mod=True))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        assert "alice" not in tracker.get_participant_names()
        sent = message.channel.send.await_args.args[0]
        assert "削除" in sent

    def test_clearall_requires_mod(self):
        bot = _make_bot()
        bot.tracker = self._make_tracker()
        message = _make_message("!clearall", _make_author(is_mod=False))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "モデレーター" in sent

    def test_clearall_clears_list(self):
        tracker = self._make_tracker()
        tracker.add_participant("alice", "参加", "参加")
        tracker.add_participant("bob", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!clearall", _make_author(is_mod=True))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        assert tracker.get_count() == 0
        sent = message.channel.send.await_args.args[0]
        assert "クリア" in sent

    def test_nextround_moves_to_participated(self):
        tracker = self._make_tracker()
        tracker.add_participant("alice", "参加", "参加")
        tracker.add_participant("bob", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!nextround", _make_author(is_mod=True))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        assert tracker.get_count() == 0
        assert tracker.get_participated_count() == 2
        # alice と bob は再参加できない
        assert not tracker.add_participant("alice", "参加", "参加")

    def test_roundreset_allows_rejoin(self):
        tracker = self._make_tracker()
        tracker.add_participant("alice", "参加", "参加")
        tracker.mark_all_as_participated()
        assert not tracker.add_participant("alice", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!roundreset", _make_author(is_mod=True))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        assert tracker.get_participated_count() == 0
        # リセット後は再参加可能
        assert tracker.add_participant("alice", "参加", "参加")

    def test_help_includes_participant_commands(self):
        bot = _make_bot()
        message = _make_message("!help", _make_author())
        asyncio.run(bot._handle_command(message))
        sent = message.channel.send.await_args.args[0]
        assert "!leave" in sent
        assert "!nextround" in sent
        assert "!roundreset" in sent
        assert "!played" in sent

    def test_played_marks_user_as_participated(self):
        tracker = self._make_tracker()
        tracker.add_participant("Alice", "参加", "参加")
        tracker.add_participant("Bob", "参加", "参加")
        bot = _make_bot()
        bot.tracker = tracker
        message = _make_message("!played Alice", _make_author(is_mod=True))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        # Aliceは待機リストから消えて参加済みになる
        assert "Alice" not in tracker.get_participant_names()
        assert tracker.get_participated_count() == 1
        # Bobはまだ待機リストにいる
        assert "Bob" in tracker.get_participant_names()
        sent = message.channel.send.await_args.args[0]
        assert "参加済み" in sent

    def test_played_requires_mod(self):
        bot = _make_bot()
        bot.tracker = self._make_tracker()
        message = _make_message("!played alice", _make_author(is_mod=False))
        consumed = asyncio.run(bot._handle_command(message))
        assert consumed is True
        sent = message.channel.send.await_args.args[0]
        assert "モデレーター" in sent

    def test_played_then_cannot_rejoin_until_roundreset(self):
        tracker = self._make_tracker()
        tracker.add_participant("Alice", "参加", "参加")
        tracker.mark_as_participated("Alice")
        # 参加済みなので再登録できない
        assert not tracker.add_participant("Alice", "参加", "参加")
        # ラウンドリセット後は再登録できる
        tracker.reset_participated()
        assert tracker.add_participant("Alice", "参加", "参加")
