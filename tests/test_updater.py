# -*- coding: utf-8 -*-
"""src/updater.py のユニットテスト"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.updater import (
    ReleaseInfo,
    UpdateError,
    _extract_sha256,
    _find_installer_url_for_version,
    check_for_updates,
    clear_rollback_info,
    download_update,
    format_file_size,
    get_rollback_info,
    is_newer,
    parse_version,
    rollback_to_previous,
    save_rollback_info,
)


# =========================================
# parse_version
# =========================================

class TestParseVersion:
    def test_basic(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert parse_version("v1.0.0") == (1, 0, 0)

    def test_with_capital_v(self):
        assert parse_version("V2.10.5") == (2, 10, 5)

    def test_with_extra_text(self):
        assert parse_version("v1.2.3-beta") == (1, 2, 3)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_version("invalid")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_version("")


# =========================================
# is_newer
# =========================================

class TestIsNewer:
    def test_newer_patch(self):
        assert is_newer("1.0.0", "1.0.1") is True

    def test_newer_minor(self):
        assert is_newer("1.0.0", "1.1.0") is True

    def test_newer_major(self):
        assert is_newer("1.0.0", "2.0.0") is True

    def test_same_version(self):
        assert is_newer("1.0.0", "1.0.0") is False

    def test_older(self):
        assert is_newer("1.1.0", "1.0.0") is False

    def test_with_v_prefix(self):
        assert is_newer("v1.0.0", "v1.0.1") is True

    def test_rc_ordering(self):
        assert is_newer("v1.1.3-rc9", "v1.1.3-rc10") is True
        assert is_newer("v1.1.3-rc10", "v1.1.3-rc9") is False
        assert is_newer("v1.1.3-rc10", "v1.1.3") is True

    def test_invalid_returns_false(self):
        assert is_newer("1.0.0", "invalid") is False
        assert is_newer("invalid", "1.0.0") is False


# =========================================
# _extract_sha256
# =========================================

class TestExtractSha256:
    def test_with_backticks(self):
        body = "SHA256: `abc123def456abc123def456abc123def456abc123def456abc123def456abcd`"
        result = _extract_sha256(body)
        assert result == "abc123def456abc123def456abc123def456abc123def456abc123def456abcd"

    def test_without_backticks(self):
        body = "SHA256: abc123def456abc123def456abc123def456abc123def456abc123def456abcd"
        result = _extract_sha256(body)
        assert result == "abc123def456abc123def456abc123def456abc123def456abc123def456abcd"

    def test_in_multiline(self):
        body = """## Changes
- Fixed bugs

