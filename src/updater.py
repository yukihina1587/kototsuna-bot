# -*- coding: utf-8 -*-
"""自動アップデートエンジン

GitHub Releasesからの更新チェック、ダウンロード、
SHA256検証、exe差し替え、再起動を担当する。
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import requests
from packaging.version import InvalidVersion, Version

from src.logger import logger

# GitHub API設定
GITHUB_API_URL = "https://api.github.com/repos/yukihina1587/kototsuna-bot/releases"
EXE_ASSET_NAME = "Kototsuna.exe"

# タイムアウト設定
REQUEST_TIMEOUT = 30
DOWNLOAD_CHUNK_SIZE = 8192


class UpdateError(Exception):
    """アップデート処理中のエラー"""


@dataclass(frozen=True)
class ReleaseInfo:
    """GitHubリリース情報"""
    version: str
    tag_name: str
    name: str
    body: str
    published_at: str
    prerelease: bool
    asset_url: str
    asset_size: int
    sha256: str


def parse_version(version_str: str) -> tuple[int, int, int]:
    """セマンティックバージョン文字列をタプルにパースする。

    Args:
        version_str: "v1.2.3" or "1.2.3" 形式の文字列

    Returns:
        (major, minor, patch) のタプル

    Raises:
        ValueError: パース不能な文字列の場合
    """
    cleaned = version_str.lstrip("vV").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _to_packaging_version(version_str: str) -> Optional[Version]:
    """Git tag文字列を packaging.version.Version へ変換する。"""
    cleaned = version_str.lstrip("vV").strip().lower()
    cleaned = cleaned.replace("-alpha.", "a").replace("-alpha", "a")
    cleaned = cleaned.replace("-beta.", "b").replace("-beta", "b")
    cleaned = cleaned.replace("-rc.", "rc").replace("-rc", "rc")
    try:
        return Version(cleaned)
    except InvalidVersion:
        return None


def is_newer(current: str, latest: str) -> bool:
    """latest が current より新しいか判定する。

    Args:
        current: 現在のバージョン文字列
        latest: 比較対象のバージョン文字列

    Returns:
        latest > current なら True
    """
    current_v = _to_packaging_version(current)
    latest_v = _to_packaging_version(latest)
    if current_v is not None and latest_v is not None:
        return latest_v > current_v
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


def _extract_sha256(body: str) -> str:
    """リリースノート本文からSHA256ハッシュを抽出する。

    パターン: SHA256: `abc123...` or SHA256: abc123...

    Args:
        body: リリースノートの本文

    Returns:
        SHA256ハッシュ文字列。見つからなければ空文字列
    """
    if not body:
        return ""
    match = re.search(r"SHA256[:\s]+`?([a-fA-F0-9]{64})`?", body)
    return match.group(1).lower() if match else ""


def check_for_updates(
    current_version: str,
    include_prerelease: bool = False,
) -> Optional[ReleaseInfo]:
    """GitHub Releases APIで新バージョンを確認する。

    Args:
        current_version: 現在のアプリバージョン
        include_prerelease: プレリリースも含めるか

    Returns:
        新バージョンがあれば ReleaseInfo、なければ None
    """
    try:
        if include_prerelease:
            url = GITHUB_API_URL
        else:
            url = f"{GITHUB_API_URL}/latest"

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        response.raise_for_status()

        if include_prerelease:
            releases = response.json()
            if not releases:
                return None

            current_v = _to_packaging_version(current_version)
            best_release = None
            best_version = None
            best_asset_url = ""
            best_asset_size = 0

            for release in releases:
                tag_name = release.get("tag_name", "")
                rel_v = _to_packaging_version(tag_name)
                if rel_v is None:
                    continue
                if current_v is not None and rel_v <= current_v:
                    continue

                asset_url = ""
                asset_size = 0
                for asset in release.get("assets", []):
                    if asset.get("name") == EXE_ASSET_NAME:
                        asset_url = asset.get("browser_download_url", "")
                        asset_size = asset.get("size", 0)
                        break
                if not asset_url:
                    continue

                if best_version is None or rel_v > best_version:
                    best_release = release
                    best_version = rel_v
                    best_asset_url = asset_url
                    best_asset_size = asset_size

            if best_release is None:
                return None
            release_data = best_release
            asset_url = best_asset_url
            asset_size = best_asset_size
        else:
            release_data = response.json()
            asset_url = ""
            asset_size = 0
            for asset in release_data.get("assets", []):
                if asset.get("name") == EXE_ASSET_NAME:
                    asset_url = asset.get("browser_download_url", "")
                    asset_size = asset.get("size", 0)
                    break

        if not asset_url:
            logger.debug(f"Release {release_data.get('tag_name')} has no {EXE_ASSET_NAME} asset")
            return None

        tag_name = release_data.get("tag_name", "")
        body = release_data.get("body", "")
        sha256 = _extract_sha256(body)

        # バージョン比較
        if not is_newer(current_version, tag_name):
            logger.debug(f"Current version {current_version} is up to date (latest: {tag_name})")
            return None

        return ReleaseInfo(
            version=tag_name.lstrip("vV"),
            tag_name=tag_name,
            name=release_data.get("name", tag_name),
            body=body,
            published_at=release_data.get("published_at", ""),
            prerelease=release_data.get("prerelease", False),
            asset_url=asset_url,
            asset_size=asset_size,
            sha256=sha256,
        )

    except requests.RequestException as e:
        logger.warning(f"Update check failed: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Failed to parse release data: {e}")
        return None


def download_update(
    release: ReleaseInfo,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """リリースのexeをダウンロードし、SHA256を検証する。

    Args:
        release: ダウンロード対象のリリース情報
        progress_callback: (downloaded_bytes, total_bytes) を受け取るコールバック

    Returns:
        ダウンロードした一時ファイルのパス

    Raises:
        UpdateError: ダウンロードまたは検証失敗時
    """
    temp_path = ""
    try:
        logger.info(f"Downloading update: {release.tag_name} from {release.asset_url}")

        response = requests.get(
            release.asset_url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0)) or release.asset_size
        sha256_hash = hashlib.sha256()

        # 一時ファイルにダウンロード
        fd, temp_path = tempfile.mkstemp(suffix=".tmp", prefix="kototsuna_update_")
        downloaded = 0

        with os.fdopen(fd, "wb") as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

        logger.info(f"Download complete: {downloaded} bytes")

        # SHA256検証
        if release.sha256:
            computed_hash = sha256_hash.hexdigest().lower()
            expected_hash = release.sha256.lower()
            if computed_hash != expected_hash:
                os.unlink(temp_path)
                raise UpdateError(
                    f"SHA256 mismatch: expected {expected_hash}, got {computed_hash}"
                )
            logger.info("SHA256 verification passed")
        else:
            logger.warning("No SHA256 hash in release notes, skipping verification")

        return temp_path

    except requests.RequestException as e:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise UpdateError(f"Download failed: {e}") from e
    except OSError as e:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise UpdateError(f"File operation failed: {e}") from e


def apply_update(downloaded_path: str) -> None:
    """ダウンロードしたexeで現在のexeを差し替える。

    手順:
    1. 現在のexe → .old にリネーム
    2. ダウンロードファイル → 現在のexeの位置にコピー
    3. 失敗時は .old から復元

    Args:
        downloaded_path: ダウンロードした一時ファイルのパス

    Raises:
        UpdateError: 差し替え失敗時
    """
    current_exe = _get_current_exe_path()
    if not current_exe:
        raise UpdateError("Cannot determine current executable path")

    old_path = current_exe + ".old"

    try:
        # 既存の.oldファイルを削除
        if os.path.exists(old_path):
            os.unlink(old_path)

        # 現在のexeをリネーム
        logger.info(f"Renaming current exe: {current_exe} -> {old_path}")
        os.rename(current_exe, old_path)

        # ダウンロードファイルを配置
        logger.info(f"Moving downloaded file: {downloaded_path} -> {current_exe}")
        import shutil
        shutil.move(downloaded_path, current_exe)

        logger.info("Update applied successfully")

    except OSError as e:
        # ロールバック: .oldを元に戻す
        logger.error(f"Update failed, attempting rollback: {e}")
        try:
            if os.path.exists(old_path) and not os.path.exists(current_exe):
                os.rename(old_path, current_exe)
                logger.info("Rollback successful")
        except OSError as rollback_error:
            logger.critical(f"Rollback failed: {rollback_error}")
        raise UpdateError(f"Failed to apply update: {e}") from e


def restart_app() -> None:
    """アプリを再起動する（--cleanup引数付き）。"""
    current_exe = _get_current_exe_path()
    if not current_exe:
        logger.error("Cannot determine executable path for restart")
        return

    logger.info(f"Restarting application: {current_exe} --cleanup")
    try:
        subprocess.Popen([current_exe, "--cleanup"])
        sys.exit(0)
    except OSError as e:
        logger.error(f"Failed to restart: {e}")


def cleanup_old_exe() -> None:
    """前回のアップデートで残った.old/.tmpファイルを削除する。"""
    current_exe = _get_current_exe_path()
    if not current_exe:
        return

    exe_dir = os.path.dirname(current_exe)
    cleaned = 0

    for filename in os.listdir(exe_dir):
        filepath = os.path.join(exe_dir, filename)
        if filepath.endswith(".old") or (
            filename.startswith("kototsuna_update_") and filename.endswith(".tmp")
        ):
            try:
                os.unlink(filepath)
                logger.info(f"Cleaned up old file: {filepath}")
                cleaned += 1
            except OSError as e:
                logger.warning(f"Failed to clean up {filepath}: {e}")

    if cleaned:
        logger.info(f"Cleanup complete: {cleaned} file(s) removed")


def _get_current_exe_path() -> Optional[str]:
    """現在の実行ファイルパスを取得する。

    PyInstallerビルド時は sys.executable がexeパス。
    開発環境では None を返す。
    """
    if getattr(sys, "frozen", False):
        return sys.executable
    return None


def format_file_size(size_bytes: int) -> str:
    """バイト数を人間が読みやすい形式に変換する。

    Args:
        size_bytes: バイト数

    Returns:
        "280.5 MB" 形式の文字列
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
