"""
翻訳モジュール

複数の翻訳エンジン（DeepL, Google翻訳, LibreTranslate）をサポート。
後方互換性のため、旧APIも維持。
"""

import time
import asyncio
import threading
from collections import OrderedDict
from typing import Optional

from src.logger import logger
from src.translator.base import TranslatorInterface, TranslateMode, TranslateResult
from src.translator.deepl import DeepLTranslator
from src.translator.google import GoogleTranslator
from src.translator.libre import LibreTranslator
from src.translator.factory import (
    create_translator,
    get_engine_display_name,
    get_available_engines,
    AVAILABLE_ENGINES,
)

__all__ = [
    # 新API
    "TranslatorInterface",
    "TranslateMode",
    "TranslateResult",
    "DeepLTranslator",
    "GoogleTranslator",
    "LibreTranslator",
    "create_translator",
    "get_engine_display_name",
    "get_available_engines",
    "AVAILABLE_ENGINES",
    # 後方互換API
    "translate_text",
    "translate_text_sync",
    "get_deepl_usage",
    "set_translation_filters",
    "set_translation_dictionary",
    "should_filter",
    "apply_translation_dictionary",
    "get_stats",
    "set_current_engine",
    "get_current_engine",
]

# ========================================
# キャッシュ・レート制限・統計（共通）
# ========================================

CACHE_MAX_ENTRIES = 500
CACHE_TTL_SECONDS = 600
MIN_REQUEST_INTERVAL = 0.4
MAX_CONCURRENT_REQUESTS = 2


class _TranslationCache:
    """LRUキャッシュ（TTL付き）"""

    def __init__(self, max_entries=CACHE_MAX_ENTRIES, ttl=CACHE_TTL_SECONDS):
        self.max_entries = max_entries
        self.ttl = ttl
        self._store: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def _cleanup(self):
        now = time.time()
        keys_to_remove = [k for k, (ts, _) in list(self._store.items()) if now - ts > self.ttl]
        for k in keys_to_remove:
            self._store.pop(k, None)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def get(self, key):
        with self._lock:
            self._cleanup()
            if key not in self._store:
                return None
            ts, value = self._store.pop(key)
            self._store[key] = (ts, value)
            return value

    def set(self, key, value):
        with self._lock:
            self._cleanup()
            self._store[key] = (time.time(), value)
            self._store.move_to_end(key)


class _RateLimiter:
    """レートリミッター"""

    def __init__(self, min_interval=MIN_REQUEST_INTERVAL, max_concurrent=MAX_CONCURRENT_REQUESTS):
        self.min_interval = min_interval
        self._last_time = 0.0
        self._lock = threading.Lock()
        self._sem_async = asyncio.Semaphore(max_concurrent)

    def wait_sync(self):
        with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_time)
            if wait > 0:
                time.sleep(wait)
            self._last_time = time.monotonic()

    async def wait_async(self):
        async with self._sem_async:
            wait = 0.0
            with self._lock:
                now = time.monotonic()
                wait = self.min_interval - (now - self._last_time)
                self._last_time = time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)


# グローバル状態
_cache = _TranslationCache()
_rate_limiter = _RateLimiter()
_translation_filters: list[str] = []
_translation_dictionary: list[dict] = []
_stats = {
    "requests": 0,
    "cache_hits": 0,
    "filtered": 0,
    "errors": 0,
}

# 現在のエンジン設定
_current_engine: str = "deepl"
_engine_config: dict = {
    "deepl_api_key": "",
    "google_api_key": "",
    "libre_url": "https://libretranslate.com",
    "libre_api_key": "",
}


# ========================================
# エンジン管理
# ========================================

def set_current_engine(
    engine: str,
    deepl_api_key: str = "",
    google_api_key: str = "",
    libre_url: str = "",
    libre_api_key: str = "",
):
    """現在の翻訳エンジンを設定"""
    global _current_engine, _engine_config
    _current_engine = engine.lower().strip() if engine else "deepl"
    _engine_config = {
        "deepl_api_key": deepl_api_key,
        "google_api_key": google_api_key,
        "libre_url": libre_url or "https://libretranslate.com",
        "libre_api_key": libre_api_key,
    }
    logger.info(f"Translation engine set to: {_current_engine}")


def get_current_engine() -> str:
    """現在の翻訳エンジンを取得"""
    return _current_engine


