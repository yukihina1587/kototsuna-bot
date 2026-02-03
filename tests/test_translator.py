import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src import translator
from src.translator.base import TranslateResult, TranslateMode


@pytest.mark.asyncio
async def test_translate_text_uses_cache(monkeypatch):
    """キャッシュが正しく機能することを確認"""
    # 新しいキャッシュとレートリミッタをセット
    translator._cache = translator._TranslationCache(max_entries=10, ttl=60)
    translator._rate_limiter = translator._RateLimiter(min_interval=0, max_concurrent=5)
    translator.set_translation_filters([])
    translator.set_translation_dictionary([])

    calls = {"count": 0}

    # モックトランスレーターを作成
    mock_translator = MagicMock()
    async def fake_translate(text, mode):
        calls["count"] += 1
        return TranslateResult(success=True, translated_text="OUT")

    mock_translator.translate = fake_translate

    # _get_translator をモック
    monkeypatch.setattr(translator, "_get_translator", lambda: mock_translator)

    res1 = await translator.translate_text("hello", "英→日", "KEY")
    res2 = await translator.translate_text("hello", "英→日", "KEY")

    assert res1 == "OUT"
    assert res2 == "OUT"
    assert calls["count"] == 1  # キャッシュにより1回のみ


def test_translate_text_sync_uses_cache(monkeypatch):
    """同期版でもキャッシュが正しく機能することを確認"""
    translator._cache = translator._TranslationCache(max_entries=10, ttl=60)
    translator._rate_limiter = translator._RateLimiter(min_interval=0, max_concurrent=5)
    translator.set_translation_filters([])
    translator.set_translation_dictionary([])

    calls = {"count": 0}

    # モックトランスレーターを作成
    mock_translator = MagicMock()
    def fake_translate_sync(text, mode):
        calls["count"] += 1
        return TranslateResult(success=True, translated_text="SYNC")

    mock_translator.translate_sync = fake_translate_sync

    # _get_translator をモック
    monkeypatch.setattr(translator, "_get_translator", lambda: mock_translator)

    res1 = translator.translate_text_sync("world", "日→英", "KEY")
    res2 = translator.translate_text_sync("world", "日→英", "KEY")

    assert res1 == "SYNC"
    assert res2 == "SYNC"
    assert calls["count"] == 1


def test_rate_limiter_sync_spacing():
    """レートリミッターが正しく間隔を空けることを確認"""
    limiter = translator._RateLimiter(min_interval=0.05, max_concurrent=2)
    start = time.monotonic()
    limiter.wait_sync()
    limiter.wait_sync()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05
