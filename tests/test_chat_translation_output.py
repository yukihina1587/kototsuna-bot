"""Exercise local translation output and optional Twitch delivery without a connection."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from src import bot as bot_module


@pytest.fixture
def chat_pipeline(monkeypatch):
    config = {
        "chat_translation_enabled": True,
        "archive_enabled": False,
        "welcome_enabled": False,
        "commands_enabled": False,
        "bot_filter_enabled": False,
    }
    tracker = Mock()
    tracker.check_message.return_value = False
    emotes = Mock()
    emotes.detect_emotes.return_value = []
    viewers = Mock()
    viewers.get_assigned_voice.return_value = None
    plugins = Mock()
    plugins.count = 0
    tts = Mock()
    gui = Mock(spec=["on_comment_received", "log_message"])
    translate = AsyncMock(return_value="こんにちは")

    monkeypatch.setattr(bot_module, "load_config", lambda: config)
    monkeypatch.setattr(bot_module, "get_tts_instance", lambda: tts)
    monkeypatch.setattr(bot_module, "get_tracker", lambda: tracker)
    monkeypatch.setattr(bot_module, "CommandStore", Mock)
    monkeypatch.setattr(bot_module, "EmoteProvider", lambda: emotes)
    monkeypatch.setattr(bot_module, "get_viewer_store", lambda: viewers)
    monkeypatch.setattr(bot_module, "get_plugin_manager", lambda: plugins)
    monkeypatch.setattr(bot_module, "translate_text_batched", translate)
    bot = bot_module.TranslateBot.create_test_dispatcher(
        token="",
        channel="testchannel",
        get_lang_mode=lambda: "英→日",
        gui_ref=gui,
        tts_enabled_getter=lambda: True,
        tts_include_name_getter=lambda: False,
    )
    message = SimpleNamespace(
        content="Hello",
        author=SimpleNamespace(
            name="viewer", display_name="Viewer", is_mod=False,
            is_subscriber=False, badges={},
        ),
        tags={"id": "comment-1", "badges": {}},
        echo=False,
        channel=SimpleNamespace(send=AsyncMock()),
    )
    return SimpleNamespace(
        bot=bot, config=config, gui=gui, tts=tts, message=message, translate=translate,
    )


def assert_local_translation(pipeline):
    pipeline.gui.on_comment_received.assert_called_once()
    comment = pipeline.gui.on_comment_received.call_args.args[0]
    assert comment.message == "Hello"
    assert comment.translated == "こんにちは"
    pipeline.tts.speak.assert_called_once_with("こんにちは", speaker_id=None)


@pytest.mark.parametrize("posting", [None, False, "true", 1])
def test_local_translation_without_posting(chat_pipeline, posting):
    pipeline = chat_pipeline
    if posting is not None:
        pipeline.config["chat_translation_post_to_twitch"] = posting
    pipeline.config["translate_mode_2"] = "日→英"

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    assert_local_translation(pipeline)
    pipeline.message.channel.send.assert_not_awaited()
    pipeline.translate.assert_awaited_once_with("Hello", "英→日")


def test_opt_in_posts_after_local_output(chat_pipeline):
    pipeline = chat_pipeline
    pipeline.config["chat_translation_post_to_twitch"] = True

    async def send_after_local_output(_text):
        assert_local_translation(pipeline)

    pipeline.message.channel.send.side_effect = send_after_local_output
    asyncio.run(pipeline.bot.event_message(pipeline.message))

    pipeline.message.channel.send.assert_awaited_once_with("[Chat] こんにちは\u200B")


def test_post_failure_preserves_local_output(chat_pipeline, monkeypatch):
    pipeline = chat_pipeline
    pipeline.config["chat_translation_post_to_twitch"] = True
    pipeline.message.channel.send.side_effect = RuntimeError("private transport detail")
    logger = Mock()
    monkeypatch.setattr(bot_module, "logger", logger)

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    assert_local_translation(pipeline)
    logger.warning.assert_called_once_with(
        "Optional chat translation post failed (%s)", "RuntimeError",
    )
    pipeline.gui.log_message.assert_called_once()
    assert "private transport detail" not in str(pipeline.gui.log_message.call_args)


def test_opt_in_preserves_second_language_posts(chat_pipeline):
    pipeline = chat_pipeline
    pipeline.config.update({
        "chat_translation_post_to_twitch": True, "translate_mode_2": "日→英",
    })
    pipeline.translate.side_effect = ["<k>こんにちは</k>", "<k>Hi there</k>"]

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    assert_local_translation(pipeline)
    assert pipeline.translate.await_args_list == [call("Hello", "英→日"), call("Hello", "日→英")]
    assert pipeline.message.channel.send.await_args_list == [
        call("[Chat] こんにちは\u200B"), call("[Chat2] Hi there\u200B"),
    ]


def test_second_language_failure_preserves_local_output(chat_pipeline):
    pipeline = chat_pipeline
    pipeline.config.update({
        "chat_translation_post_to_twitch": True, "translate_mode_2": "日→英",
    })
    pipeline.translate.side_effect = ["こんにちは", RuntimeError("translation failed")]

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    assert_local_translation(pipeline)
    pipeline.message.channel.send.assert_awaited_once_with("[Chat] こんにちは\u200B")


def test_disabled_translation_keeps_original_without_posting(chat_pipeline):
    pipeline = chat_pipeline
    pipeline.config.update({
        "chat_translation_enabled": False, "chat_translation_post_to_twitch": True,
    })

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    pipeline.translate.assert_not_awaited()
    pipeline.message.channel.send.assert_not_awaited()
    comment = pipeline.gui.on_comment_received.call_args.args[0]
    assert comment.message == "Hello"
    assert comment.translated is None
    pipeline.tts.speak.assert_called_once_with("Hello", speaker_id=None)


@pytest.mark.parametrize("translation", ["Hello", ""])
def test_unchanged_or_filtered_translation_is_not_posted(chat_pipeline, translation):
    pipeline = chat_pipeline
    pipeline.config["chat_translation_post_to_twitch"] = True
    pipeline.translate.return_value = translation

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    pipeline.message.channel.send.assert_not_awaited()
    comment = pipeline.gui.on_comment_received.call_args.args[0]
    assert comment.message == "Hello"
    assert comment.translated is None


@pytest.fixture
def gui_module(monkeypatch):
    pytest.importorskip("customtkinter")
    pygame = pytest.importorskip("pygame")
    monkeypatch.setattr(pygame.mixer, "init", Mock())
    from src import theme_loader
    monkeypatch.setattr(theme_loader, "load_custom_themes", lambda _themes: {})
    from src import gui
    return gui


@pytest.mark.parametrize("posting", [False, True])
def test_original_and_translation_reach_obs_data(chat_pipeline, gui_module, monkeypatch, posting):
    from src import overlay_server

    pipeline = chat_pipeline
    pipeline.config["chat_translation_post_to_twitch"] = posting
    pipeline.message.channel.send.side_effect = RuntimeError("send failed")
    monkeypatch.setattr(overlay_server, "_chat_state", {"messages": [], "max_entries": 200})
    monkeypatch.setattr(gui_module, "update_translation", Mock())
    app = gui_module.KototsunaApp.__new__(gui_module.KototsunaApp)
    app.master = SimpleNamespace(after=lambda _delay, callback: callback())
    app.log_history = []
    app.chat_history = []
    app._next_chat_entry_id = 1
    app._add_comment_tile = Mock()
    pipeline.bot.gui = app

    asyncio.run(pipeline.bot.event_message(pipeline.message))

    messages = overlay_server._chat_state["messages"]
    assert len(messages) == 1
    assert messages[0]["name_html"] == "Viewer"
    assert messages[0]["body_html"] == "Hello"
    assert messages[0]["translated_html"] == "こんにちは"
    assert pipeline.message.channel.send.await_count == int(posting)


@pytest.mark.parametrize("enabled", [False, True])
def test_posting_switch_saves_independently_of_translation(gui_module, monkeypatch, enabled):
    app = gui_module.KototsunaApp.__new__(gui_module.KototsunaApp)
    app.config = {"chat_translation_enabled": True, "translate_mode_2": "日→英"}
    app.chat_translation_post_to_twitch = Mock()
    app.chat_translation_post_to_twitch.get.return_value = enabled
    app.translate_mode_2_menu = Mock()
    app.log_message = Mock()
    save = Mock()
    monkeypatch.setattr(gui_module, "save_config", save)

    app._on_chat_translation_post_changed()

    save.assert_called_once_with({
        "chat_translation_enabled": True,
        "translate_mode_2": "日→英",
        "chat_translation_post_to_twitch": enabled,
    })
    app.translate_mode_2_menu.configure.assert_called_once_with(
        state="normal" if enabled else "disabled",
    )
