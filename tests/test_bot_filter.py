"""tests/test_bot_filter.py — BotFilter ユニットテスト"""
import pytest
from src.bot_filter import BotFilter, get_bot_filter, reset_bot_filter


class TestBotFilterDefaultBots:
    def test_known_bot_is_filtered(self):
        bf = BotFilter()
        assert bf.is_bot("nightbot") is True

    def test_known_bot_case_insensitive(self):
        bf = BotFilter()
        assert bf.is_bot("Nightbot") is True
        assert bf.is_bot("NIGHTBOT") is True
        assert bf.is_bot("NightBot") is True

    def test_normal_user_not_filtered(self):
        bf = BotFilter()
        assert bf.is_bot("normaluser") is False
        assert bf.is_bot("viewer123") is False

    def test_all_default_bots_are_filtered(self):
        bf = BotFilter()
        for bot_name in BotFilter.DEFAULT_BOTS:
            assert bf.is_bot(bot_name) is True, f"{bot_name} should be filtered"

    def test_streamlabs_variants(self):
        bf = BotFilter()
        assert bf.is_bot("streamlabs") is True
        assert bf.is_bot("streamlabs_chatbot") is True
        assert bf.is_bot("streamelements") is True


class TestBotFilterEnabled:
    def test_disabled_does_not_filter_known_bot(self):
        bf = BotFilter(enabled=False)
        assert bf.is_bot("nightbot") is False

    def test_disabled_does_not_filter_custom_bot(self):
        bf = BotFilter(enabled=False, custom_bots=["mybot"])
        assert bf.is_bot("mybot") is False

    def test_enabled_by_default(self):
        bf = BotFilter()
        assert bf.enabled is True


class TestBotFilterCustomBots:
    def test_custom_bot_is_filtered(self):
        bf = BotFilter(custom_bots=["mybot"])
        assert bf.is_bot("mybot") is True

    def test_custom_bot_case_insensitive(self):
        bf = BotFilter(custom_bots=["MyBot"])
        assert bf.is_bot("mybot") is True
        assert bf.is_bot("MYBOT") is True

    def test_add_custom_bot(self):
        bf = BotFilter()
        assert bf.is_bot("newbot") is False
        bf.add_custom("newbot")
        assert bf.is_bot("newbot") is True

    def test_remove_custom_bot(self):
        bf = BotFilter(custom_bots=["oldbot"])
        assert bf.is_bot("oldbot") is True
        bf.remove_custom("oldbot")
        assert bf.is_bot("oldbot") is False

    def test_remove_nonexistent_bot_does_not_raise(self):
        bf = BotFilter()
        bf.remove_custom("doesnotexist")  # 例外が出ないこと

    def test_get_custom_bots_sorted(self):
        bf = BotFilter(custom_bots=["zbot", "abot", "mbot"])
        assert bf.get_custom_bots() == ["abot", "mbot", "zbot"]


class TestBotFilterProtectedNames:
    def test_protected_channel_owner_not_filtered(self):
        """チャンネルオーナーは BOT 名と一致しても除外されない（誤 BAN 対策）"""
        bf = BotFilter()
        # チャンネルオーナーが nightbot という名前でも除外されない
        assert bf.is_bot("nightbot", protected_names={"nightbot"}) is False

    def test_protected_self_not_filtered(self):
        """認証ユーザー（配信者自身）は除外されない"""
        bf = BotFilter(custom_bots=["streamer123"])
        assert bf.is_bot("streamer123", protected_names={"streamer123"}) is False

    def test_non_protected_still_filtered(self):
        """protected でない既知 BOT は通常通りフィルタリングされる"""
        bf = BotFilter()
        assert bf.is_bot("nightbot", protected_names={"other_user"}) is True

    def test_protected_case_insensitive(self):
        """protected_names との比較は大文字小文字を無視する"""
        bf = BotFilter(custom_bots=["MyChannel"])
        assert bf.is_bot("mychannel", protected_names={"MyChannel"}) is False

    def test_empty_protected_names(self):
        bf = BotFilter()
        assert bf.is_bot("nightbot", protected_names=set()) is True

    def test_none_protected_names(self):
        bf = BotFilter()
        assert bf.is_bot("nightbot", protected_names=None) is True


class TestBotFilterToConfig:
    def test_to_config(self):
        bf = BotFilter(enabled=True, custom_bots=["bot1", "bot2"])
        cfg = bf.to_config()
        assert cfg["bot_filter_enabled"] is True
        assert cfg["bot_filter_custom"] == ["bot1", "bot2"]

    def test_to_config_disabled(self):
        bf = BotFilter(enabled=False)
        cfg = bf.to_config()
        assert cfg["bot_filter_enabled"] is False
        assert cfg["bot_filter_custom"] == []


class TestBotFilterSingleton:
    def setup_method(self):
        reset_bot_filter()

    def teardown_method(self):
        reset_bot_filter()

    def test_get_bot_filter_returns_instance(self):
        bf = get_bot_filter()
        assert isinstance(bf, BotFilter)

    def test_get_bot_filter_singleton(self):
        bf1 = get_bot_filter()
        bf2 = get_bot_filter()
        assert bf1 is bf2

    def test_reset_creates_new_instance(self):
        bf1 = get_bot_filter()
        reset_bot_filter()
        bf2 = get_bot_filter()
        assert bf1 is not bf2
