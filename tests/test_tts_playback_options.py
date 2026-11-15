"""音声デバイスや外部エンジンを動かさず、音量・速度の反映を確認する。"""

import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.fixture
def tts():
    from src.tts import VoicevoxTTS
    with patch.object(VoicevoxTTS, "_check_voicevox_availability", return_value=False):
        instance = VoicevoxTTS()
    return instance


@pytest.mark.parametrize("volume,speed", [(True, 1), (-1, 1), (101, 1), (50, 0), (50, 3), (50, math.nan)])
def test_invalid_options_do_not_change_playback(tts, volume, speed):
    tts.set_playback_options(25, 1.2)
    with pytest.raises(ValueError):
        tts.set_playback_options(volume, speed)
    assert tts._playback_options == (0.25, 1.2)


def test_speed_is_forwarded_to_primary_and_fallback(tts):
    tts.set_playback_options(25, 1.5)
    tts.aio_session = Mock()
    tts.engine = Mock(synthesize_async=AsyncMock(return_value=b"audio"))
    assert asyncio.run(tts._synthesize_voicevox_async("test")) == b"audio"
    assert tts.engine.synthesize_async.call_args.kwargs["speed"] == 1.5
    fallback = Mock(synthesize_async=AsyncMock(return_value=b"fallback"))
    with patch.object(tts, "_get_edge_fallback_engine", return_value=fallback):
        assert asyncio.run(tts._synthesize_edge_fallback_async("test")) == b"fallback"
    assert fallback.synthesize_async.call_args.kwargs["speed"] == 1.5


def test_volume_is_applied_before_and_during_pygame_playback(tts):
    from src import tts as module
    tts.set_playback_options(25, 1)
    pygame = MagicMock()
    calls = iter([True, False])
    def busy():
        assert tts.speaking
        result = next(calls)
        if result:
            tts.set_playback_options(0, 1)
        return result
    pygame.mixer.music.get_busy.side_effect = busy
    with patch.object(module, "AUDIO_AVAILABLE", True), patch.object(module, "pygame", pygame):
        tts.play_audio(b"test audio")
    assert [call.args[0] for call in pygame.mixer.music.set_volume.call_args_list] == [0.25, 0]
    assert not tts.speaking


def test_pyttsx3_fallback_uses_same_volume_and_speed(tts):
    tts.set_playback_options(30, 1.5)
    engine = Mock()
    engine.runAndWait.side_effect = lambda: pytest.fail("Speaking state missing") if not tts.speaking else None
    with patch.object(tts, "_get_pyttsx3_engine", return_value=engine):
        assert tts._speak_pyttsx3("sample")
    engine.setProperty.assert_any_call("volume", 0.3)
    engine.setProperty.assert_any_call("rate", 315)
    assert not tts.speaking


def test_speaking_state_clears_when_fallback_playback_fails(tts):
    engine = Mock(runAndWait=Mock(side_effect=RuntimeError("test playback error")))
    with patch.object(tts, "_get_pyttsx3_engine", return_value=engine):
        assert not tts._speak_pyttsx3("sample")
    assert not tts.speaking


def test_voicevox_query_receives_speed_before_synthesis():
    from src.tts_engines.voicevox import VoicevoxEngine
    query = MagicMock(status=200)
    query.json = AsyncMock(return_value={"speedScale": 1, "accent_phrases": []})
    audio = MagicMock(status=200)
    audio.read = AsyncMock(return_value=b"audio")
    contexts = []
    for response in (query, audio):
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        contexts.append(context)
    session = MagicMock()
    session.post.side_effect = contexts
    result = asyncio.run(VoicevoxEngine().synthesize_async(session, "test", 3, speed=1.4))
    assert result == b"audio"
    assert session.post.call_args_list[1].kwargs["json"]["speedScale"] == 1.4


def test_edge_speed_is_converted_to_rate():
    from src.tts_engines.edge import EdgeTtsEngine
    async def stream():
        yield {"type": "audio", "data": b"audio"}
    communication = Mock(stream=stream)
    edge = Mock(Communicate=Mock(return_value=communication))
    with patch.dict("sys.modules", {"edge_tts": edge}):
        result = asyncio.run(EdgeTtsEngine().synthesize_async(Mock(), "test", "sample-voice", speed=0.8))
    assert result == b"audio"
    edge.Communicate.assert_called_once_with("test", "sample-voice", rate="-20%")


def test_saved_options_are_applied_at_creation(monkeypatch):
    from src import tts as module
    from src import config
    monkeypatch.setattr(module, "_tts_instance", None)
    monkeypatch.setattr(config, "load_config", lambda: {"tts_volume": 18, "tts_speed": 1.3})
    monkeypatch.setattr(module.VoicevoxTTS, "_check_voicevox_availability", lambda _self: False)
    assert module.get_tts_instance()._playback_options == (0.18, 1.3)
