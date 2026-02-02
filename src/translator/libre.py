"""
LibreTranslate翻訳エンジン

オープンソースの翻訳API。セルフホストも可能。
"""

import re
import aiohttp
import asyncio
import requests
from typing import Optional

from src.logger import logger
from src.translator.base import TranslatorInterface, TranslateMode, TranslateResult


DEFAULT_LIBRE_URL = "https://libretranslate.com"


def _is_japanese(text: str) -> bool:
    """テキストに日本語が含まれているか判定"""
    if not text:
        return False
    jp_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
    return bool(jp_pattern.search(text))


class LibreTranslator(TranslatorInterface):
    """LibreTranslate翻訳エンジン"""

    def __init__(self, url: str = DEFAULT_LIBRE_URL, api_key: str = ""):
        """
        Args:
            url: LibreTranslate APIのURL
            api_key: APIキー（公開サーバーの場合は必要な場合あり）
        """
        self.url = url.rstrip('/') if url else DEFAULT_LIBRE_URL
        self.api_key = api_key

    def get_name(self) -> str:
        return "LibreTranslate"

    def _get_translate_endpoint(self) -> str:
        return f"{self.url}/translate"

    def _get_languages_endpoint(self) -> str:
        return f"{self.url}/languages"

    def validate_config(self) -> tuple[bool, str]:
        """設定の検証"""
        if not self.url:
            return False, "LibreTranslate URLが設定されていません"

        # URLの基本チェック
        if not self.url.startswith(("http://", "https://")):
            return False, "URLはhttp://またはhttps://で始まる必要があります"

        return True, "OK"

    def get_usage(self) -> Optional[dict]:
        """LibreTranslateは使用量APIを提供しない"""
        return None

    def _get_lang_params(self, text: str, mode: TranslateMode) -> tuple[str, str]:
        """
        言語パラメータを取得

        Returns:
            tuple[str, str]: (source_lang, target_lang)
        """
        if mode == TranslateMode.EN_TO_JA:
            return 'en', 'ja'
        elif mode == TranslateMode.JA_TO_EN:
            return 'ja', 'en'
        else:  # AUTO
            if _is_japanese(text):
                return 'ja', 'en'
            else:
                return 'auto', 'ja'

    async def translate(self, text: str, mode: TranslateMode) -> TranslateResult:
        """非同期翻訳"""
        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        source_lang, target_lang = self._get_lang_params(text, mode)

        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._get_translate_endpoint(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        translated = result.get("translatedText", text)
                        detected = result.get("detectedLanguage", {})
                        return TranslateResult(
                            success=True,
                            translated_text=translated,
                            source_lang=detected.get("language", source_lang),
                            target_lang=target_lang
                        )
                    else:
                        body = await resp.text()
                        logger.error(f"LibreTranslate API Error: {resp.status} {body}")
                        return TranslateResult(
                            success=False,
                            translated_text=text,
                            error=f"API Error: {resp.status}"
                        )
        except asyncio.TimeoutError:
            logger.error("LibreTranslate API timeout")
            return TranslateResult(success=False, translated_text=text, error="Timeout")
        except aiohttp.ClientError as e:
            logger.error(f"LibreTranslate connection error: {e}")
            return TranslateResult(success=False, translated_text=text, error=f"Connection error: {e}")
        except Exception as e:
            logger.error(f"LibreTranslate request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))

    def translate_sync(self, text: str, mode: TranslateMode) -> TranslateResult:
        """同期翻訳"""
        if not text or not text.strip():
            return TranslateResult(success=True, translated_text=text)

        source_lang, target_lang = self._get_lang_params(text, mode)

        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        try:
            resp = requests.post(
                self._get_translate_endpoint(),
                json=payload,
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()
                translated = result.get("translatedText", text)
                detected = result.get("detectedLanguage", {})
                return TranslateResult(
                    success=True,
                    translated_text=translated,
                    source_lang=detected.get("language", source_lang),
                    target_lang=target_lang
                )
            else:
                logger.error(f"LibreTranslate API Error: {resp.status_code} {resp.text}")
                return TranslateResult(
                    success=False,
                    translated_text=text,
                    error=f"API Error: {resp.status_code}"
                )
        except requests.exceptions.Timeout:
            logger.error("LibreTranslate API timeout")
            return TranslateResult(success=False, translated_text=text, error="Timeout")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"LibreTranslate connection error: {e}")
            return TranslateResult(success=False, translated_text=text, error=f"Connection error: {e}")
        except Exception as e:
            logger.error(f"LibreTranslate request error: {e}", exc_info=True)
            return TranslateResult(success=False, translated_text=text, error=str(e))