def _get_translator() -> TranslatorInterface:
    """現在の設定に基づいてTranslatorを取得"""
    return create_translator(
        engine=_current_engine,
        **_engine_config
    )


# ========================================
# フィルタ・辞書
# ========================================

def set_translation_filters(filters):
    """翻訳フィルタを設定"""
    global _translation_filters
    _translation_filters = [f.strip().lower() for f in filters or [] if f]
    logger.info(f"Translation filters updated: {len(_translation_filters)} entries")


def set_translation_dictionary(entries):
    """翻訳前置換辞書を設定"""
    global _translation_dictionary
    normalized = []
    for e in entries or []:
        if isinstance(e, dict):
            src = str(e.get("source", ""))
            tgt = str(e.get("target", ""))
            if src:
                normalized.append({"source": src, "target": tgt})
    _translation_dictionary = normalized
    logger.info(f"Translation dictionary updated: {len(_translation_dictionary)} entries")


def should_filter(text: str) -> bool:
    """フィルタに合致する場合True"""
    if not text:
        return False
    lowered = text.lower()
    return any(f in lowered for f in _translation_filters)


def apply_translation_dictionary(text: str) -> str:
    """翻訳前に辞書置換を適用"""
    if not text:
        return text
    result = text
    for entry in _translation_dictionary:
        src = entry.get("source", "")
        tgt = entry.get("target", "")
        if src:
            result = result.replace(src, tgt)
    return result


def get_stats():
    """統計情報を取得"""
    return _stats.copy()


# ========================================
# 後方互換API
# ========================================

def _normalize_text(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text


def _make_cache_key(text: str, mode: str, engine: str) -> tuple:
    return (text, mode, engine)


async def translate_text(text, mode, api_key=None):
    """
    非同期翻訳（後方互換API）

    Args:
        text: 翻訳するテキスト
        mode: 翻訳モード ("自動", "英→日", "日→英")
        api_key: DeepL APIキー（後方互換用、set_current_engineで設定した方が優先）
    """
    text = _normalize_text(text)
    if not text.strip():
        return text

    # フィルタチェック
    if should_filter(text):
        _stats["filtered"] += 1
        logger.info("Translation skipped by filter")
        return ""

    # 辞書置換
    text = apply_translation_dictionary(text)

    # キャッシュチェック
    cache_key = _make_cache_key(text, mode, _current_engine)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text cache hit")
        return cached

    # api_keyが渡された場合は一時的にDeepL設定を更新
    if api_key and _current_engine == "deepl":
        _engine_config["deepl_api_key"] = api_key

    translator = _get_translator()
    translate_mode = TranslateMode.from_string(mode)

    await _rate_limiter.wait_async()
    _stats["requests"] += 1

    result = await translator.translate(text, translate_mode)

    if result.success:
        _cache.set(cache_key, result.translated_text)
        return result.translated_text
    else:
        _stats["errors"] += 1
        logger.error(f"Translation error: {result.error}")
        return text


def translate_text_sync(text, mode, api_key=None):
    """
    同期翻訳（後方互換API）

    Args:
        text: 翻訳するテキスト
        mode: 翻訳モード ("自動", "英→日", "日→英")
        api_key: DeepL APIキー（後方互換用）
    """
    text = _normalize_text(text)
    if not text.strip():
        return text

    # フィルタチェック
    if should_filter(text):
        _stats["filtered"] += 1
        logger.info("Translation skipped by filter")
        return ""

    # 辞書置換
    text = apply_translation_dictionary(text)

    # キャッシュチェック
    cache_key = _make_cache_key(text, mode, _current_engine)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text_sync cache hit")
        return cached

    # api_keyが渡された場合は一時的にDeepL設定を更新
    if api_key and _current_engine == "deepl":
        _engine_config["deepl_api_key"] = api_key

    translator = _get_translator()
    translate_mode = TranslateMode.from_string(mode)

    _rate_limiter.wait_sync()
    _stats["requests"] += 1

    result = translator.translate_sync(text, translate_mode)

    if result.success:
        _cache.set(cache_key, result.translated_text)
        return result.translated_text
    else:
        _stats["errors"] += 1
        logger.error(f"Translation error: {result.error}")
        return text


def get_deepl_usage(api_key: str) -> dict:
    """DeepL API使用状況を取得（後方互換API）"""
    translator = DeepLTranslator(api_key=api_key)
    return translator.get_usage() or {'character_count': 0, 'character_limit': 0, 'error': 'Unknown'}
