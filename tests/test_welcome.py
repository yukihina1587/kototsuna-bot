"""初見視聴者ウェルカム機能のテスト（Issue #140）。"""

from __future__ import annotations

import pytest

from src.welcome import (
    DEFAULT_WELCOME_MESSAGE,
    VALID_WELCOME_TARGETS,
    WelcomeDispatcher,
    build_welcome_payload,
    format_welcome_message,
    is_first_message,
    normalize_targets,
)


class TestFormatWelcomeMessage:
    def test_substitutes_user_and_channel(self) -> None:
        text = format_welcome_message(
            "@{user} さん、ようこそ {channel} へ", user="alice", channel="bob"
        )
        assert text == "@alice さん、ようこそ bob へ"

    def test_unknown_placeholder_is_kept_literally(self) -> None:
        text = format_welcome_message(
            "{user} {unknown_key}", user="alice", channel="bob"
        )
        assert text == "alice {unknown_key}"

    def test_empty_template_falls_back_to_default(self) -> None:
        text = format_welcome_message("", user="alice", channel="bob")
        assert "alice" in text
        assert "bob" in text

    def test_invalid_format_returns_template(self) -> None:
        text = format_welcome_message("{0}", user="alice", channel="bob")
        assert text == "{0}"


class TestIsFirstMessage:
    def test_returns_true_when_tag_is_one(self) -> None:
        assert is_first_message({"first-msg": "1"}) is True

    def test_returns_false_when_tag_is_zero(self) -> None:
        assert is_first_message({"first-msg": "0"}) is False

    def test_returns_false_when_tag_missing(self) -> None:
        assert is_first_message({}) is False

    def test_returns_false_when_tags_none(self) -> None:
        assert is_first_message(None) is False


class TestNormalizeTargets:
    def test_keeps_only_known_targets(self) -> None:
        assert normalize_targets(["chat", "tts", "junk"]) == ["chat", "tts"]

    def test_dedupes_targets(self) -> None:
        assert normalize_targets(["chat", "chat", "tts"]) == ["chat", "tts"]

    def test_returns_default_for_non_list(self) -> None:
        assert normalize_targets("chat") == ["chat"]

    def test_handles_case_insensitively(self) -> None:
        assert normalize_targets(["CHAT", "TTS"]) == ["chat", "tts"]


class TestWelcomeDispatcher:
    def test_does_not_fire_when_disabled(self) -> None:
        d = WelcomeDispatcher(enabled=False, cooldown_sec=0)
        assert (
            d.should_fire(username="alice", is_first=True, now=0.0) is False
        )

    def test_does_not_fire_when_not_first(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        assert (
            d.should_fire(username="alice", is_first=False, now=0.0) is False
        )

    def test_fires_on_first_message(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        assert d.should_fire(username="alice", is_first=True, now=1.0) is True

    def test_dedupes_same_user(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        assert d.should_fire(username="alice", is_first=True, now=1.0) is True
        d.mark_fired("alice", now=1.0)
        # 同じユーザーが再度 first-msg を送ってきても発火しない
        assert d.should_fire(username="alice", is_first=True, now=2.0) is False

    def test_dedupe_is_case_insensitive(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        d.mark_fired("Alice", now=1.0)
        assert (
            d.should_fire(username="ALICE", is_first=True, now=2.0) is False
        )

    def test_cooldown_blocks_second_user(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=10)
        assert d.should_fire(username="alice", is_first=True, now=0.0) is True
        d.mark_fired("alice", now=0.0)
        # 別ユーザーでもクールダウン中は発火しない
        assert d.should_fire(username="bob", is_first=True, now=5.0) is False

    def test_cooldown_releases_after_window(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=10)
        d.mark_fired("alice", now=0.0)
        assert (
            d.should_fire(username="bob", is_first=True, now=15.0) is True
        )

    def test_zero_cooldown_allows_back_to_back_users(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        d.mark_fired("alice", now=0.0)
        assert (
            d.should_fire(username="bob", is_first=True, now=0.0) is True
        )

    def test_empty_username_does_not_fire(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        assert d.should_fire(username="", is_first=True, now=0.0) is False

    def test_reset_dedup_allows_re_firing(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        d.mark_fired("alice", now=0.0)
        d.reset_dedup()
        assert d.should_fire(username="alice", is_first=True, now=1.0) is True

    def test_update_config_disables_in_flight(self) -> None:
        d = WelcomeDispatcher(enabled=True, cooldown_sec=0)
        d.update_config(enabled=False, cooldown_sec=0)
        assert (
            d.should_fire(username="alice", is_first=True, now=0.0) is False
        )


class TestBuildWelcomePayload:
    def test_returns_normalized_targets(self) -> None:
        payload = build_welcome_payload(
            template="@{user} ようこそ",
            user="alice",
            channel="bob",
            targets=["chat", "junk", "tts"],
        )
        assert payload["text"] == "@alice ようこそ"
        assert payload["targets"] == ["chat", "tts"]
        assert payload["user"] == "alice"
        assert payload["channel"] == "bob"

    def test_default_template_when_falsy(self) -> None:
        payload = build_welcome_payload(
            template="",
            user="alice",
            channel="bob",
            targets=["chat"],
        )
        assert "alice" in payload["text"]


class TestConfigValidation:
    def test_default_welcome_keys_present(self) -> None:
        from src.config import DEFAULT_CONFIG, validate_config

        validated, _ = validate_config({})
        assert validated["welcome_enabled"] is False
        assert validated["welcome_message"] == DEFAULT_CONFIG["welcome_message"]
        assert validated["welcome_targets"] == ["chat"]
        assert validated["welcome_cooldown_sec"] == 5
        assert validated["welcome_tts_voice_id"] is None

    def test_invalid_targets_are_filtered(self) -> None:
        from src.config import validate_config

        validated, changed = validate_config(
            {"welcome_targets": ["chat", "junk", "TTS", 1]}
        )
        assert validated["welcome_targets"] == ["chat", "tts"]
        assert changed is True

    def test_cooldown_clamped(self) -> None:
        from src.config import validate_config

        validated, _ = validate_config({"welcome_cooldown_sec": 999999})
        assert validated["welcome_cooldown_sec"] == 3600

    def test_negative_cooldown_clamped_to_zero(self) -> None:
        from src.config import validate_config

        validated, _ = validate_config({"welcome_cooldown_sec": -10})
        assert validated["welcome_cooldown_sec"] == 0

    def test_empty_message_falls_back_to_default(self) -> None:
        from src.config import DEFAULT_CONFIG, validate_config

        validated, changed = validate_config({"welcome_message": "  "})
        assert validated["welcome_message"] == DEFAULT_CONFIG["welcome_message"]
        assert changed is True

    def test_invalid_voice_id_falls_back_to_none(self) -> None:
        from src.config import validate_config

        validated, _ = validate_config({"welcome_tts_voice_id": "abc"})
        assert validated["welcome_tts_voice_id"] is None


class TestModuleConstants:
    def test_valid_targets_set(self) -> None:
        assert VALID_WELCOME_TARGETS == {"chat", "tts", "overlay"}

    def test_default_message_has_placeholders(self) -> None:
        assert "{user}" in DEFAULT_WELCOME_MESSAGE
        assert "{channel}" in DEFAULT_WELCOME_MESSAGE


@pytest.mark.skip(reason="GUI 統合は手動検証で確認")
def test_gui_panel_placeholder() -> None:  # pragma: no cover
    pass
