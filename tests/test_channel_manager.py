"""
Tests for src/channel_manager.py
"""
from unittest.mock import patch, MagicMock
import pytest
from src.channel_manager import (
    normalize_channel_name,
    get_history,
    add_to_history,
    remove_from_history,
    validate_channel,
    clear_validation_cache,
    HISTORY_MAX,
)


# ---------------------------------------------------------------------------
# normalize_channel_name
# ---------------------------------------------------------------------------

def test_normalize_lowercase():
    assert normalize_channel_name("YukkiHina_Yukky") == "yukkihina_yukky"

def test_normalize_url_https():
    assert normalize_channel_name("https://twitch.tv/YukkiHina_Yukky") == "yukkihina_yukky"

def test_normalize_url_no_scheme():
    assert normalize_channel_name("twitch.tv/SomeChannel") == "somechannel"

def test_normalize_strips_whitespace():
    assert normalize_channel_name("  hello  ") == "hello"

def test_normalize_already_lowercase():
    assert normalize_channel_name("abc123") == "abc123"


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

def test_get_history_empty():
    assert get_history({}) == []

def test_get_history_returns_copy():
    config = {"channel_history": [{"login": "a", "display_name": "A", "user_id": "", "last_connected_at": ""}]}
    h = get_history(config)
    h.clear()
    assert len(config["channel_history"]) == 1


# ---------------------------------------------------------------------------
# add_to_history
# ---------------------------------------------------------------------------

def test_add_to_history_basic():
    config = {}
    add_to_history(config, "testchannel", "TestChannel", "123")
    assert config["channel_history"][0]["login"] == "testchannel"
    assert config["channel_history"][0]["display_name"] == "TestChannel"
    assert config["channel_history"][0]["user_id"] == "123"

def test_add_to_history_lowercases_login():
    config = {}
    add_to_history(config, "MyChannel")
    assert config["channel_history"][0]["login"] == "mychannel"

def test_add_to_history_deduplication():
    config = {}
    add_to_history(config, "chan", "Chan1")
    add_to_history(config, "chan", "Chan2")
    assert len(config["channel_history"]) == 1
    assert config["channel_history"][0]["display_name"] == "Chan2"

def test_add_to_history_moves_to_front():
    config = {}
    add_to_history(config, "first")
    add_to_history(config, "second")
    add_to_history(config, "first")  # re-add
    assert config["channel_history"][0]["login"] == "first"
    assert config["channel_history"][1]["login"] == "second"

def test_add_to_history_max_limit():
    config = {}
    for i in range(HISTORY_MAX + 5):
        add_to_history(config, f"channel{i}")
    assert len(config["channel_history"]) == HISTORY_MAX

def test_add_to_history_default_display_name():
    config = {}
    add_to_history(config, "mychan")
    assert config["channel_history"][0]["display_name"] == "mychan"


# ---------------------------------------------------------------------------
# remove_from_history
# ---------------------------------------------------------------------------

def test_remove_from_history():
    config = {"channel_history": [
        {"login": "a", "display_name": "A", "user_id": "", "last_connected_at": ""},
        {"login": "b", "display_name": "B", "user_id": "", "last_connected_at": ""},
    ]}
    remove_from_history(config, "a")
    assert len(config["channel_history"]) == 1
    assert config["channel_history"][0]["login"] == "b"

def test_remove_from_history_case_insensitive():
    config = {"channel_history": [
        {"login": "mychan", "display_name": "MyChan", "user_id": "", "last_connected_at": ""},
    ]}
    remove_from_history(config, "MyChan")
    assert len(config["channel_history"]) == 0

def test_remove_from_history_nonexistent():
    config = {"channel_history": [
        {"login": "a", "display_name": "A", "user_id": "", "last_connected_at": ""},
    ]}
    remove_from_history(config, "z")
    assert len(config["channel_history"]) == 1


# ---------------------------------------------------------------------------
# config.py migration
# ---------------------------------------------------------------------------

def test_validate_config_adds_channel_history():
    from src.config import validate_config
    validated, changed = validate_config({"channel_name": "yukky"})
    assert "channel_history" in validated
    # 既存 channel_name から移行されているはず
    assert any(h["login"] == "yukky" for h in validated["channel_history"])

def test_validate_config_channel_history_not_overwritten():
    from src.config import validate_config
    existing = [{"login": "existing", "display_name": "Existing", "user_id": "", "last_connected_at": ""}]
    validated, _ = validate_config({"channel_history": existing, "channel_name": "other"})
    assert validated["channel_history"][0]["login"] == "existing"

def test_validate_config_channel_history_normalizes():
    from src.config import validate_config
    raw = {"channel_history": [{"login": "MixedCase", "display_name": "MC", "user_id": "1", "last_connected_at": "x"}]}
    validated, _ = validate_config(raw)
    assert validated["channel_history"][0]["login"] == "mixedcase"


# ---------------------------------------------------------------------------
# validate_channel (mocked)
# ---------------------------------------------------------------------------

def _make_mock_response(status_code, json_data):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


def test_validate_channel_valid():
    clear_validation_cache()
    with patch("requests.get", return_value=_make_mock_response(200, {"data": [{"display_name": "TestUser", "id": "42"}]})):
        valid, display_name, user_data = validate_channel("token", "client_id", "testuser")
    assert valid is True
    assert display_name == "TestUser"
    assert user_data["id"] == "42"


def test_validate_channel_not_found():
    clear_validation_cache()
    with patch("requests.get", return_value=_make_mock_response(200, {"data": []})):
        valid, display_name, user_data = validate_channel("token", "client_id", "ghostchannel")
    assert valid is False
    assert display_name == ""


def test_validate_channel_rate_limited():
    clear_validation_cache()
    with patch("requests.get", return_value=_make_mock_response(429, {})):
        valid, _, _ = validate_channel("token", "client_id", "anychannel")
    assert valid is None


def test_validate_channel_cache_hit():
    clear_validation_cache()
    mock_resp = _make_mock_response(200, {"data": [{"display_name": "Cached", "id": "99"}]})
    with patch("requests.get", return_value=mock_resp) as mock_get:
        validate_channel("token", "client_id", "cachedchan")
        validate_channel("token", "client_id", "cachedchan")  # 2回目はキャッシュ
    assert mock_get.call_count == 1


def test_validate_channel_network_error():
    clear_validation_cache()
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        valid, _, _ = validate_channel("token", "client_id", "errortest")
    assert valid is None
