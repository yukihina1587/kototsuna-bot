import json
import os
from src.config import validate_config, DEFAULT_CONFIG, backup_config, restore_config, reset_config


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


def test_window_geometry_default_is_none():
    validated, _ = validate_config({})
    assert validated["window_geometry"] is None


def test_window_geometry_preserved_when_valid():
    geom = "1200x800+100+50"
    validated, changed = validate_config({"window_geometry": geom})
    assert validated["window_geometry"] == geom
    assert changed is False


def test_window_geometry_cleared_when_invalid():
    validated, changed = validate_config({"window_geometry": "not-a-geometry!"})
    assert validated["window_geometry"] is None
    assert changed is True


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


# --- backup / restore / reset tests ---


def test_backup_config_creates_file(tmp_path, monkeypatch):
    import src.config as cfg_mod
    config_src = tmp_path / "config.json"
    config_src.write_text('{"translate_mode": "自動"}', encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(config_src))

    dst = tmp_path / "backup.json"
    result = backup_config(str(dst))

    assert result is True
    assert dst.exists()
    data = json.loads(dst.read_text(encoding="utf-8"))
    assert data["translate_mode"] == "自動"


def test_backup_config_uses_defaults_when_no_config(tmp_path, monkeypatch):
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(tmp_path / "nonexistent.json"))

    dst = tmp_path / "backup.json"
    result = backup_config(str(dst))

    assert result is True
    data = json.loads(dst.read_text(encoding="utf-8"))
    assert data["translate_mode"] == DEFAULT_CONFIG["translate_mode"]


def test_restore_config_writes_validated_data(tmp_path, monkeypatch):
    import src.config as cfg_mod
    config_dst = tmp_path / "config.json"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(config_dst))

    src_file = tmp_path / "src.json"
    src_file.write_text('{"translate_mode": "英→日", "stt_num_threads": 4}', encoding="utf-8")

    result = restore_config(str(src_file))

    assert result is True
    data = json.loads(config_dst.read_text(encoding="utf-8"))
    assert data["translate_mode"] == "英→日"
    assert data["stt_num_threads"] == 4


def test_restore_config_returns_false_on_invalid_json(tmp_path, monkeypatch):
    import src.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(tmp_path / "config.json"))

    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json", encoding="utf-8")

    result = restore_config(str(bad_file))
    assert result is False


def test_reset_config_writes_defaults(tmp_path, monkeypatch):
    import src.config as cfg_mod
    config_dst = tmp_path / "config.json"
    config_dst.write_text('{"translate_mode": "英→日"}', encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(config_dst))

    returned = reset_config()

    assert returned["translate_mode"] == DEFAULT_CONFIG["translate_mode"]
    saved = json.loads(config_dst.read_text(encoding="utf-8"))
    assert saved["translate_mode"] == DEFAULT_CONFIG["translate_mode"]


def test_save_config_rotates_backups(tmp_path, monkeypatch):
    import src.config as cfg_mod
    from src.config import save_config

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(config_file))

    # 1回目の保存（バックアップなし）
    save_config({"translate_mode": "自動"})
    assert config_file.exists()
    bak1 = tmp_path / "config.json.bak"
    assert not bak1.exists()  # まだバックアップなし

    # 2回目：bak が作られる
    save_config({"translate_mode": "英→日"})
    assert bak1.exists()
    assert json.loads(bak1.read_text(encoding="utf-8"))["translate_mode"] == "自動"

    # 3回目：bak.2 が作られる
    save_config({"translate_mode": "日→英"})
    bak2 = tmp_path / "config.json.bak.2"
    assert bak2.exists()
    assert json.loads(bak2.read_text(encoding="utf-8"))["translate_mode"] == "自動"


# --- chat_html_max_entries tests ---


def test_chat_html_max_entries_default():
    validated, _ = validate_config({})
    assert validated["chat_html_max_entries"] == 200


def test_chat_html_max_entries_clamped_upper():
    validated, _ = validate_config({"chat_html_max_entries": 9999})
    assert validated["chat_html_max_entries"] == 5000


def test_chat_html_max_entries_clamped_lower():
    validated, _ = validate_config({"chat_html_max_entries": 0})
    assert validated["chat_html_max_entries"] == 1


def test_chat_html_max_entries_valid():
    validated, _ = validate_config({"chat_html_max_entries": 500})
    assert validated["chat_html_max_entries"] == 500


def test_chat_html_max_entries_invalid_type():
    validated, changed = validate_config({"chat_html_max_entries": "many"})
    assert validated["chat_html_max_entries"] == 200
    assert changed is True
