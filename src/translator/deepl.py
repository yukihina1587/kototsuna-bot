"""
DeepL翻訳エンジン

DeepL API (Free/Pro) を使用した翻訳。
"""

import re
import aiohttp
import asyncio
import requests
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.logger import logger
from src.translator.base import TranslatorInterface, TranslateMode, TranslateResult


class DeepLRetryableError(Exception):
    """DeepL APIのリトライ可能なエラー（429, 503など）"""
    pass


# エンドポイント
DEEPL_FREE_ENDPOINT = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO_ENDPOINT = "https://api.deepl.com/v2/translate"
DEEPL_FREE_USAGE_ENDPOINT = "https://api-free.deepl.com/v2/usage"
DEEPL_PRO_USAGE_ENDPOINT = "https://api.deepl.com/v2/usage"


def _is_japanese(text: str) -> bool:
    """テキストに日本語が含まれているか判定"""
    if not text:
        return False
    jp_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
    return bool(jp_pattern.search(text))


class DeepLTranslator(TranslatorInterface):
    """DeepL翻訳エンジン"""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: DeepL APIキー（Free版は:fxで終わる）
        """
        self.api_key = api_key

    def get_name(self) -> str:
        return "DeepL"

    def _is_free_api(self) -> bool:
        """Free APIかどうか"""
        return self.api_key and self.api_key.strip().endswith(":fx")

    def _get_endpoint(self) -> str:
        """翻訳エンドポイント取得"""
        if self._is_free_api():
            return DEEPL_FREE_ENDPOINT
        return DEEPL_PRO_ENDPOINT

    def _get_usage_endpoint(self) -> str:
        """使用量エンドポイント取得"""
        if self._is_free_api():
            return DEEPL_FREE_USAGE_ENDPOINT
        return DEEPL_PRO_USAGE_ENDPOINT

    def validate_config(self) -> tuple[bool, str]:
        """APIキーの検証"""
        if not self.api_key or not self.api_key.strip():
            return False, "DeepL APIキーが設定されていません"

        # 基本的なフォーマットチェック
        key = self.api_key.strip()
        if len(key) < 10:
            return False, "DeepL APIキーの形式が不正です"

        return True, "OK"

    def get_usage(self) -> Optional[dict]:
        """API使用状況を取得"""
        if not self.api_key or not self.api_key.strip():
            return {'character_count': 0, 'character_limit': 0, 'error': 'APIキー未設定'}

        endpoint = self._get_usage_endpoint()
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}

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

    def _build_payload(self, text: str, mode: TranslateMode) -> tuple[dict, str, str]:
        """
        リクエストペイロードを構築

        Returns:
            tuple[dict, str, str]: (payload, source_lang, target_lang)
        """
        if mode == TranslateMode.EN_TO_JA:
            source_lang = 'EN'
            target_lang = 'JA'
        elif mode == TranslateMode.JA_TO_EN:
            source_lang = 'JA'
            target_lang = 'EN'
        else:  # AUTO
            if _is_japanese(text):
                source_lang = 'JA'
                target_lang = 'EN'
            else:
                source_lang = None  # DeepLに判定させる
                target_lang = 'JA'

        data = {
            "text": text,
            "target_lang": target_lang,
            "tag_handling": "xml",
            "ignore_tags": "k",
        }
        if source_lang:
            data["source_lang"] = source_lang

        return data, source_lang or "AUTO", target_lang

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, DeepLRetryableError)),
        reraise=True
    )
    async def _request_async(self, payload: dict) -> tuple[int, str, Optional[dict]]:
        """非同期HTTPリクエスト"""
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
        endpoint = self._get_endpoint()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status in (429, 503):
                    logger.warning(f"DeepL rate limited ({resp.status}). Will retry...")
                    raise DeepLRetryableError(f"Rate limited: {resp.status}")
                body = await resp.text()
                result = await resp.json() if resp.status == 200 else None
                return resp.status, body, result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, DeepLRetryableError)),
        reraise=True
    )
    def _request_sync(self, payload: dict) -> tuple[int, str, Optional[dict]]:
        """同期HTTPリクエスト"""
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
        endpoint = self._get_endpoint()

        resp = requests.post(endpoint, data=payload, headers=headers, timeout=30)
        if resp.status_code in (429, 503):
            logger.warning(f"DeepL rate limited ({resp.status_code}). Will retry...")
            raise DeepLRetryableError(f"Rate limited: {resp.status_code}")
        result = resp.json() if resp.status_code == 200 else None
        return resp.status_code, resp.text, result

    async def translate(self, text: str, mode: TranslateMode) -> TranslateResult:
        """非同期翻訳"""
        if not self.api_key:
            return TranslateResult(
                success=False,
                translated_text=text,
                error="DeepL APIキーが設定されていません"
            )

        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        payload, source_lang, target_lang = self._build_payload(text, mode)

        try:
            status, body, result = await self._request_async(payload)
            if status == 200 and result:
                translated = result["translations"][0]["text"]
                return TranslateResult(
                    success=True,
                    translated_text=translated,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
            else:
                logger.error(f"DeepL API Error: {status} {body}")
                return TranslateResult(
                    success=False,
                    translated_text=text,
                    error=f"API Error: {status}"
                )
        except DeepLRetryableError:
            logger.error("DeepL API retry exhausted")
            return TranslateResult(success=False, translated_text=text, error="Rate limit exceeded")
        except Exception as e:
            logger.error(f"DeepL request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))

    def translate_sync(self, text: str, mode: TranslateMode) -> TranslateResult:
        """同期翻訳"""
        if not self.api_key:
            return TranslateResult(
                success=False,
                translated_text=text,
                error="DeepL APIキーが設定されていません"
            )

        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        payload, source_lang, target_lang = self._build_payload(text, mode)

        try:
            status, body, result = self._request_sync(payload)
            if status == 200 and result:
                translated = result["translations"][0]["text"]
                return TranslateResult(
                    success=True,
                    translated_text=translated,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
            else:
                logger.error(f"DeepL API Error: {status} {body}")
                return TranslateResult(
                    success=False,
                    translated_text=text,
                    error=f"API Error: {status}"
                )
        except DeepLRetryableError:
            logger.error("DeepL API retry exhausted")
            return TranslateResult(success=False, translated_text=text, error="Rate limit exceeded")
        except Exception as e:
            logger.error(f"DeepL request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))
