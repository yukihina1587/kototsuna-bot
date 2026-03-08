from src.config import validate_config, DEFAULT_CONFIG


def test_validate_config_fills_defaults_and_clamps_mode():
    raw = {
        "translate_mode": "invalid",
        "voicevox_auto_start": "yes",  # truthy but not bool
        "deepl_api_key": None,
    }
    validated, changed = validate_config(raw)

    assert validated["translate_mode"] == "自動"
    assert validated["voicevox_auto_start"] is True
    assert validated["deepl_api_key"] == ""  # None -> default string
    # 任意の既定値は保たれる
    assert validated["twitch_client_id"] == DEFAULT_CONFIG["twitch_client_id"]
    assert changed is True


# --- STT config tests ---


def test_stt_num_threads_default():
    validated, _ = validate_config({})
    assert validated["stt_num_threads"] == 2


def test_stt_num_threads_clamped():
    validated, _ = validate_config({"stt_num_threads": 20})
    assert validated["stt_num_threads"] == 8


def test_stt_num_threads_invalid():
    validated, changed = validate_config({"stt_num_threads": "abc"})
    assert validated["stt_num_threads"] == 2
    assert changed is True


def test_stt_vad_threshold_default():
    validated, _ = validate_config({})
    assert validated["stt_vad_threshold"] == 0.3


def test_stt_vad_threshold_clamped():
    validated, _ = validate_config({"stt_vad_threshold": 2.0})
    assert validated["stt_vad_threshold"] == 1.0


def test_stt_vad_threshold_invalid():
    validated, changed = validate_config({"stt_vad_threshold": "abc"})
    assert validated["stt_vad_threshold"] == 0.3
    assert changed is True


def test_gladia_keys_removed():
    gladia_keys = [
        "gladia_api_key",
        "gladia_usage_seconds",
        "gladia_reset_month",
        "stt_provider",
    ]
    for key in gladia_keys:
        assert key not in DEFAULT_CONFIG, f"{key} should not exist in DEFAULT_CONFIG"


def test_obs_defaults_present():
    validated, _ = validate_config({})
    assert validated["obs_enabled"] is False
    assert validated["obs_host"] == "127.0.0.1"
    assert validated["obs_port"] == 4455
    assert validated["obs_auto_control_enabled"] is True


def test_obs_values_are_normalized():
    validated, changed = validate_config(
        {
            "obs_enabled": 1,
            "obs_port": "70000",
            "obs_poll_interval_sec": "0.01",
            "obs_scene_rules": [
                {"scene": "休憩", "tts_mute": "yes", "show_sources": ["Alert"], "hide_sources": "bad"},
                {"scene": "", "tts_mute": True},
                "invalid",
            ],
        }
    )
    assert changed is True
    assert validated["obs_enabled"] is True
    assert validated["obs_port"] == 65535
    assert validated["obs_poll_interval_sec"] == 0.2
    assert validated["obs_scene_rules"] == [
        {"scene": "休憩", "tts_mute": True, "show_sources": ["Alert"], "hide_sources": []}
    ]
