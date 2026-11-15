"""実際のloopback HTTP境界と、GUIへ渡す操作の検証。外部接続はしない。"""

from concurrent.futures import ThreadPoolExecutor
import math
from threading import Event, Thread
import time

import pytest
import requests

from src.web_control import ControlBridge, ControlError, validate_command
from src.web_ui import WebUIServer


@pytest.fixture
def ui():
    bridge = ControlBridge()
    bridge.publish({"channel": "test_channel", "comments": []})
    server = WebUIServer(bridge, command_timeout=0.15)
    server.start()
    yield server, bridge
    server.close()
    assert not server._thread.is_alive()


def headers(server):
    return {"Authorization": f"Bearer {server._token}", "Origin": server.origin}


def test_server_binds_only_loopback_and_serves_allowlisted_assets(ui):
    server, _ = ui
    assert server.origin.startswith("http://127.0.0.1:")
    for route, content_type in [("/", "text/html"), ("/dock", "text/html"),
                                ("/app.js", "text/javascript"), ("/app.css", "text/css"),
                                ("/icon.ico", "image/x-icon")]:
        response = requests.get(server.origin + route, timeout=2)
        assert response.status_code == 200
        assert content_type in response.headers["Content-Type"]
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert server._token not in response.text
    for route in ("/config.json", "/src/auth.py", "/../config.json", "/%2e%2e/config.json"):
        assert requests.get(server.origin + route, timeout=2).status_code == 404


def test_state_requires_session_and_is_read_only(ui):
    server, bridge = ui
    response = requests.get(server.origin + "/api/state", timeout=2)
    assert response.status_code == 401
    assert "Access-Control-Allow-Origin" not in response.headers
    response = requests.get(server.origin + "/api/state", headers=headers(server), timeout=2)
    assert response.status_code == 200
    assert response.json() == bridge.snapshot()
    assert not bridge._commands.qsize()


@pytest.mark.parametrize("extra", [
    {"Origin": "http://untrusted.invalid"}, {"Origin": "null"},
    {"Host": "untrusted.invalid"}, {"Host": "127.0.0.1"},
    {"Sec-Fetch-Site": "cross-site"}, {"Authorization": "Bearer invalid-session"},
])
def test_untrusted_requests_never_enqueue_operations(ui, extra):
    server, bridge = ui
    response = requests.post(server.origin + "/api/command", json={"action": "start"},
                             headers={**headers(server), **extra}, timeout=2)
    assert response.status_code in (401, 403)
    assert bridge._commands.empty()


def test_post_requires_origin_even_with_valid_session(ui):
    server, bridge = ui
    response = requests.post(server.origin + "/api/command", json={"action": "stop"},
                             headers={"Authorization": headers(server)["Authorization"]}, timeout=2)
    assert response.status_code == 403
    assert bridge._commands.empty()


@pytest.mark.parametrize("data,content_type,status", [
    ('{"action":"stop"}', "text/plain", 415),
    ("{", "application/json", 400),
    ('{"action":"volume","value":NaN}', "application/json", 400),
    (" " * 17000, "application/json", 413),
])
def test_body_validation(ui, data, content_type, status):
    server, bridge = ui
    response = requests.post(server.origin + "/api/command", data=data,
                             headers={**headers(server), "Content-Type": content_type}, timeout=2)
    assert response.status_code == status
    assert bridge._commands.empty()


@pytest.mark.parametrize("command", [
    None, [], {}, {"action": "delete"}, {"action": "start", "value": True},
    {"action": "translation", "value": "false"}, {"action": "include_name", "value": 1},
    {"action": "volume", "value": True}, {"action": "volume", "value": 101},
    {"action": "volume", "value": 10 ** 400},
    {"action": "volume", "value": -1}, {"action": "speed", "value": 0.1},
    {"action": "speed", "value": math.inf}, {"action": "speed", "value": math.nan},
    {"action": "language", "value": "unknown"}, {"action": "language", "value": []},
    {"action": "settings", "token": "not-a-real-credential"},
])
def test_invalid_commands_rejected_before_gui(command):
    with pytest.raises(ControlError):
        validate_command(command)


@pytest.mark.parametrize("command", [
    {"action": "start"}, {"action": "stop"}, {"action": "settings"},
    {"action": "translation", "value": False}, {"action": "include_name", "value": True},
    {"action": "volume", "value": 0}, {"action": "speed", "value": 2},
    {"action": "language", "value": "日→英"},
])
def test_allowed_commands(command):
    assert validate_command(command) == command


def test_http_operation_executes_only_on_owner_thread(ui):
    server, bridge = ui
    applied = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        response = pool.submit(requests.post, server.origin + "/api/command",
                               json={"action": "volume", "value": 25},
                               headers=headers(server), timeout=2)
        deadline = time.monotonic() + 1
        while bridge._commands.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not bridge._commands.empty()
        assert not applied
        def handler(command):
            applied.append(command)
            return {"tts_volume": command["value"]}
        bridge.drain(handler)
        result = response.result()
    assert result.status_code == 200
    assert result.json() == {"tts_volume": 25}
    assert applied == [{"action": "volume", "value": 25}]


def test_timed_out_pending_command_is_never_executed_later(ui):
    server, bridge = ui
    response = requests.post(server.origin + "/api/command", json={"action": "start"},
                             headers=headers(server), timeout=2)
    assert response.status_code == 504
    applied = []
    bridge.drain(applied.append)
    assert not applied


def test_bridge_copy_queue_limit_close_and_cancel():
    bridge = ControlBridge()
    state = {"comments": ["first"]}
    bridge.publish(state)
    state["comments"].append("second")
    view = bridge.snapshot()
    view["comments"].append("third")
    assert bridge.snapshot()["comments"] == ["first"]
    futures = [bridge.submit({"action": "stop"}) for _ in range(16)]
    with pytest.raises(ControlError) as error:
        bridge.submit({"action": "stop"})
    assert error.value.status == 429
    bridge.close()
    assert all(future.cancelled() for future in futures)
    with pytest.raises(ControlError):
        bridge.submit({"action": "start"})
    with pytest.raises(ControlError):
        bridge.snapshot()


def test_unexpected_errors_do_not_expose_exception_content(ui):
    server, bridge = ui
    stop = Event()
    def failing_handler(_command):
        raise ValueError("private diagnostic must not be returned")
    def owner():
        while not stop.wait(0.005):
            bridge.drain(failing_handler)
    thread = Thread(target=owner)
    thread.start()
    try:
        response = requests.post(server.origin + "/api/command", json={"action": "start"},
                                 headers=headers(server), timeout=2)
        assert response.status_code == 500
        assert "private diagnostic" not in response.text
    finally:
        stop.set()
        thread.join()


def test_old_session_is_invalid_after_server_restart(ui):
    server, _ = ui
    other = WebUIServer(ControlBridge())
    other.start()
    try:
        response = requests.get(other.origin + "/api/state", headers={
            "Authorization": headers(server)["Authorization"], "Origin": other.origin}, timeout=2)
        assert response.status_code == 401
    finally:
        other.close()
