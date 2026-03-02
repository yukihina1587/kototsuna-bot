# -*- coding: utf-8 -*-
"""ローカル翻訳エンジン (CTranslate2 + OPUS-MT)

CTranslate2 + SentencePieceを使用したオフライン翻訳。
Helsinki-NLP/OPUS-MT ja-en / en-jap モデルのINT8量子化版を使用。
"""

import os
import sys
import threading
from typing import Optional

from src.logger import logger

# Optional dependencies
try:
    import ctranslate2
    _HAS_CT2 = True
except ImportError:
    ctranslate2 = None  # type: ignore[assignment]
    _HAS_CT2 = False

try:
    import sentencepiece as spm
    _HAS_SPM = True
except ImportError:
    spm = None  # type: ignore[assignment]
    _HAS_SPM = False


# Model directory names under models/
_JA_EN_MODEL_DIR = "opus-mt-ja-en"
_EN_JA_MODEL_DIR = "opus-mt-en-jap"

# Required files in each model directory
_REQUIRED_FILES = ["model.bin", "source.spm", "target.spm"]


def _get_models_dir() -> str:
    """モデルディレクトリのパスを返す。"""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", ""), "models")
    return os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "models"
    )


def is_local_translation_available() -> bool:
    """ローカル翻訳が利用可能か確認する。"""
    if not _HAS_CT2 or not _HAS_SPM:
        return False

    models_dir = _get_models_dir()
    for model_name in [_JA_EN_MODEL_DIR, _EN_JA_MODEL_DIR]:
        model_path = os.path.join(models_dir, model_name)
        for filename in _REQUIRED_FILES:
            filepath = os.path.join(model_path, filename)
            if not os.path.isfile(filepath):
                logger.warning(f"Local translation model file missing: {filepath}")
                return False
    return True


class _ModelPair:
    """CTranslate2 Translator + SentencePiece tokenizer pair."""

    def __init__(
        self,
        translator: "ctranslate2.Translator",
        source_sp: "spm.SentencePieceProcessor",
        target_sp: "spm.SentencePieceProcessor",
    ):
        self.translator = translator
        self.source_sp = source_sp
        self.target_sp = target_sp


class LocalTranslator:
    """CTranslate2 + OPUS-MT ローカル翻訳エンジン。

    モデルは初回翻訳時に遅延ロードされる。
    """

    def __init__(self) -> None:
        self._ja_en: Optional[_ModelPair] = None
        self._en_ja: Optional[_ModelPair] = None
        self._lock = threading.Lock()
        self._models_dir = _get_models_dir()

    def _load_model(self, model_name: str) -> _ModelPair:
        """モデルをロードする。非ASCIIパス対策でCWD+相対パスを使用。"""
        model_path = os.path.join(self._models_dir, model_name)
        base_dir = os.path.dirname(self._models_dir)
        rel_model = os.path.join("models", model_name)

        prev_cwd = os.getcwd()
        try:
            os.chdir(base_dir)

            translator = ctranslate2.Translator(
                rel_model, device="cpu", compute_type="int8"
            )

            source_sp = spm.SentencePieceProcessor()
            source_sp.load(os.path.join(rel_model, "source.spm"))

            target_sp = spm.SentencePieceProcessor()
            target_sp.load(os.path.join(rel_model, "target.spm"))

            logger.info(f"Local translation model loaded: {model_name}")
            return _ModelPair(translator, source_sp, target_sp)
        finally:
            os.chdir(prev_cwd)

    def _get_model(self, direction: str) -> _ModelPair:
        """指定方向のモデルを取得（遅延ロード）。"""
        with self._lock:
            if direction == "ja-en":
                if self._ja_en is None:
                    self._ja_en = self._load_model(_JA_EN_MODEL_DIR)
                return self._ja_en
            else:
                if self._en_ja is None:
                    self._en_ja = self._load_model(_EN_JA_MODEL_DIR)
                return self._en_ja

    def translate(self, text: str, direction: str) -> str:
        """テキストを翻訳する。

        Args:
            text: 翻訳対象のテキスト
            direction: "ja-en" or "en-ja"

        Returns:
            翻訳結果。エラー時は元テキスト
        """
        if not text or not text.strip():
            return text

        try:
            pair = self._get_model(direction)
            source_tokens = pair.source_sp.encode(text, out_type=str)
            results = pair.translator.translate_batch([source_tokens])
            output_tokens = results[0].hypotheses[0]
            translated = pair.target_sp.decode(output_tokens)
            return translated
        except Exception as e:
            logger.error(f"Local translation error ({direction}): {e}", exc_info=True)
            return text

    def is_loaded(self, direction: str) -> bool:
        """指定方向のモデルがロード済みか。"""
        if direction == "ja-en":
            return self._ja_en is not None
        return self._en_ja is not None


_translator: Optional[LocalTranslator] = None
_translator_lock = threading.Lock()


def get_local_translator() -> Optional[LocalTranslator]:
    """LocalTranslatorのシングルトンを取得する。利用不可ならNone。"""
    global _translator
    if not is_local_translation_available():
        return None
    with _translator_lock:
        if _translator is None:
            _translator = LocalTranslator()
        return _translator
