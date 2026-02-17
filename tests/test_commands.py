"""src.commands モジュールのユニットテスト。

PermissionLevel, CooldownManager, check_permission, substitute_variables を検証する。
"""

import pytest
from unittest.mock import Mock, patch

from src.commands import (
    CooldownManager,
    PermissionLevel,
    check_permission,
    substitute_variables,
)


# ---------------------------------------------------------------------------
# Helper: twitchio author モックを生成
# ---------------------------------------------------------------------------


def _make_author(
    name: str = "testuser",
    display_name: str = "TestUser",
    is_mod: bool = False,
    is_subscriber: bool = False,
    badges: dict[str, str] | None = None,
) -> Mock:
    """テスト用の author Mock オブジェクトを生成する。"""
    author = Mock()
    author.name = name
    author.display_name = display_name
    author.is_mod = is_mod
    author.is_subscriber = is_subscriber
    author.badges = badges if badges is not None else {}
    return author


# ===========================================================================
# TestPermissionLevel
# ===========================================================================


class TestPermissionLevel:
    """PermissionLevel IntEnum の値と順序を検証する。"""

    def test_enum_values(self):
        """各権限レベルの数値が正しいこと。"""
        assert PermissionLevel.EVERYONE == 0
        assert PermissionLevel.SUBSCRIBER == 1
        assert PermissionLevel.VIP == 2
        assert PermissionLevel.MODERATOR == 3
        assert PermissionLevel.BROADCASTER == 4

    def test_ordering_comparison(self):
        """IntEnum として大小比較が正しく動作すること。"""
        assert PermissionLevel.EVERYONE < PermissionLevel.SUBSCRIBER
        assert PermissionLevel.SUBSCRIBER < PermissionLevel.VIP
        assert PermissionLevel.VIP < PermissionLevel.MODERATOR
        assert PermissionLevel.MODERATOR < PermissionLevel.BROADCASTER
        assert PermissionLevel.BROADCASTER > PermissionLevel.EVERYONE


# ===========================================================================
# TestCooldownManager
# ===========================================================================


class TestCooldownManager:
    """CooldownManager のグローバル / ユーザー別クールダウンを検証する。"""

    def test_initially_allowed(self):
        """記録がない状態ではすべてのコマンドが許可される。"""
        mgr = CooldownManager()
        allowed, remaining = mgr.check("!hello", "user_a", global_cd=5.0, user_cd=10.0)
        assert allowed is True
        assert remaining == 0.0

    def test_global_cooldown_blocks(self):
        """record 直後はグローバルクールダウンでブロックされる。"""
        mgr = CooldownManager()
        mgr.record("!hello", "user_a")

        allowed, remaining = mgr.check("!hello", "user_b", global_cd=5.0, user_cd=0.0)
        assert allowed is False
        assert remaining > 0.0

    def test_user_cooldown_blocks(self):
        """record 直後は同一ユーザーのクールダウンでブロックされる。"""
        mgr = CooldownManager()
        mgr.record("!hello", "user_a")

        allowed, remaining = mgr.check("!hello", "user_a", global_cd=0.0, user_cd=10.0)
        assert allowed is False
        assert remaining > 0.0

    def test_different_users_independent(self):
        """異なるユーザーはユーザー別クールダウンを共有しない。"""
        mgr = CooldownManager()
        mgr.record("!hello", "user_a")

        # user_b はユーザー別クールダウンに引っかからない（global_cd=0 にする）
        allowed, remaining = mgr.check("!hello", "user_b", global_cd=0.0, user_cd=10.0)
        assert allowed is True
        assert remaining == 0.0

    def test_allowed_after_cooldown_expires(self):
        """クールダウン時間が経過すれば再び許可される（time.monotonic をモック）。"""
        mgr = CooldownManager()

        # t=100.0 で記録
        with patch("src.commands.time.monotonic", return_value=100.0):
            mgr.record("!hello", "user_a")

        # t=106.0 — global_cd=5, user_cd=5 → 両方経過済み
        with patch("src.commands.time.monotonic", return_value=106.0):
            allowed, remaining = mgr.check(
                "!hello", "user_a", global_cd=5.0, user_cd=5.0
            )
            assert allowed is True
            assert remaining == 0.0

    def test_still_blocked_before_cooldown_expires(self):
        """クールダウン時間内はブロックされる（time.monotonic をモック）。"""
        mgr = CooldownManager()

        with patch("src.commands.time.monotonic", return_value=100.0):
            mgr.record("!hello", "user_a")

        # t=103.0 — global_cd=5 → まだ 2 秒残っている
        with patch("src.commands.time.monotonic", return_value=103.0):
            allowed, remaining = mgr.check(
                "!hello", "user_a", global_cd=5.0, user_cd=5.0
            )
            assert allowed is False
            assert remaining == pytest.approx(2.0, abs=0.1)


