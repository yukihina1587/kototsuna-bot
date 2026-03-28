from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceTranslationView:
    has_distinct_translation: bool
    log_message: str
    overlay_text: str
    subtitle_translated: str


def build_voice_translation_view(original: str, translated: str) -> VoiceTranslationView:
    """音声認識結果と翻訳結果から、UI表示用の値を組み立てる。"""
    original_text = original or ""
    translated_text = translated or ""
    distinct = bool(
        translated_text.strip()
        and translated_text.strip() != "(No API Key)"
        and translated_text.strip() != original_text.strip()
    )

    log_message = f"🎤 [Voice] {original_text}"
    if distinct:
        log_message += f"\n    ➡ {translated_text}"

    return VoiceTranslationView(
        has_distinct_translation=distinct,
        log_message=log_message,
        overlay_text=translated_text if distinct else original_text,
        subtitle_translated=translated_text if distinct else "",
    )
