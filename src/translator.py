import aiohttp
import os
import requests
import time
import asyncio
import threading
import re
from collections import OrderedDict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.logger import logger
from src.performance_logger import get_perf


class DeepLRetryableError(Exception):
    """DeepL APIのリトライ可能なエラー（429, 503など）"""
    pass

DEEPL_FREE_ENDPOINT = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO_ENDPOINT = "https://api.deepl.com/v2/translate"
DEEPL_FREE_USAGE_ENDPOINT = "https://api-free.deepl.com/v2/usage"
DEEPL_PRO_USAGE_ENDPOINT = "https://api.deepl.com/v2/usage"

# キャッシュ設定
CACHE_MAX_ENTRIES = 500
CACHE_TTL_SECONDS = 600  # 10分

# レート制限設定（簡易的にリクエスト間隔と同時実行数を制御）
MIN_REQUEST_INTERVAL = 0.4  # 約2.5req/sec
MAX_CONCURRENT_REQUESTS = 2
RETRY_BACKOFF = [0.5, 1.0, 2.0]  # 429等のときの再試行待機


def get_deepl_endpoint(api_key):
    """APIキーに基づいて適切なエンドポイントを返す"""
    if api_key and api_key.strip().endswith(":fx"):
        return DEEPL_FREE_ENDPOINT
    return DEEPL_PRO_ENDPOINT


def get_deepl_usage_endpoint(api_key):
    """APIキーに基づいて適切な使用量エンドポイントを返す"""
    if api_key and api_key.strip().endswith(":fx"):
        return DEEPL_FREE_USAGE_ENDPOINT
    return DEEPL_PRO_USAGE_ENDPOINT


def get_deepl_usage(api_key: str) -> dict:
    """
    DeepL APIの使用状況を取得する

    Returns:
        dict: {
            'character_count': int,  # 使用文字数
            'character_limit': int,  # 上限文字数
            'error': str or None     # エラーメッセージ（あれば）
        }
    """
    if not api_key or not api_key.strip():
        return {'character_count': 0, 'character_limit': 0, 'error': 'APIキー未設定'}

    endpoint = get_deepl_usage_endpoint(api_key)
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'character_count': data.get('character_count', 0),
                'character_limit': data.get('character_limit', 0),
                'error': None
            }
        elif response.status_code == 403:
            return {'character_count': 0, 'character_limit': 0, 'error': 'APIキーが無効'}
        else:
            return {'character_count': 0, 'character_limit': 0, 'error': f'API Error: {response.status_code}'}
    except requests.exceptions.Timeout:
        return {'character_count': 0, 'character_limit': 0, 'error': 'タイムアウト'}
    except Exception as e:
        logger.error(f"DeepL usage API error: {e}")
        return {'character_count': 0, 'character_limit': 0, 'error': str(e)}


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


class _RateLimiter:
    """簡易レートリミッター（最小間隔 & 同時実行数）"""

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
            # 同じロックを利用してインターバルを共有
            with self._lock:
                now = time.monotonic()
                wait = self.min_interval - (now - self._last_time)
                self._last_time = time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)


class _SessionManager:
    """aiohttp.ClientSessionを再利用するためのマネージャー"""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30)
                )
        return self._session

    async def close(self):
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None


