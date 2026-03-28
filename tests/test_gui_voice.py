"""音声翻訳表示ロジックのテスト"""

from src.voice_display import build_voice_translation_view


class TestVoiceTranslationView:
    def test_same_text_is_not_treated_as_distinct_translation(self):
        view = build_voice_translation_view("こんにちは", "こんにちは")

        assert view.has_distinct_translation is False
        assert view.log_message == "🎤 [Voice] こんにちは"
        assert view.overlay_text == "こんにちは"
        assert view.subtitle_translated == ""

    def test_different_text_keeps_translation_outputs(self):
        view = build_voice_translation_view("こんにちは", "hello")

        assert view.has_distinct_translation is True
        assert view.log_message == "🎤 [Voice] こんにちは\n    ➡ hello"
        assert view.overlay_text == "hello"
        assert view.subtitle_translated == "hello"
