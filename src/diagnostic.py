"""
DiagnosticCollector - 診断バンドル（ZIP）の収集・出力。

収集内容:
- diagnostic_info.txt : OS・Pythonバージョン・アプリバージョン・セッションID・収集理由
- masked_config.json  : 機密キーをマスクした設定ファイル
- bot_*.log           : 直近3日分のテキストログ
- bot_*.jsonl         : 直近3日分のJSONLログ
- kototsuna_error.txt : クラッシュログ（存在する場合）
"""

import json
import os
import platform
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---- 定数 ----------------------------------------------------------------

MASKED_KEYS: frozenset[str] = frozenset({
    "twitch_access_token",
    "obs_password",
    "gladia_api_key",
    "youtube_client_secret",
    "youtube_access_token",
    "youtube_refresh_token",
    "google_translate_api_key",
    "libre_translate_api_key",
})

_LOG_DAYS = 3  # 収集するログの日数


# ---- ヘルパー -----------------------------------------------------------

def _get_exe_dir() -> Path:
    """exeフォルダ（開発時はプロジェクトルート）を返す。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _get_log_dir() -> Path:
    return _get_exe_dir() / "logs"


def _get_output_dir() -> Path:
    """診断ZIPの出力先ディレクトリを返す。"""
    if getattr(sys, 'frozen', False):
        # exe版: %LOCALAPPDATA%\Kototsuna\diagnostics
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            out = Path(local_app_data) / "Kototsuna" / "diagnostics"
            out.mkdir(parents=True, exist_ok=True)
            return out
    # 開発版またはフォールバック: プロジェクトルート/dist/diagnostics
    out = _get_exe_dir() / "dist" / "diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _mask_config(config: dict) -> dict:
    """設定dictの機密キーをマスクしたコピーを返す。"""
    masked: dict = {}
    for key, value in config.items():
        if key in MASKED_KEYS and isinstance(value, str) and value:
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _build_diagnostic_info(reason: str, session_id: str) -> str:
    """diagnostic_info.txt の内容を生成する。"""
    try:
        from src import __version__
        app_version = __version__
    except Exception:
        app_version = "unknown"

    lines = [
        f"=== Kototsuna Diagnostic Bundle ===",
        f"Collected  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Reason     : {reason}",
        f"Session    : {session_id}",
        f"App version: {app_version}",
        "",
        f"OS         : {platform.platform()}",
        f"Python     : {sys.version}",
        f"Executable : {sys.executable}",
        f"Frozen     : {getattr(sys, 'frozen', False)}",
    ]
    return "\n".join(lines) + "\n"


# ---- メインクラス -------------------------------------------------------

class DiagnosticCollector:
    """診断バンドルを収集してZIPファイルとして出力するクラス。"""

    def collect(self, reason: str = "manual") -> Optional[Path]:
        """
        診断バンドルZIPを作成して保存パスを返す。

        Args:
            reason: 収集理由（"manual", "crash_recovery", "user_request" 等）

        Returns:
            作成したZIPファイルのパス。失敗した場合は None。
        """
        try:
            return self._collect_internal(reason)
        except Exception as e:
            # 診断収集自体が失敗しても本体の動作に影響させない
            try:
                from src.logger import logger
                logger.error(f"DiagnosticCollector.collect failed: {e}", exc_info=True)
            except Exception:
                pass
            return None

    def _collect_internal(self, reason: str) -> Path:
        from src.logger import SESSION_ID

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        zip_path = _get_output_dir() / f"kototsuna_diag_{timestamp}.zip"

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # diagnostic_info.txt
            zf.writestr(
                "diagnostic_info.txt",
                _build_diagnostic_info(reason, SESSION_ID),
            )

            # masked_config.json
            self._add_masked_config(zf)

            # ログファイル（直近 _LOG_DAYS 日分）
            self._add_log_files(zf)

            # kototsuna_error.txt（存在する場合）
            self._add_error_file(zf)

        return zip_path

    def _add_masked_config(self, zf: zipfile.ZipFile) -> None:
        """設定ファイルをマスクしてZIPに追加する。"""
        try:
            from src.config import load_config
            config = load_config()
            masked = _mask_config(config)
            zf.writestr(
                "masked_config.json",
                json.dumps(masked, ensure_ascii=False, indent=2),
            )
        except Exception as e:
            zf.writestr("masked_config.json", f"{{\"error\": \"{e}\"}}")

    def _add_log_files(self, zf: zipfile.ZipFile) -> None:
        """直近 _LOG_DAYS 日分のログファイルをZIPに追加する。"""
        log_dir = _get_log_dir()
        if not log_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=_LOG_DAYS)
        for pattern in ("bot_*.log", "bot_*.jsonl"):
            for log_file in sorted(log_dir.glob(pattern)):
                try:
                    # ファイル名から日付を抽出して古すぎるファイルを除外
                    # 形式: bot_YYYY-MM-DD.log / bot_YYYY-MM-DD.jsonl
                    stem = log_file.stem  # bot_YYYY-MM-DD
                    date_str = stem[4:]   # YYYY-MM-DD
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff:
                        continue
                except (ValueError, IndexError):
                    pass  # 日付解析失敗時は含める

                try:
                    zf.write(log_file, arcname=f"logs/{log_file.name}")
                except OSError:
                    pass

    def _add_error_file(self, zf: zipfile.ZipFile) -> None:
        """kototsuna_error.txt が存在する場合にZIPへ追加する。

        _kototsuna_excepthook は exeフォルダが書き込み不可の場合に
        %TEMP%\kototsuna_error.txt へフォールバックするため、
        TEMP も候補に含める。
        """
        exe_dir = _get_exe_dir()
        for candidate in [
            exe_dir / "kototsuna_error.txt",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Kototsuna" / "kototsuna_error.txt",
            Path(os.environ.get("TEMP", "")) / "kototsuna_error.txt",
        ]:
            if candidate.exists():
                try:
                    zf.write(candidate, arcname="kototsuna_error.txt")
                except OSError:
                    pass
                break