class _TranslationBatcher:
    """翻訳リクエストをバッチ化して効率的にAPI呼び出しを行う"""

    def __init__(self, batch_size: int = 5, wait_ms: int = 100):
        self.batch_size = batch_size
        self.wait_ms = wait_ms
        self._pending: list[tuple[str, str, str, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

    async def submit(self, text: str, mode: str, api_key: str) -> str:
        """翻訳リクエストを送信。バッチ処理で効率化される。"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async with self._lock:
            self._pending.append((text, mode, api_key, future))

            if len(self._pending) >= self.batch_size:
                # バッチサイズに達したら即座にフラッシュ
                batch = self._pending[:]
                self._pending.clear()
                if self._flush_task and not self._flush_task.done():
                    self._flush_task.cancel()
                asyncio.create_task(self._process_batch(batch))
            elif self._flush_task is None or self._flush_task.done():
                # 待機タイマーを開始
                self._flush_task = asyncio.create_task(self._delayed_flush())

        return await future

    async def _delayed_flush(self):
        """待機時間後にバッチをフラッシュ"""
        await asyncio.sleep(self.wait_ms / 1000.0)
        async with self._lock:
            if self._pending:
                batch = self._pending[:]
                self._pending.clear()
                asyncio.create_task(self._process_batch(batch))

    async def _process_batch(self, batch: list):
        """バッチ内のリクエストを処理"""
        for text, mode, api_key, future in batch:
            if future.done():
                continue
            try:
                result = await translate_text(text, mode, api_key)
                if not future.done():
                    future.set_result(result)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)


_cache = _TranslationCache()
_rate_limiter = _RateLimiter()
_session_manager = _SessionManager()
_batcher = _TranslationBatcher()
_translation_filters = []
_translation_dictionary = []
_translation_engine = "deepl"  # deepl / local / hybrid
_stats = {
    "requests": 0,
    "cache_hits": 0,
    "filtered": 0,
    "errors": 0,
    "batched": 0,
    "local_requests": 0,
    "local_errors": 0,
}


def _normalize_text(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text


def _make_cache_key(text, mode, api_key):
    safe_key = api_key or ""
    return (text, mode, safe_key)


def set_translation_engine(engine: str) -> None:
    """翻訳エンジンを設定する。"""
    global _translation_engine
    if engine in ("deepl", "local", "hybrid"):
        _translation_engine = engine
        logger.info(f"Translation engine set to: {engine}")


def get_translation_engine() -> str:
    """現在の翻訳エンジンを返す。"""
    return _translation_engine


def _translate_local(text: str, mode: str) -> str | None:
    """ローカル翻訳を試みる。成功時は翻訳結果、失敗時はNone。"""
    try:
        from src.local_translator import get_local_translator
    except ImportError:
        return None

    translator = get_local_translator()
    if translator is None:
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
    result = translator.translate(text, direction)
    if result == text:
        # translate() returns original text on error
        _stats["local_errors"] += 1
        return None
    return result


def set_translation_filters(filters):
    """翻訳フィルタの設定（部分一致で判定、lower比較）"""
    global _translation_filters
    _translation_filters = [f.strip().lower() for f in filters or [] if f]
    logger.info(f"Translation filters updated: {len(_translation_filters)} entries")


def set_translation_dictionary(entries):
    """翻訳前置換の辞書を設定"""
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
    """フィルタに合致する場合 True"""
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
    stats = _stats.copy()
    _perf = get_perf()
    api_stats = _perf.get_stats("deepl_api")
    if api_stats:
        stats["avg_api_ms"] = api_stats["avg"]
        stats["p95_api_ms"] = api_stats.get("p95")
    return stats


def _build_payload(text, mode):
    if mode == '英→日':
        source_lang = 'EN'
        target_lang = 'JA'
    elif mode == '日→英':
        source_lang = 'JA'
        target_lang = 'EN'
    elif mode == '自動':
        # 自動モード: 日本語が含まれていれば英語に、それ以外は日本語に翻訳
        if _is_japanese(text):
            source_lang = 'JA'
            target_lang = 'EN'
        else:
            # ソース言語はDeepLに任せる（英語以外も日本語にしたいのでsource指定なし）
            source_lang = None
            target_lang = 'JA'
    else:
        source_lang = None
        target_lang = 'JA'

    data = {
        "text": text,
        "target_lang": target_lang,
        "tag_handling": "xml",
        "ignore_tags": "k",
    }
    if source_lang:
        data["source_lang"] = source_lang
    return data


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, DeepLRetryableError)),
    reraise=True
)
async def _translate_http_async(payload, endpoint, api_key):
    """DeepL API呼び出し（指数バックオフリトライ付き、セッション再利用）"""
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    session = await _session_manager.get_session()
    async with session.post(endpoint, data=payload, headers=headers) as resp:
        if resp.status in (429, 503):
            logger.warning(f"DeepL rate limited ({resp.status}). Will retry with exponential backoff...")
            raise DeepLRetryableError(f"Rate limited: {resp.status}")
        body = await resp.text()
        return resp.status, body, await resp.json() if resp.status == 200 else None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, DeepLRetryableError)),
    reraise=True
)
def _translate_http_sync(payload, endpoint, api_key):
    """DeepL API呼び出し（指数バックオフリトライ付き）"""
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    resp = requests.post(endpoint, data=payload, headers=headers, timeout=30)
    if resp.status_code in (429, 503):
        logger.warning(f"DeepL rate limited ({resp.status_code}). Will retry with exponential backoff...")
        raise DeepLRetryableError(f"Rate limited: {resp.status_code}")
    return resp.status_code, resp.text, resp.json() if resp.status_code == 200 else None


async def translate_text(text, mode, api_key):
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

    cache_key = _make_cache_key(text, mode, api_key)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text cache hit")
        return cached

    # ローカル翻訳エンジン
    if _translation_engine == "local":
        result = _translate_local(text, mode)
        if result is not None:
            _cache.set(cache_key, result)
            return result
        return text

    # DeepL API（deepl or hybrid）
    if not api_key:
        # hybrid: DeepL APIキーなしでもローカルにフォールバック
        if _translation_engine == "hybrid":
            result = _translate_local(text, mode)
            if result is not None:
                _cache.set(cache_key, result)
                return result
        logger.error("DeepL API Key is missing.")
        return text

    payload = _build_payload(text, mode)
    endpoint = get_deepl_endpoint(api_key)
    await _rate_limiter.wait_async()
    _stats["requests"] += 1

    _perf = get_perf()
    try:
        with _perf.measure("deepl_api"):
            status, body, result = await _translate_http_async(payload, endpoint, api_key)
        if status == 200:
            translated = result["translations"][0]["text"]
            _cache.set(cache_key, translated)
            return translated
        else:
            logger.error(f"DeepL API Error: {status} {body}")
    except DeepLRetryableError:
        logger.error("DeepL API retry exhausted")
        _stats["errors"] += 1
    except Exception as e:
        logger.error(f"Exception during DeepL request: {e}", exc_info=True)
        _stats["errors"] += 1

    # hybrid: DeepL失敗時にローカルフォールバック
    if _translation_engine == "hybrid":
        result = _translate_local(text, mode)
        if result is not None:
            _cache.set(cache_key, result)
            return result

    return text


def translate_text_sync(text, mode, api_key):
    text = _normalize_text(text)
    if not text.strip():
        return text

    if should_filter(text):
        _stats["filtered"] += 1
        logger.info("Translation skipped by filter")
        return ""

    text = apply_translation_dictionary(text)

    cache_key = _make_cache_key(text, mode, api_key)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        logger.debug("translate_text_sync cache hit")
        return cached

    # ローカル翻訳エンジン
    if _translation_engine == "local":
        result = _translate_local(text, mode)
        if result is not None:
            _cache.set(cache_key, result)
            return result
        return text

    # DeepL API（deepl or hybrid）
    if not api_key:
        if _translation_engine == "hybrid":
            result = _translate_local(text, mode)
            if result is not None:
                _cache.set(cache_key, result)
                return result
        logger.error("DeepL API Key is missing.")
        return text

    payload = _build_payload(text, mode)
    endpoint = get_deepl_endpoint(api_key)
    _rate_limiter.wait_sync()
    _stats["requests"] += 1

    try:
        status, body, result = _translate_http_sync(payload, endpoint, api_key)
        if status == 200:
            translated = result["translations"][0]["text"]
            _cache.set(cache_key, translated)
            return translated
        else:
            logger.error(f"DeepL API Error: {status} {body}")
    except DeepLRetryableError:
        logger.error("DeepL API retry exhausted")
        _stats["errors"] += 1
    except Exception as e:
        logger.error(f"Exception during DeepL request: {e}", exc_info=True)
        _stats["errors"] += 1

    # hybrid: DeepL失敗時にローカルフォールバック
    if _translation_engine == "hybrid":
        result = _translate_local(text, mode)
        if result is not None:
            _cache.set(cache_key, result)
            return result

    return text


async def translate_text_batched(text: str, mode: str, api_key: str) -> str:
    """バッチ処理対応の翻訳関数。キャッシュ済みは即返却、未キャッシュはバッチ対象。"""
    if not api_key:
        logger.error("DeepL API Key is missing.")
        return _normalize_text(text)

    text = _normalize_text(text)
    if not text.strip():
        return text

    if should_filter(text):
        _stats["filtered"] += 1
        return ""

    text = apply_translation_dictionary(text)

    # キャッシュ済みは即返却
    cache_key = _make_cache_key(text, mode, api_key)
    cached = _cache.get(cache_key)
    if cached is not None:
        _stats["cache_hits"] += 1
        return cached

    _stats["batched"] += 1
    return await _batcher.submit(text, mode, api_key)


def configure_batcher(batch_size: int = 5, wait_ms: int = 100):
    """バッチ処理の設定を変更（ペンディング中のリクエストはキャンセルされる）"""
    global _batcher
    old_batcher = _batcher
    _batcher = _TranslationBatcher(batch_size=batch_size, wait_ms=wait_ms)
    # 旧バッチャーのペンディングリクエストをキャンセル
    for _, _, _, future in old_batcher._pending:
        if not future.done():
            future.cancel()
    old_batcher._pending.clear()


async def cleanup():
    """モジュールクリーンアップ（セッション解放）"""
    await _session_manager.close()
