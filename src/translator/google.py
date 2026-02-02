"""
Google Cloud Translation API翻訳エンジン

Google Cloud Translation API v2を使用した翻訳。
"""

import re
import aiohttp
import asyncio
import requests
from typing import Optional

from src.logger import logger
from src.translator.base import TranslatorInterface, TranslateMode, TranslateResult


GOOGLE_TRANSLATE_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"


def _is_japanese(text: str) -> bool:
    """テキストに日本語が含まれているか判定"""
    if not text:
        return False
    jp_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
    return bool(jp_pattern.search(text))


class GoogleTranslator(TranslatorInterface):
    """Google Cloud Translation翻訳エンジン"""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Google Cloud APIキー
        """
        self.api_key = api_key

    def get_name(self) -> str:
        return "Google翻訳"

    def validate_config(self) -> tuple[bool, str]:
        """APIキーの検証"""
        if not self.api_key or not self.api_key.strip():
            return False, "Google Cloud APIキーが設定されていません"

        # 基本的なフォーマットチェック
        key = self.api_key.strip()
        if len(key) < 10:
            return False, "Google Cloud APIキーの形式が不正です"

        return True, "OK"

    def get_usage(self) -> Optional[dict]:
        """Google Translate APIは使用量APIを直接提供しない"""
        return None

    def _get_lang_params(self, text: str, mode: TranslateMode) -> tuple[Optional[str], str]:
        """
        言語パラメータを取得

        Returns:
            tuple[Optional[str], str]: (source_lang, target_lang)
        """
        if mode == TranslateMode.EN_TO_JA:
            return 'en', 'ja'
        elif mode == TranslateMode.JA_TO_EN:
            return 'ja', 'en'
        else:  # AUTO
            if _is_japanese(text):
                return 'ja', 'en'
            else:
                return None, 'ja'  # ソース言語は自動検出

    async def translate(self, text: str, mode: TranslateMode) -> TranslateResult:
        """非同期翻訳"""
        if not self.api_key:
            return TranslateResult(
                success=False,
                translated_text=text,
                error="Google Cloud APIキーが設定されていません"
            )

        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        source_lang, target_lang = self._get_lang_params(text, mode)

        params = {
            "key": self.api_key,
            "q": text,
            "target": target_lang,
            "format": "text",
        }
        if source_lang:
            params["source"] = source_lang

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GOOGLE_TRANSLATE_ENDPOINT,
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        translated = result["data"]["translations"][0]["translatedText"]
                        detected_source = result["data"]["translations"][0].get("detectedSourceLanguage", source_lang)
                        return TranslateResult(
                            success=True,
                            translated_text=translated,
                            source_lang=detected_source or "AUTO",
                            target_lang=target_lang
                        )
                    else:
                        body = await resp.text()
                        logger.error(f"Google Translate API Error: {resp.status} {body}")
                        return TranslateResult(
                            success=False,
                            translated_text=text,
                            error=f"API Error: {resp.status}"
                        )
        except asyncio.TimeoutError:
            logger.error("Google Translate API timeout")
            return TranslateResult(success=False, translated_text=text, error="Timeout")
        except Exception as e:
            logger.error(f"Google Translate request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))

    def translate_sync(self, text: str, mode: TranslateMode) -> TranslateResult:
        """同期翻訳"""
        if not self.api_key:
            return TranslateResult(
                success=False,
                translated_text=text,
                error="Google Cloud APIキーが設定されていません"
            )

        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        source_lang, target_lang = self._get_lang_params(text, mode)

        params = {
            "key": self.api_key,
            "q": text,
            "target": target_lang,
            "format": "text",
        }
        if source_lang:
            params["source"] = source_lang

        try:
            resp = requests.post(GOOGLE_TRANSLATE_ENDPOINT, data=params, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                translated = result["data"]["translations"][0]["translatedText"]
                detected_source = result["data"]["translations"][0].get("detectedSourceLanguage", source_lang)
                return TranslateResult(
                    success=True,
                    translated_text=translated,
                    source_lang=detected_source or "AUTO",
                    target_lang=target_lang
                )
            else:
                logger.error(f"Google Translate API Error: {resp.status_code} {resp.text}")
                return TranslateResult(
                    success=False,
                    translated_text=text,
                    error=f"API Error: {resp.status_code}"
                )
        except requests.exceptions.Timeout:
            logger.error("Google Translate API timeout")
            return TranslateResult(success=False, translated_text=text, error="Timeout")
        except Exception as e:
            logger.error(f"Google Translate request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))