SHA256: `aabbccdd11223344aabbccdd11223344aabbccdd11223344aabbccdd11223344`
"""
        result = _extract_sha256(body)
        assert result == "aabbccdd11223344aabbccdd11223344aabbccdd11223344aabbccdd11223344"

    def test_empty_body(self):
        assert _extract_sha256("") == ""
        assert _extract_sha256(None) == ""

    def test_no_hash(self):
        assert _extract_sha256("Just some text") == ""

    def test_uppercase_hash(self):
        body = "SHA256: AABBCCDD11223344AABBCCDD11223344AABBCCDD11223344AABBCCDD11223344"
        result = _extract_sha256(body)
        assert result == "aabbccdd11223344aabbccdd11223344aabbccdd11223344aabbccdd11223344"


# =========================================
# check_for_updates (mocked)
# =========================================

MOCK_RELEASE_DATA = {
    "tag_name": "v1.1.0",
    "name": "Release v1.1.0",
    "body": "## Changes\nSHA256: `aabbccdd11223344aabbccdd11223344aabbccdd11223344aabbccdd11223344`",
    "published_at": "2026-01-01T00:00:00Z",
    "prerelease": False,
    "assets": [
        {
            "name": "Kototsuna_Setup.exe",
            "browser_download_url": "https://github.com/test/releases/download/v1.1.0/Kototsuna_Setup.exe",
            "size": 300000000,
        }
    ],
}


class TestCheckForUpdates:
    @patch("src.updater.requests.get")
    def test_new_version_available(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_RELEASE_DATA
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = check_for_updates("1.0.0", include_prerelease=False)
        assert result is not None
        assert result.version == "1.1.0"
        assert result.tag_name == "v1.1.0"
        assert result.sha256 == "aabbccdd11223344aabbccdd11223344aabbccdd11223344aabbccdd11223344"
        assert result.asset_url.endswith("Kototsuna_Setup.exe")

    @patch("src.updater.requests.get")
    def test_no_new_version(self, mock_get):
        data = {**MOCK_RELEASE_DATA, "tag_name": "v1.0.0"}
        mock_response = MagicMock()
        mock_response.json.return_value = data
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = check_for_updates("1.0.0")
        assert result is None

    @patch("src.updater.requests.get")
    def test_no_exe_asset(self, mock_get):
        data = {**MOCK_RELEASE_DATA, "assets": [{"name": "other.zip", "browser_download_url": "x", "size": 100}]}
        mock_response = MagicMock()
        mock_response.json.return_value = data
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = check_for_updates("1.0.0")
        assert result is None

    @patch("src.updater.requests.get")
    def test_network_error_returns_none(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("Network error")

        result = check_for_updates("1.0.0")
        assert result is None

    @patch("src.updater.requests.get")
    def test_prerelease_list(self, mock_get):
        prerelease_data = {**MOCK_RELEASE_DATA, "tag_name": "v1.2.0-beta", "prerelease": True}
        mock_response = MagicMock()
        mock_response.json.return_value = [prerelease_data]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = check_for_updates("1.0.0", include_prerelease=True)
        assert result is not None
        assert result.prerelease is True

    @patch("src.updater.requests.get")
    def test_prerelease_selects_highest_version(self, mock_get):
        rc9 = {
            **MOCK_RELEASE_DATA,
            "tag_name": "v1.1.3-rc9",
            "prerelease": True,
            "assets": [{
                "name": "Kototsuna_Setup.exe",
                "browser_download_url": "https://example.com/v1.1.3-rc9/Kototsuna_Setup.exe",
                "size": 100,
            }],
        }
        rc11 = {
            **MOCK_RELEASE_DATA,
            "tag_name": "v1.1.3-rc11",
            "prerelease": True,
            "assets": [{
                "name": "Kototsuna_Setup.exe",
                "browser_download_url": "https://example.com/v1.1.3-rc11/Kototsuna_Setup.exe",
                "size": 100,
            }],
        }

        mock_response = MagicMock()
        # intentionally unsorted order
        mock_response.json.return_value = [rc9, rc11]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = check_for_updates("v1.1.2", include_prerelease=True)
        assert result is not None
        assert result.tag_name == "v1.1.3-rc11"


# =========================================
# download_update (mocked)
# =========================================

class TestDownloadUpdate:
    @patch("src.updater.requests.get")
    def test_download_success_no_sha(self, mock_get):
        content = b"fake exe content"
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_content.return_value = [content]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        release = ReleaseInfo(
            version="1.1.0", tag_name="v1.1.0", name="Release",
            body="", published_at="", prerelease=False,
            asset_url="https://example.com/Kototsuna_Setup.exe",
            asset_size=len(content), sha256="",
        )

        import os
        path = download_update(release)
        try:
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == content
        finally:
            os.unlink(path)

    @patch("src.updater.requests.get")
    def test_download_sha256_mismatch(self, mock_get):
        content = b"fake exe content"
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_content.return_value = [content]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        release = ReleaseInfo(
            version="1.1.0", tag_name="v1.1.0", name="Release",
            body="", published_at="", prerelease=False,
            asset_url="https://example.com/Kototsuna_Setup.exe",
            asset_size=len(content),
            sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )

        with pytest.raises(UpdateError, match="SHA256 mismatch"):
            download_update(release)

    @patch("src.updater.requests.get")
    def test_progress_callback(self, mock_get):
        content = b"x" * 1024
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_content.return_value = [content]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        release = ReleaseInfo(
            version="1.1.0", tag_name="v1.1.0", name="Release",
            body="", published_at="", prerelease=False,
            asset_url="https://example.com/Kototsuna_Setup.exe",
            asset_size=len(content), sha256="",
        )

        callback = MagicMock()
        import os
        path = download_update(release, progress_callback=callback)
        try:
            callback.assert_called()
            args = callback.call_args[0]
            assert args[0] == 1024  # downloaded
            assert args[1] == 1024  # total
        finally:
            os.unlink(path)


# =========================================
# format_file_size
# =========================================

class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(500) == "500 B"

    def test_kb(self):
        assert format_file_size(1536) == "1.5 KB"

    def test_mb(self):
        assert format_file_size(293_601_280) == "280.0 MB"

    def test_gb(self):
        assert format_file_size(1_073_741_824) == "1.0 GB"


# =========================================
# _find_installer_url_for_version (mocked)
# =========================================

class TestFindInstallerUrl:
    @patch("src.updater.requests.get")
    def test_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v1.0.0",
            "assets": [{
                "name": "Kototsuna_Setup.exe",
                "browser_download_url": "https://example.com/v1.0.0/Kototsuna_Setup.exe",
                "size": 100,
            }],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = _find_installer_url_for_version("v1.0.0")
        assert url == "https://example.com/v1.0.0/Kototsuna_Setup.exe"

    @patch("src.updater.requests.get")
    def test_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v1.0.0", "assets": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = _find_installer_url_for_version("v1.0.0")
        assert url == ""

    @patch("src.updater.requests.get")
    def test_network_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("Network error")

        url = _find_installer_url_for_version("v1.0.0")
        assert url == ""

    @patch("src.updater.requests.get")
    def test_adds_v_prefix(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v1.0.0", "assets": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        _find_installer_url_for_version("1.0.0")
        call_url = mock_get.call_args[0][0]
        assert call_url.endswith("/tags/v1.0.0")


# =========================================
# save / get / clear rollback info (mocked config)
# =========================================

class TestRollbackInfo:
    @patch("src.config.save_config")
    @patch("src.config.load_config")
    @patch("src.updater._find_installer_url_for_version")
    def test_save_rollback_info(self, mock_find, mock_load, mock_save):
        mock_load.return_value = {"previous_version": "", "just_updated": False, "previous_installer_url": ""}
        mock_find.return_value = "https://example.com/setup.exe"

        save_rollback_info("1.5.0-beta.4")

        saved = mock_save.call_args[0][0]
        assert saved["previous_version"] == "v1.5.0-beta.4"
        assert saved["just_updated"] is True
        assert saved["previous_installer_url"] == "https://example.com/setup.exe"

    @patch("src.config.load_config")
    def test_get_rollback_info_exists(self, mock_load):
        mock_load.return_value = {
            "previous_version": "v1.4.0",
            "previous_installer_url": "https://example.com/v1.4.0/setup.exe",
        }

        info = get_rollback_info()
        assert info is not None
        assert info["version"] == "v1.4.0"
        assert info["installer_url"] == "https://example.com/v1.4.0/setup.exe"

    @patch("src.config.load_config")
    def test_get_rollback_info_empty(self, mock_load):
        mock_load.return_value = {"previous_version": "", "previous_installer_url": ""}

        info = get_rollback_info()
        assert info is None

    @patch("src.config.save_config")
    @patch("src.config.load_config")
    def test_clear_rollback_info(self, mock_load, mock_save):
        mock_load.return_value = {"just_updated": True, "previous_version": "v1.4.0"}

        clear_rollback_info()

        saved = mock_save.call_args[0][0]
        assert saved["just_updated"] is False

    @patch("src.updater.restart_app")
    @patch("src.updater.apply_update")
    @patch("src.updater.download_update")
    @patch("src.config.save_config")
    @patch("src.config.load_config")
    @patch("src.updater.get_rollback_info")
    def test_rollback_to_previous_success(
        self, mock_info, mock_load, mock_save, mock_download, mock_apply, mock_restart
    ):
        mock_info.return_value = {
            "version": "v1.4.0",
            "installer_url": "https://example.com/v1.4.0/setup.exe",
        }
        mock_load.return_value = {
            "previous_version": "v1.4.0",
            "just_updated": True,
            "previous_installer_url": "https://example.com/v1.4.0/setup.exe",
        }
        mock_download.return_value = "/tmp/fake_installer.exe"

        rollback_to_previous()

        mock_download.assert_called_once()
        release_arg = mock_download.call_args[0][0]
        assert release_arg.tag_name == "v1.4.0"
        assert release_arg.asset_url == "https://example.com/v1.4.0/setup.exe"
        mock_apply.assert_called_once_with("/tmp/fake_installer.exe")
        mock_restart.assert_called_once()

    @patch("src.updater.get_rollback_info")
    def test_rollback_no_info_raises(self, mock_info):
        mock_info.return_value = None

        with pytest.raises(UpdateError, match="ロールバック情報がありません"):
            rollback_to_previous()

    @patch("src.updater._find_installer_url_for_version")
    @patch("src.updater.get_rollback_info")
    def test_rollback_no_url_raises(self, mock_info, mock_find):
        mock_info.return_value = {"version": "v1.4.0", "installer_url": ""}
        mock_find.return_value = ""

        with pytest.raises(UpdateError, match="インストーラーが見つかりません"):
            rollback_to_previous()
