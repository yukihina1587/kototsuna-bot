"""src/sentry_init.py のテスト。

PII スクラブと無害例外ドロップを検証する。実際の Sentry SDK は不要
（`init_sentry()` は `enabled=False` または SDK 不在時に安全に no-op になる）。
"""
from src.sentry_init import _redact_mapping, _scrub_event, init_sentry


def test_init_sentry_disabled_returns_false():
    assert init_sentry(False) is False


def test_scrub_removes_user_field():
    event = {"user": {"id": "streamer1", "ip": "1.2.3.4"}}
    out = _scrub_event(event, {})
    assert "user" not in out


def test_scrub_masks_oauth_token_in_message():
    event = {"message": "login with oauth:abcdef1234567890"}
    out = _scrub_event(event, {})
    assert "oauth:***" in out["message"]
    assert "abcdef1234567890" not in out["message"]


def test_scrub_redacts_pii_keys_in_extra():
    event = {
        "extra": {
            "channel": "kototsuna_test",
            "comment": "hello",
            "username": "viewer1",
            "safe_field": 42,
        }
    }
    out = _scrub_event(event, {})
    assert out["extra"]["channel"] == "***"
    assert out["extra"]["comment"] == "***"
    assert out["extra"]["username"] == "***"
    assert out["extra"]["safe_field"] == 42


def test_scrub_redacts_breadcrumb_data():
    event = {
        "breadcrumbs": {
            "values": [
                {
                    "message": "Bearer XYZABCDEF1234567",
                    "data": {"username": "foo", "channel": "bar"},
                }
            ]
        }
    }
    out = _scrub_event(event, {})
    crumb = out["breadcrumbs"]["values"][0]
    assert "Bearer ***" in crumb["message"]
    assert crumb["data"]["username"] == "***"
    assert crumb["data"]["channel"] == "***"


def test_scrub_strips_local_vars_from_stacktrace():
    event = {
        "exception": {
            "values": [
                {
                    "value": "boom",
                    "stacktrace": {"frames": [{"vars": {"tok": "secret"}}]},
                }
            ]
        }
    }
    out = _scrub_event(event, {})
    frame = out["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "vars" not in frame


def test_scrub_drops_keyboard_interrupt():
    event = {"message": "interrupted"}
    out = _scrub_event(event, {"exc_info": (KeyboardInterrupt, KeyboardInterrupt(), None)})
    assert out is None


def test_scrub_drops_system_exit():
    event = {"message": "exit"}
    out = _scrub_event(event, {"exc_info": (SystemExit, SystemExit(), None)})
    assert out is None


def test_scrub_keeps_real_exception():
    class MyErr(Exception):
        pass

    event = {"message": "real bug"}
    out = _scrub_event(event, {"exc_info": (MyErr, MyErr("boom"), None)})
    assert out is not None
    assert out["message"] == "real bug"


def test_redact_mapping_recurses_into_nested_dicts():
    data = {"safe": 1, "level1": {"channel": "x", "ok": "y"}}
    out = _redact_mapping(data)
    assert out["safe"] == 1
    assert out["level1"]["channel"] == "***"
    assert out["level1"]["ok"] == "y"


def test_redact_mapping_masks_strings():
    data = {"note": "token leaked: oauth:abcdef1234567890"}
    out = _redact_mapping(data)
    assert "oauth:***" in out["note"]
