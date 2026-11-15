from unittest.mock import Mock
import subprocess

import pytest

from src.desktop_window import DesktopWindow, validate_launch_url


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:1234/#session=sample", "http://localhost:1234/#session=sample",
    "http://127.0.0.1:1234/other#session=sample", "http://127.0.0.1:1234/?token=sample",
    "file:///tmp/file", "http://evil.example:1234/#session=sample",
    "http://user:password@127.0.0.1:1234/#session=sample",
])
def test_only_private_local_endpoint_can_open(url):
    with pytest.raises(ValueError):
        validate_launch_url(url)


def test_launch_uses_pipe_not_command_line_and_owned_child_is_closed(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.stdout = iter([])
    # No reader thread is needed for process ownership assertions.
    monkeypatch.setattr("src.desktop_window.Thread", Mock())
    popen = Mock(return_value=process)
    monkeypatch.setattr("src.desktop_window.subprocess.Popen", popen)
    master = Mock()
    url = "http://127.0.0.1:1234/#session=sample"
    window = DesktopWindow(master, url, Mock(), Mock())
    assert "sample" not in str(popen.call_args)
    assert popen.call_args.kwargs["stdin"] == subprocess.PIPE
    assert "sample" in process.stdin.write.call_args.args[0]
    window.close()
    window.close()
    process.stdin.close.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    process.terminate.assert_not_called()


def test_window_close_and_failed_start_have_different_callbacks(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr("src.desktop_window.Thread", Mock())
    monkeypatch.setattr("src.desktop_window.subprocess.Popen", Mock(return_value=process))
    closed, failed = Mock(), Mock()
    window = DesktopWindow(Mock(), "http://127.0.0.1:1234/#session=sample", closed, failed)
    window._messages.put("READY")
    process.poll.return_value = 0
    window._poll()
    closed.assert_called_once()
    failed.assert_not_called()


def test_unready_host_failure_is_reported_and_pipe_closed(monkeypatch):
    process = Mock()
    process.poll.return_value = 1
    monkeypatch.setattr("src.desktop_window.Thread", Mock())
    monkeypatch.setattr("src.desktop_window.subprocess.Popen", Mock(return_value=process))
    closed, failed = Mock(), Mock()
    DesktopWindow(Mock(), "http://127.0.0.1:1234/#session=sample", closed, failed)
    failed.assert_called_once()
    closed.assert_not_called()
    process.stdin.close.assert_called_once()
