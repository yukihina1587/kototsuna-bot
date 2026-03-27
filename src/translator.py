import os
import time
import threading
import re
from collections import OrderedDict
from src.logger import logger
from src.translation_dictionary import TranslationDictionary

# キャッシュ設定
CACHE_MAX_ENTRIES = 500
CACHE_TTL_SECONDS = 600  # 10分

def _is_japanese(text):
    """
    テキストに日本語が含まれているか判定する簡易ロジック
    ひらがな([3040-309F]) または カタカナ([30A0-30FF]) が含まれていれば日本語とみなす
    """
    if not text:
        return False
    # ひらがな・カタカナの範囲
    jp_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
    return bool(jp_pattern.search(text))


class _TranslationCache:
    """単純なLRUキャッシュ（TTL付き）"""

    def __init__(self, max_entries=CACHE_MAX_ENTRIES, ttl=CACHE_TTL_SECONDS):
        self.max_entries = max_entries
        self.ttl = ttl
        self._store = OrderedDict()
        self._lock = threading.Lock()

    def _cleanup(self):
        now = time.time()
        keys_to_remove = []
        for k, (ts, _) in list(self._store.items()):
            if now - ts > self.ttl:
                keys_to_remove.append(k)
        for k in keys_to_remove:
            self._store.pop(k, None)

        # サイズ超過分を削除
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def get(self, key):
        with self._lock:
            self._cleanup()
            if key not in self._store:
                return None
            ts, value = self._store.pop(key)
            # 再挿入で新しい順に
            self._store[key] = (ts, value)
            return value

    def set(self, key, value):
        with self._lock:
            self._cleanup()
            self._store[key] = (time.time(), value)
            # 最新を末尾に
            self._store.move_to_end(key)
            self._cleanup()


_cache = _TranslationCache()
_translation_filters = []
_dict_instance: TranslationDictionary | None = None
_stats = {
    "cache_hits": 0,
    "filtered": 0,
    "local_requests": 0,
    "local_errors": 0,
}


def _normalize_text(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text


def _make_cache_key(text, mode):
    return (text, mode)


def _translate_local(text: str, mode: str) -> str | None:
    """ローカル翻訳を試みる。成功時は翻訳結果、失敗時はNone。"""
    try:
        from src.local_translator import get_local_translator
    except ImportError:
        return None

    translator = get_local_translator()
    if translator is None:
        logger.warning("Local translator unavailable (models missing or dependencies not installed)")
        return None

    if mode == "英→日":
        direction = "en-ja"
    elif mode == "日→英":
        direction = "ja-en"
    elif mode == "自動":
        direction = "ja-en" if _is_japanese(text) else "en-ja"
    else:
        direction = "en-ja"

    _stats["local_requests"] += 1
    logger.debug(f"Local translate: text='{text[:50]}' direction={direction}")
    result = translator.translate(text, direction)
    logger.debug(f"Local translate result: '{result[:100]}'")
    if result == text:
        logger.warning(f"Local translation returned same text (direction={direction})")
        _stats["local_errors"] += 1
        return None
    return result


def set_translation_filters(filters):
    """翻訳フィルタの設定（部分一致で判定、lower比較）"""
    global _translation_filters
    _translation_filters = [f.strip().lower() for f in filters or [] if f]
    logger.info(f"Translation filters updated: {len(_translation_filters)} entries")


def set_translation_dictionary(entries: list[dict]) -> None:
    """後方互換用。config.jsonの辞書をインスタンスにセット（マイグレーション）。"""
    global _dict_instance
    if _dict_instance is None:
        return
    if entries:
        count = _dict_instance.migrate_from_config(entries)
        if count:
            logger.info(f"Migrated {count} entries from config to translation_dict.json")


def init_translation_dictionary() -> TranslationDictionary:
    """起動時に辞書インスタンスを初期化して返す。"""
    global _dict_instance
    _dict_instance = TranslationDictionary()
    return _dict_instance


def get_translation_dictionary() -> TranslationDictionary | None:
    """辞書インスタンスを返す。"""
    return _dict_instance


def should_filter(text: str) -> bool:
    """フィルタに合致する場合 True"""
    if not text:
        return False
    lowered = text.lower()
    return any(f in lowered for f in _translation_filters)


def apply_translation_dictionary(text: str) -> str:
    """翻訳前に辞書置換を適用する。"""
    if not text or _dict_instance is None:
        return text
    return _dict_instance.apply(text)


def get_stats():
    return _stats.copy()


async def translate_text(text, mode, api_key=""):
    text = _normalize_text(text)
    if not text.strip():
        return text

    # フィルタチェック
    if should_filter(text):
        _stats["filtered"] += 1
        logger.debug("Translation skipped by filter")
        return ""

    # 辞書置換
    text = apply_translation_dictionary(text)

    cache_key = _make_cache_key(text, mode)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text cache hit")
        return cached

    result = _translate_local(text, mode)
    if result is not None:
        _cache.set(cache_key, result)
        return result
    logger.warning("Local translation failed, returning original text")
    return text


def translate_text_sync(text, mode, api_key=""):
    text = _normalize_text(text)
    if not text.strip():
        return text

    if should_filter(text):
        _stats["filtered"] += 1
        logger.debug("Translation skipped by filter")
        return ""

    text = apply_translation_dictionary(text)

    cache_key = _make_cache_key(text, mode)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text_sync cache hit")
        return cached

    result = _translate_local(text, mode)
    if result is not None:
        _cache.set(cache_key, result)
        return result
    logger.warning("Local translation failed, returning original text")
    return text


async def translate_text_batched(text: str, mode: str, api_key: str = "") -> str:
    """バッチ処理対応の翻訳関数。キャッシュ済みは即返却、未キャッシュはバッチ対象。"""
    text = _normalize_text(text)
    if not text.strip():
        return text

    if should_filter(text):
        _stats["filtered"] += 1
        return ""

    text = apply_translation_dictionary(text)

    # キャッシュ済みは即返却
    cache_key = _make_cache_key(text, mode)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        return cached

    result = _translate_local(text, mode)
    if result is not None:
        _cache.set(cache_key, result)
        return result

    logger.warning("Local translation failed during batched translate, returning original text")
    return text


async def cleanup():
    """互換用のクリーンアップフック。ローカル翻訳のみでは特別な解放は不要。"""
    return None
