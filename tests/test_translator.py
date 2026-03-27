import asyncio
from src import translator


def test_translate_text_uses_cache(monkeypatch):
    """translate_text の非同期キャッシュテスト（同期ラッパー）"""
    translator._cache = translator._TranslationCache(max_entries=10, ttl=60)
    translator.set_translation_filters([])
    translator.set_translation_dictionary([])

    calls = {"count": 0}

    def fake_local(text, mode):
        calls["count"] += 1
        return "OUT"

    monkeypatch.setattr(translator, "_translate_local", fake_local)

    loop = asyncio.new_event_loop()
    try:
        res1 = loop.run_until_complete(translator.translate_text("hello", "英→日", "KEY"))
        res2 = loop.run_until_complete(translator.translate_text("hello", "英→日", "KEY"))
    finally:
        loop.close()

    assert res1 == "OUT"
    assert res2 == "OUT"
    assert calls["count"] == 1  # キャッシュにより1回のみ


def test_translate_text_sync_uses_cache(monkeypatch):
    translator._cache = translator._TranslationCache(max_entries=10, ttl=60)
    translator.set_translation_filters([])
    translator.set_translation_dictionary([])

    calls = {"count": 0}

    def fake_local(text, mode):
        calls["count"] += 1
        return "SYNC"

    monkeypatch.setattr(translator, "_translate_local", fake_local)

    res1 = translator.translate_text_sync("world", "日→英", "KEY")
    res2 = translator.translate_text_sync("world", "日→英", "KEY")

    assert res1 == "SYNC"
    assert res2 == "SYNC"
    assert calls["count"] == 1
