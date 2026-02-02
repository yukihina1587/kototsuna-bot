"""
翻訳エンジンファクトリ

設定に基づいて適切な翻訳エンジンを生成する。
"""

from typing import Optional

from src.translator.base import TranslatorInterface
from src.translator.deepl import DeepLTranslator
from src.translator.google import GoogleTranslator
from src.translator.libre import LibreTranslator


# 利用可能なエンジン
AVAILABLE_ENGINES = {
    "deepl": "DeepL",
    "google": "Google翻訳",
    "libre": "LibreTranslate",
}


def create_translator(
    engine: str,
    deepl_api_key: str = "",
    google_api_key: str = "",
    libre_url: str = "",
    libre_api_key: str = "",
) -> Optional[TranslatorInterface]:
    """
    翻訳エンジンを生成

    Args:
        engine: エンジン種別 ("deepl", "google", "libre")
        deepl_api_key: DeepL APIキー
        google_api_key: Google Cloud APIキー
        libre_url: LibreTranslate URL
        libre_api_key: LibreTranslate APIキー

    Returns:
        TranslatorInterface or None
    """
    engine = engine.lower().strip() if engine else "deepl"

    if engine == "deepl":
        return DeepLTranslator(api_key=deepl_api_key)
    elif engine == "google":
        return GoogleTranslator(api_key=google_api_key)
    elif engine == "libre":
        return LibreTranslator(url=libre_url, api_key=libre_api_key)
    else:
        # 未知のエンジンはDeepLにフォールバック
        return DeepLTranslator(api_key=deepl_api_key)


def get_engine_display_name(engine: str) -> str:
    """エンジンの表示名を取得"""
    return AVAILABLE_ENGINES.get(engine.lower(), engine)


def get_available_engines() -> dict[str, str]:
    """利用可能なエンジン一覧を取得"""
    return AVAILABLE_ENGINES.copy()
