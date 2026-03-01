# -*- coding: utf-8 -*-
"""src/local_translator.py のユニットテスト"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.local_translator import (
    LocalTranslator,
    _get_models_dir,
    is_local_translation_available,
)


# =========================================
# _get_models_dir
# =========================================

class TestGetModelsDir:
    def test_dev_mode(self):
        """開発環境ではプロジェクトルート/models を返す"""
        models_dir = _get_models_dir()
        assert models_dir.endswith("models")
        assert os.path.isabs(models_dir)

    @patch("src.local_translator.sys")
    def test_frozen_mode(self, mock_sys):
        mock_sys.frozen = True
        mock_sys._MEIPASS = "/fake/meipass"
        result = _get_models_dir()
        assert result == os.path.join("/fake/meipass", "models")


# =========================================
# is_local_translation_available
# =========================================

class TestIsLocalTranslationAvailable:
    @patch("src.local_translator._HAS_CT2", False)
    def test_no_ctranslate2(self):
        assert is_local_translation_available() is False

    @patch("src.local_translator._HAS_SPM", False)
    def test_no_sentencepiece(self):
        assert is_local_translation_available() is False

    @patch("src.local_translator._HAS_CT2", True)
    @patch("src.local_translator._HAS_SPM", True)
    @patch("src.local_translator._get_models_dir")
    def test_missing_model_files(self, mock_dir):
        mock_dir.return_value = "/nonexistent/models"
        assert is_local_translation_available() is False

    @patch("src.local_translator._HAS_CT2", True)
    @patch("src.local_translator._HAS_SPM", True)
    @patch("src.local_translator._get_models_dir")
    @patch("os.path.isfile")
    def test_all_files_present(self, mock_isfile, mock_dir):
        mock_dir.return_value = "/fake/models"
        mock_isfile.return_value = True
        assert is_local_translation_available() is True


# =========================================
# LocalTranslator
# =========================================

class TestLocalTranslator:
    def test_translate_empty_text(self):
        """空文字はそのまま返す"""
        t = LocalTranslator()
        assert t.translate("", "ja-en") == ""
        assert t.translate("  ", "ja-en") == "  "

    def test_is_loaded_initial(self):
        """初期状態ではモデル未ロード"""
        t = LocalTranslator()
        assert t.is_loaded("ja-en") is False
        assert t.is_loaded("en-ja") is False

    @patch("src.local_translator.ctranslate2")
    @patch("src.local_translator.spm")
    def test_translate_success(self, mock_spm, mock_ct2):
        """正常な翻訳フロー"""
        # Mock SentencePiece
        mock_source_sp = MagicMock()
        mock_source_sp.encode.return_value = ["▁Hello", "▁world"]
        mock_target_sp = MagicMock()
        mock_target_sp.decode.return_value = "こんにちは世界"
        mock_spm.SentencePieceProcessor.side_effect = [mock_source_sp, mock_target_sp]

        # Mock CTranslate2
        mock_result = MagicMock()
        mock_result.hypotheses = [["▁こんにちは", "世界"]]
        mock_translator = MagicMock()
        mock_translator.translate_batch.return_value = [mock_result]
        mock_ct2.Translator.return_value = mock_translator

        t = LocalTranslator()
        with patch("os.getcwd", return_value="/fake"), \
             patch("os.chdir"):
            result = t.translate("Hello world", "en-ja")

        assert result == "こんにちは世界"
        assert t.is_loaded("en-ja") is True

    @patch("src.local_translator.ctranslate2")
    @patch("src.local_translator.spm")
    def test_translate_error_returns_original(self, mock_spm, mock_ct2):
        """翻訳エラー時は元テキストを返す"""
        mock_ct2.Translator.side_effect = RuntimeError("Model load failed")

        t = LocalTranslator()
        with patch("os.getcwd", return_value="/fake"), \
             patch("os.chdir"):
            result = t.translate("Hello", "en-ja")

        assert result == "Hello"


# =========================================
# translator.py integration (engine routing)
# =========================================

class TestTranslatorEngineRouting:
    def test_set_translation_engine(self):
        from src.translator import set_translation_engine, get_translation_engine
        set_translation_engine("local")
        assert get_translation_engine() == "local"
        set_translation_engine("hybrid")
        assert get_translation_engine() == "hybrid"
        set_translation_engine("deepl")
        assert get_translation_engine() == "deepl"

    def test_set_invalid_engine_ignored(self):
        from src.translator import set_translation_engine, get_translation_engine
        set_translation_engine("deepl")
        set_translation_engine("invalid")
        assert get_translation_engine() == "deepl"
