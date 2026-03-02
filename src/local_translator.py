# -*- coding: utf-8 -*-
"""ローカル翻訳エンジン (CTranslate2 + NLLB-200)

CTranslate2 + SentencePieceを使用したオフライン翻訳。
facebook/nllb-200-distilled-600M の INT8量子化版を使用。
1モデルで日英双方向翻訳が可能。
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


# NLLB-200 model directory under models/
_NLLB_MODEL_DIR = "nllb-200-distilled-600M-ct2-int8"

# Required files in the model directory
_REQUIRED_FILES = ["model.bin", "sentencepiece.bpe.model"]

# NLLB-200 language codes
_LANG_JA = "jpn_Jpan"
_LANG_EN = "eng_Latn"


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
    model_path = os.path.join(models_dir, _NLLB_MODEL_DIR)
    for filename in _REQUIRED_FILES:
        filepath = os.path.join(model_path, filename)
        if not os.path.isfile(filepath):
            logger.warning(f"Local translation model file missing: {filepath}")
            return False
    return True


class LocalTranslator:
    """CTranslate2 + NLLB-200 ローカル翻訳エンジン。

    1つのモデルで日英双方向翻訳が可能。
    モデルは初回翻訳時に遅延ロードされる。
    """

    def __init__(self) -> None:
        self._translator: Optional["ctranslate2.Translator"] = None
        self._sp: Optional["spm.SentencePieceProcessor"] = None
        self._lock = threading.Lock()
        self._models_dir = _get_models_dir()

    def _load_model(self) -> None:
        """モデルをロードする。非ASCIIパス対策でCWD+相対パスを使用。"""
        base_dir = os.path.dirname(self._models_dir)
        rel_model = os.path.join("models", _NLLB_MODEL_DIR)

        prev_cwd = os.getcwd()
        try:
            os.chdir(base_dir)

            self._translator = ctranslate2.Translator(
                rel_model, device="cpu", compute_type="int8"
            )

            self._sp = spm.SentencePieceProcessor()
            self._sp.load(os.path.join(rel_model, "sentencepiece.bpe.model"))

            logger.info(f"NLLB-200 translation model loaded: {_NLLB_MODEL_DIR}")
        finally:
            os.chdir(prev_cwd)

    def _ensure_loaded(self) -> None:
        """モデルがロード済みでなければロードする。"""
        with self._lock:
            if self._translator is None:
                self._load_model()

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
            self._ensure_loaded()

            if direction == "ja-en":
                src_lang, tgt_lang = _LANG_JA, _LANG_EN
            else:
                src_lang, tgt_lang = _LANG_EN, _LANG_JA

            # NLLB-200 format: [src_lang] + tokens + ["</s>"]
            tokens = self._sp.encode(text.strip(), out_type=str)
            source = [src_lang] + tokens + ["</s>"]

            n_src = len(tokens)
            max_length = min(n_src * 3 + 10, 512)

            results = self._translator.translate_batch(
                [source],
                target_prefix=[[tgt_lang]],
                max_decoding_length=max_length,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                beam_size=4,
            )

            hypothesis = results[0].hypotheses[0]
            logger.info(f"NLLB raw hypothesis: {hypothesis[:20]}")
            # Remove leading language token
            if hypothesis and hypothesis[0] == tgt_lang:
                hypothesis = hypothesis[1:]

            translated = self._sp.decode(hypothesis)

            # Repetition guard: output too long relative to input
            if len(translated) > len(text) * 5 + 30:
                logger.warning(
                    f"Local translation output too long ({len(translated)} chars "
                    f"vs input {len(text)} chars), likely repetition"
                )
                return text

            return translated
        except Exception as e:
            logger.error(f"Local translation error ({direction}): {e}", exc_info=True)
            return text

    def is_loaded(self, direction: str) -> bool:
        """モデルがロード済みか。NLLB-200は1モデルなのでdirectionに関わらず同じ。"""
        return self._translator is not None


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
