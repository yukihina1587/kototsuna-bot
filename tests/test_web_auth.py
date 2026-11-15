from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

import requests

from src.auth import build_auth_url, run_auth_server_and_get_token


def test_authorization_url_includes_state_and_encodes_it():
    query = parse_qs(urlsplit(build_auth_url("example", state="state+test&value")).query)
    assert query["state"] == ["state+test&value"]


def test_auth_callback_requires_same_origin_and_nonce_and_expires():
    ready, result = Event(), []
    thread = Thread(target=lambda: result.append(run_auth_server_and_get_token(
        on_ready=ready.set, expected_state="test-state", timeout=4)), daemon=True)
    thread.start()
    assert ready.wait(2)
    endpoint = "http://127.0.0.1:8787/token"
    headers = {"Host": "localhost:8787", "Origin": "http://localhost:8787"}
    assert requests.post(endpoint, headers={**headers, "Origin": "https://untrusted.example"},
                         json={"token": "sample", "state": "test-state"}, timeout=2).status_code == 403
    assert requests.post(endpoint, headers=headers, json={"token": "sample", "state": "wrong"}, timeout=2).status_code == 400
    assert requests.post(endpoint, headers=headers, json={"token": "sample", "state": "test-state"}, timeout=2).status_code == 200
    thread.join(2)
    assert result == ["oauth:sample"]
    # 新しい認証試行では前回のトークンを返さない。
    assert run_auth_server_and_get_token(timeout=.01) is None
