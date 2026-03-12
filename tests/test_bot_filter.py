"""
src/bot_filter.py のユニットテスト (Issue #145)
"""
import pytest
from src.bot_filter import BotFilter


class TestBotFilter:
    def test_default_bots_are_filtered(self):
        bf = BotFilter()
        assert bf.is_bot("Nightbot") is True
        assert bf.is_bot("nightbot") is True
        assert bf.is_bot("STREAMLABS") is True
        assert bf.is_bot("Fossabot") is True

    def test_normal_user_not_filtered(self):
        bf = BotFilter()
        assert bf.is_bot("normaluser") is False
        assert bf.is_bot("yukky123") is False
        assert bf.is_bot("") is False

    def test_disabled_skips_all(self):
        bf = BotFilter(enabled=False)
        assert bf.is_bot("nightbot") is False
        assert bf.is_bot("streamlabs") is False

    def test_custom_bot_is_filtered(self):
        bf = BotFilter(custom_bots=["MyBot"])
        assert bf.is_bot("mybot") is True
        assert bf.is_bot("MyBot") is True
        assert bf.is_bot("MYBOT") is True

    def test_add_custom_bot(self):
        bf = BotFilter()
        assert bf.is_bot("newbot") is False
        bf.add_custom("NewBot")
        assert bf.is_bot("newbot") is True
        assert bf.is_bot("NEWBOT") is True

    def test_remove_custom_bot(self):
        bf = BotFilter(custom_bots=["mybot"])
        bf.remove_custom("mybot")
        assert bf.is_bot("mybot") is False

    def test_remove_nonexistent_does_not_raise(self):
        bf = BotFilter()
        bf.remove_custom("doesnotexist")  # エラーにならないことを確認

    def test_list_custom_sorted(self):
        bf = BotFilter(custom_bots=["zebra", "alpha", "middle"])
        assert bf.list_custom() == ["alpha", "middle", "zebra"]

    def test_to_config(self):
        bf = BotFilter(enabled=True, custom_bots=["mybot"])
        cfg = bf.to_config()
        assert cfg["bot_filter_enabled"] is True
        assert "mybot" in cfg["bot_filter_custom"]

    def test_to_config_disabled(self):
        bf = BotFilter(enabled=False)
        cfg = bf.to_config()
        assert cfg["bot_filter_enabled"] is False

    def test_whitespace_in_custom(self):
        bf = BotFilter()
        bf.add_custom("  mybot  ")
        assert bf.is_bot("mybot") is True
