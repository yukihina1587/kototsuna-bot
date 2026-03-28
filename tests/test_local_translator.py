# -*- coding: utf-8 -*-
"""src/local_translator.py のユニットテスト"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.local_translator import (
    LocalTranslator,
    _get_models_dir,
    get_local_translation_unavailable_reason,
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

    @patch("src.local_translator._HAS_CT2", False)
    def test_unavailable_reason_for_missing_ctranslate2(self):
        assert get_local_translation_unavailable_reason() == "ctranslate2 が未インストールです"

    @patch("src.local_translator._HAS_CT2", True)
    @patch("src.local_translator._HAS_SPM", False)
    def test_unavailable_reason_for_missing_sentencepiece(self):
        assert get_local_translation_unavailable_reason() == "sentencepiece が未インストールです"

    @patch("src.local_translator._HAS_CT2", True)
    @patch("src.local_translator._HAS_SPM", True)
    @patch("src.local_translator._get_models_dir")
    @patch("os.path.isfile")
    def test_unavailable_reason_for_missing_model_files(self, mock_isfile, mock_dir):
        mock_dir.return_value = "/fake/models"
        mock_isfile.return_value = False
        reason = get_local_translation_unavailable_reason()
        assert reason is not None
        assert "翻訳モデルが不足しています" in reason


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
    def test_translate_ja_en(self, mock_spm, mock_ct2):
        """日→英翻訳フロー"""
        # Mock SentencePiece (single tokenizer for NLLB)
        mock_sp = MagicMock()
        mock_sp.encode.return_value = ["▁こんにちは", "世界"]
        mock_sp.decode.return_value = "Hello world"
        mock_spm.SentencePieceProcessor.return_value = mock_sp

        # Mock CTranslate2
        mock_result = MagicMock()
        mock_result.hypotheses = [["eng_Latn", "▁Hello", "▁world"]]
        mock_translator = MagicMock()
        mock_translator.translate_batch.return_value = [mock_result]
        mock_ct2.Translator.return_value = mock_translator

        t = LocalTranslator()
        with patch("os.getcwd", return_value="/fake"), \
             patch("os.chdir"):
            result = t.translate("こんにちは世界", "ja-en")

        assert result == "Hello world"
        assert t.is_loaded("ja-en") is True

        # Verify source format: [src_lang] + tokens + ["</s>"]
        call_args = mock_translator.translate_batch.call_args
        source = call_args[0][0][0]
        assert source[0] == "jpn_Jpan"
        assert source[-1] == "</s>"
        # Verify target_prefix
        assert call_args[1]["target_prefix"] == [["eng_Latn"]]

    @patch("src.local_translator.ctranslate2")
    @patch("src.local_translator.spm")
    def test_translate_en_ja(self, mock_spm, mock_ct2):
        """英→日翻訳フロー"""
        mock_sp = MagicMock()
        mock_sp.encode.return_value = ["▁Hello"]
        mock_sp.decode.return_value = "こんにちは"
        mock_spm.SentencePieceProcessor.return_value = mock_sp

        mock_result = MagicMock()
        mock_result.hypotheses = [["jpn_Jpan", "▁こんにちは"]]
        mock_translator = MagicMock()
        mock_translator.translate_batch.return_value = [mock_result]
        mock_ct2.Translator.return_value = mock_translator

        t = LocalTranslator()
        with patch("os.getcwd", return_value="/fake"), \
             patch("os.chdir"):
            result = t.translate("Hello", "en-ja")

        assert result == "こんにちは"
        # Verify source uses eng_Latn prefix
        call_args = mock_translator.translate_batch.call_args
        source = call_args[0][0][0]
        assert source[0] == "eng_Latn"
        assert call_args[1]["target_prefix"] == [["jpn_Jpan"]]

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

    @patch("src.local_translator.ctranslate2")
    @patch("src.local_translator.spm")
    def test_single_model_for_both_directions(self, mock_spm, mock_ct2):
        """NLLB-200は1モデルで双方向翻訳"""
        mock_sp = MagicMock()
        mock_sp.encode.return_value = ["▁test"]
        mock_sp.decode.return_value = "result"
        mock_spm.SentencePieceProcessor.return_value = mock_sp

        mock_result = MagicMock()
        mock_result.hypotheses = [["eng_Latn", "▁result"]]
        mock_translator = MagicMock()
        mock_translator.translate_batch.return_value = [mock_result]
        mock_ct2.Translator.return_value = mock_translator

        t = LocalTranslator()
        with patch("os.getcwd", return_value="/fake"), \
             patch("os.chdir"):
            t.translate("test", "ja-en")
            t.translate("test", "en-ja")

        # CTranslate2.Translator should be created only once
        assert mock_ct2.Translator.call_count == 1
