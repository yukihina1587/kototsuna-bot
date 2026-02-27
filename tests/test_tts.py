"""VoicevoxTTS クラスのテスト"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock


class TestVoicevoxTTS:
    """VoicevoxTTSクラスの基本テスト"""

    def test_import_tts_module(self):
        """ttsモジュールがインポートできることを確認"""
        from src import tts
        assert hasattr(tts, 'VoicevoxTTS')

    @patch('requests.get')
    def test_get_speakers_success(self, mock_get):
        """スピーカー一覧取得の成功ケース"""
        from src.tts import VoicevoxTTS

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "四国めたん", "styles": [{"id": 2, "name": "ノーマル"}]},
            {"name": "ずんだもん", "styles": [{"id": 3, "name": "ノーマル"}]}
        ]
        mock_get.return_value = mock_response

        tts = VoicevoxTTS(api_url="http://localhost:50021")
        speakers = tts.get_speakers_list()

        assert len(speakers) == 2
        assert speakers[0]["name"] == "四国めたん"

    @patch('requests.get')
    def test_get_speakers_failure(self, mock_get):
        """スピーカー一覧取得の失敗ケース"""
        from src.tts import VoicevoxTTS

        mock_get.side_effect = Exception("Connection refused")

        tts = VoicevoxTTS(api_url="http://localhost:50021")
        speakers = tts.get_speakers_list()

        assert speakers == []

    def test_initialization(self):
        """初期化時のデフォルト値を確認"""
        from src.tts import VoicevoxTTS

        tts = VoicevoxTTS(api_url="http://localhost:50021", speaker_id=14)

        assert tts.api_url == "http://localhost:50021"
        assert tts.speaker_id == 14
