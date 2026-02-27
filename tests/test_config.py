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
    assert validated["stt_vad_threshold"] == 0.5


def test_stt_vad_threshold_clamped():
    validated, _ = validate_config({"stt_vad_threshold": 2.0})
    assert validated["stt_vad_threshold"] == 1.0


def test_stt_vad_threshold_invalid():
    validated, changed = validate_config({"stt_vad_threshold": "abc"})
    assert validated["stt_vad_threshold"] == 0.5
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