# ===========================================================================
# TestCheckPermission
# ===========================================================================


class TestCheckPermission:
    """check_permission の権限判定ロジックを検証する。"""

    def test_everyone_passes_everyone(self):
        """一般ユーザーは EVERYONE 要件を満たす。"""
        author = _make_author()
        assert check_permission(author, PermissionLevel.EVERYONE, "somechannel") is True

    def test_subscriber_passes_subscriber(self):
        """サブスクライバーは SUBSCRIBER 要件を満たす。"""
        author = _make_author(is_subscriber=True)
        assert check_permission(author, PermissionLevel.SUBSCRIBER, "somechannel") is True

    def test_subscriber_fails_moderator(self):
        """サブスクライバーは MODERATOR 要件を満たさない。"""
        author = _make_author(is_subscriber=True)
        assert check_permission(author, PermissionLevel.MODERATOR, "somechannel") is False

    def test_vip_passes_vip(self):
        """VIP は VIP 要件を満たす。"""
        author = _make_author(badges={"vip": "1"})
        assert check_permission(author, PermissionLevel.VIP, "somechannel") is True

    def test_vip_fails_moderator(self):
        """VIP は MODERATOR 要件を満たさない。"""
        author = _make_author(badges={"vip": "1"})
        assert check_permission(author, PermissionLevel.MODERATOR, "somechannel") is False

    def test_moderator_passes_moderator(self):
        """モデレーターは MODERATOR 要件を満たす。"""
        author = _make_author(is_mod=True)
        assert check_permission(author, PermissionLevel.MODERATOR, "somechannel") is True

    def test_broadcaster_passes_everything(self):
        """配信者はすべての権限要件を満たす。"""
        author = _make_author(name="mychannel")
        for level in PermissionLevel:
            assert check_permission(author, level, "mychannel") is True

    def test_regular_user_fails_subscriber(self):
        """一般ユーザー（非mod・非sub）は SUBSCRIBER 要件を満たさない。"""
        author = _make_author()
        assert check_permission(author, PermissionLevel.SUBSCRIBER, "somechannel") is False


# ===========================================================================
# TestSubstituteVariables
# ===========================================================================


class TestSubstituteVariables:
    """substitute_variables のプレースホルダー置換を検証する。"""

    def test_user_substitution(self):
        """{user} が display_name に置換される。"""
        author = _make_author(display_name="TestUser")
        result = substitute_variables("Hello, {user}!", author, "mychannel")
        assert result == "Hello, TestUser!"

    def test_channel_substitution(self):
        """{channel} がチャンネル名に置換される。"""
        author = _make_author()
        result = substitute_variables("Welcome to {channel}", author, "mychannel")
        assert result == "Welcome to mychannel"

    def test_time_and_date_substitution(self):
        """{time} と {date} が現在時刻・日付に置換される（datetime をフリーズ）。"""
        from datetime import datetime as real_datetime

        frozen = real_datetime(2026, 2, 18, 14, 30, 0)

        author = _make_author()
        with patch("src.commands.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.strftime = real_datetime.strftime
            result = substitute_variables(
                "Now: {time}, Date: {date}", author, "mychannel"
            )

        assert result == "Now: 14:30, Date: 2026/02/18"

    def test_no_placeholders(self):
        """プレースホルダーがないテンプレートはそのまま返る。"""
        author = _make_author()
        result = substitute_variables("No variables here", author, "mychannel")
        assert result == "No variables here"

    def test_multiple_placeholders(self):
        """複数のプレースホルダーが同時に置換される。"""
        from datetime import datetime as real_datetime

        frozen = real_datetime(2026, 1, 1, 0, 0, 0)

        author = _make_author(display_name="Alice")
        with patch("src.commands.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.strftime = real_datetime.strftime
            result = substitute_variables(
                "{user} joined {channel} at {time} on {date}",
                author,
                "streamchannel",
            )

        assert result == "Alice joined streamchannel at 00:00 on 2026/01/01"
