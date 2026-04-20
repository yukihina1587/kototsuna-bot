"""TTS エンジン抽象化のテスト（Phase 1 / Issue #25）。

VOICEVOX 互換エンジン（COEIROINK / AivisSpeech / SHAREVOX）は URL プリセットのみが異なる
同一実装なので、共通の ``VoicevoxEngine`` を対象にテストする。
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest


class TestEngineRegistry:
    def test_get_engine_returns_voicevox_by_default(self) -> None:
        from src.tts_engines import get_engine
        from src.tts_engines.voicevox import VoicevoxEngine
        engine = get_engine("voicevox")
        assert isinstance(engine, VoicevoxEngine)
        assert engine.name == "voicevox"
        assert engine.api_url == "http://localhost:50021"

    def test_unknown_engine_falls_back_to_voicevox(self) -> None:
        from src.tts_engines import get_engine
        engine = get_engine("nonexistent")
        assert engine.name == "voicevox"

    def test_preset_urls_for_compatible_engines(self) -> None:
        from src.tts_engines import get_engine
        assert get_engine("coeiroink").api_url == "http://localhost:50032"
        assert get_engine("aivisspeech").api_url == "http://localhost:10101"
        assert get_engine("sharevox").api_url == "http://localhost:50025"

    def test_custom_url_overrides_preset(self) -> None:
        from src.tts_engines import get_engine
        engine = get_engine("coeiroink", "http://192.168.1.10:50032")
        assert engine.api_url == "http://192.168.1.10:50032"

    def test_list_available_engines_includes_all_four(self) -> None:
        from src.tts_engines import list_available_engines
        names = {e["name"] for e in list_available_engines()}
        assert names == {"voicevox", "coeiroink", "aivisspeech", "sharevox"}

    def test_get_preset_url_returns_default_for_unknown(self) -> None:
        from src.tts_engines import get_preset_url
        assert get_preset_url("voicevox") == "http://localhost:50021"
        # Unknown falls back to the base default.
        assert get_preset_url("__missing__") == "http://localhost:50021"


class TestVoicevoxEngineListVoices:
    @patch("requests.get")
    def test_list_voices_returns_flat_entries(self, mock_get: Mock) -> None:
        from src.tts_engines.voicevox import VoicevoxEngine

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "四国めたん", "styles": [{"id": 2, "name": "ノーマル"}]},
            {
                "name": "冥鳴ひまり",
                "styles": [
                    {"id": 14, "name": "ノーマル"},
                    {"id": 15, "name": "あまあま"},
                ],
            },
        ]
        mock_get.return_value = mock_response

        engine = VoicevoxEngine()
        voices = engine.list_voices_sync()

        assert len(voices) == 3
        assert voices[0]["id"] == 2
        assert voices[2]["display"] == "冥鳴ひまり / あまあま"

    @patch("requests.get", side_effect=Exception("Connection refused"))
    def test_list_voices_returns_empty_on_error(self, _mock_get: Mock) -> None:
        from src.tts_engines.voicevox import VoicevoxEngine
        engine = VoicevoxEngine()
        assert engine.list_voices_sync() == []

    @patch("requests.get")
    def test_list_voices_returns_empty_on_non_200(self, mock_get: Mock) -> None:
        from src.tts_engines.voicevox import VoicevoxEngine
        mock_response = Mock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response
        assert VoicevoxEngine().list_voices_sync() == []


class TestViewerStoreAssignedVoiceMigration:
    """旧スキーマ（speaker_id のみ）が読み込めることを確認する。"""

    def test_legacy_schema_yields_voicevox_engine(self, tmp_path) -> None:
        import json

        from src.viewer_store import ViewerStore

        legacy_file = tmp_path / "viewer_data.json"
        legacy_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "viewers": {
                        "alice": {
                            "display_name": "Alice",
                            "visit_count": 3,
                            "first_seen": "2026-01-01T00:00:00",
                            "last_seen": "2026-01-05T00:00:00",
                            "last_session_id": "",
                            "assigned_voice": {
                                "speaker_id": 14,
                                "speaker_name": "冥鳴ひまり / ノーマル",
                                "assigned_by": "mod",
                                "assigned_at": "2026-01-01T00:00:00",
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        store = ViewerStore(filepath=str(legacy_file))
        assert store.get_assigned_voice("alice") == 14
        spec = store.get_assigned_voice_spec("alice")
        assert spec == {
            "engine": "voicevox",
            "voice_id": 14,
            "voice_name": "冥鳴ひまり / ノーマル",
        }

    def test_new_schema_roundtrip(self, tmp_path) -> None:
        from src.viewer_store import ViewerStore

        store = ViewerStore(filepath=str(tmp_path / "viewer_data.json"))
        store.assign_voice(
            username="bob",
            speaker_id=7,
            speaker_name="ずんだもん",
            assigned_by="streamer",
            engine="coeiroink",
        )
        # 再ロードしても同じ値が読めること
        store2 = ViewerStore(filepath=str(tmp_path / "viewer_data.json"))
        assert store2.get_assigned_voice("bob") == 7
        spec = store2.get_assigned_voice_spec("bob")
        assert spec["engine"] == "coeiroink"
        assert spec["voice_name"] == "ずんだもん"
