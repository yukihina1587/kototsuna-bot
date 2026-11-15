from types import SimpleNamespace

import pytest

from src.web_control import ControlError, validate_command
from src.web_settings import FIELDS, settings_snapshot, validate_settings


@pytest.mark.parametrize("patch", [
    {"twitch_access_token": "not-a-real-credential"}, {"unknown": True}, {}, [],
    {"tts_engine": "arbitrary"}, {"channel_name": "a/b"}, {"channel_name": "a" * 26},
    {"obs_port": True}, {"obs_port": 1.2}, {"obs_port": 65536},
    {"voicevox_speaker_id": -1}, {"stt_vad_threshold": float("nan")},
    {"stt_vad_threshold": float("inf")}, {"voicevox_auto_start": "true"},
    {"tts_engine_url": "file:///tmp/private"}, {"tts_engine_url": "http://a:b@localhost"},
    {"tts_engine_url": "http://localhost:999999"}, {"tts_engine_url": "http://localhost?q=secret"},
    {"ui_theme": "other"}, {"web_workspace_layout": "other"}, {"comment_log_bg": "red; color:blue"},
    {"comment_bubble_style": ""}, {"comment_bubble_style": "unknown"},
    {"obs_host": "host/path"}, {"obs_password": "x\x00y"},
    {"mic_device_index": -1}, {"mic_device_index": False},
    {"voicevox_engine_path": "x" * 1025},
])
def test_settings_reject_unknown_invalid_and_secret_fields(patch):
    with pytest.raises(ControlError):
        validate_command({"action": "save_settings", "value": patch})


def test_settings_are_validated_as_one_patch_before_queueing():
    with pytest.raises(ControlError):
        validate_settings({"channel_name": "valid", "obs_port": 0})
    assert validate_settings({"channel_name": " viewer ", "mic_device_index": None}) == {
        "channel_name": "viewer", "mic_device_index": None}


def test_password_is_write_only_and_blank_preserves_it():
    cfg = {"obs_password": "not-a-real-password", "twitch_access_token": "not-a-real-token",
           "unknown_internal": "private", "tts_engine": "voicevox"}
    result = settings_snapshot(SimpleNamespace(config=cfg))
    assert result["obs_password_set"]
    assert "obs_password" not in result["values"]
    assert "twitch_access_token" not in result["values"]
    assert "not-a-real" not in str(result)
    assert "unknown_internal" not in str(result)
    assert validate_settings({"obs_password": "", "obs_enabled": True}) == {"obs_enabled": True}


def test_all_default_settings_roundtrip_validation():
    result = settings_snapshot(SimpleNamespace(config={}))
    assert validate_settings(result["values"]) == result["values"]
    assert len({f["key"] for f in FIELDS}) == len(FIELDS)


@pytest.mark.parametrize("style", ["classic", "modern", "box", "bubble", "neon", "cute", "minimal"])
def test_legacy_comment_styles_remain_selectable_and_saveable(style):
    result = settings_snapshot(SimpleNamespace(config={"comment_bubble_style": style}))
    rule = next(f for f in result["fields"] if f["key"] == "comment_bubble_style")
    assert style in rule["choices"]
    assert result["values"]["comment_bubble_style"] == style
    assert validate_settings(result["values"]) == result["values"]
