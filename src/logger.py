"""
Logging configuration for KototsunaBot
Provides centralized logging setup with size-based rotating file handler
and a parallel JSON Lines handler for structured log analysis.
"""
import json
import logging
import re
import time
import sys
import uuid
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ログローテーション設定
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_LOG_BACKUP_COUNT = 7               # 最大7世代保持
_LOG_RETENTION_DAYS = 7             # 7日より古いログを削除

_LOGGER_NAME = "KototsunaBot"

# セッション識別子（起動ごとに一意）
SESSION_ID: str = uuid.uuid4().hex[:8]

# ログ内でマスクするシークレットパターン
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'oauth:[A-Za-z0-9_\-]{10,}', re.IGNORECASE), 'oauth:***'),
    (re.compile(r'Bearer [A-Za-z0-9_.~+/\-]+=*', re.IGNORECASE), 'Bearer ***'),
    (re.compile(r'"access_token"\s*:\s*"[^"]{4}[^"]*"'), '"access_token": "***"'),
    (re.compile(r'password=[^\s&"\']{3,}'), 'password=***'),
]


def _mask_secrets(text: str) -> str:
    """ログメッセージ内のシークレット情報をマスクする。"""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class _SessionFilter(logging.Filter):
    """全ログレコードにセッションIDを注入するフィルター。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = SESSION_ID  # type: ignore[attr-defined]
        return True


class _SecretMaskFilter(logging.Filter):
    """ログメッセージ内のシークレット情報をマスクするフィルター。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = _mask_secrets(msg)
        record.args = None  # 既にフォーマット済み
        return True


class _JsonLineFormatter(logging.Formatter):
    """JSON Lines形式のフォーマッター。"""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": datetime.fromtimestamp(record.created).strftime("%Y-%m-%dT%H:%M:%S.")
                  + f"{int(record.msecs):03d}",
            "level": record.levelname,
            "session": getattr(record, "session_id", SESSION_ID),
            "file": record.filename,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def _get_log_directory() -> Path:
    """
    Get the appropriate log directory based on execution context.

    Returns:
        Path to the log directory
    """
    if getattr(sys, 'frozen', False):
        # Running as exe (PyInstaller)
        base_dir = Path(sys.executable).parent
    else:
        # Running as script (development)
        base_dir = Path(__file__).parent.parent / "dist"

    return base_dir / "logs"


def _cleanup_old_logs(log_dir: Path, retention_days: int = _LOG_RETENTION_DAYS) -> None:
    """指定日数より古いログファイルを削除する。"""
    cutoff = time.time() - retention_days * 86400
    for pattern in ("bot_*.log*", "bot_*.jsonl*"):
        for log_file in log_dir.glob(pattern):
            try:
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
            except OSError:
                pass


def setup_logger(name: str = _LOGGER_NAME, level: str = "INFO") -> logging.Logger:
    """
    Setup and configure logger with size-based rotating file handler
    and a parallel JSON Lines handler.
    Console output is disabled - all logs go to file only.

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # Logger itself captures all levels

    # セッションフィルターとシークレットマスクフィルターをロガーに追加
    logger.addFilter(_SessionFilter())
    logger.addFilter(_SecretMaskFilter())

    # Create logs directory if it doesn't exist
    log_dir = _get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 古いログファイルをクリーンアップ
    _cleanup_old_logs(log_dir)

    today = datetime.now().strftime("%Y-%m-%d")

    # --- テキストハンドラー（サイズベースローテーション、10MB上限、7世代保持）---
    log_file = log_dir / f"bot_{today}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)-8s] [%(session_id)s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)

    # --- JSON Linesハンドラー（INFO以上、診断バンドル用）---
    jsonl_file = log_dir / f"bot_{today}.jsonl"
    jsonl_handler = RotatingFileHandler(
        jsonl_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    jsonl_handler.setLevel(logging.INFO)
    jsonl_handler.setFormatter(_JsonLineFormatter())
    jsonl_handler._jsonl_handler = True  # type: ignore[attr-defined]  # set_log_levelで除外するためのマーカー
    logger.addHandler(jsonl_handler)

    return logger


def set_log_level(level: str) -> None:
    """
    ログレベルを動的に変更する

    Args:
        level: ログレベル (DEBUG, INFO, WARNING, ERROR)
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = level_map.get(level.upper(), logging.INFO)

    root_logger = logging.getLogger(_LOGGER_NAME)
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers:
        # JSONLハンドラーは常にINFO以上を維持する
        if getattr(handler, '_jsonl_handler', False):
            continue
        handler.setLevel(log_level)

    root_logger.info(f"[Logger] Log level changed to: {level.upper()}")


def get_log_level() -> str:
    """
    現在のログレベルを取得する

    Returns:
        現在のログレベル文字列
    """
    level_names = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
    }
    root_logger = logging.getLogger(_LOGGER_NAME)
    return level_names.get(root_logger.level, "INFO")


# Create default logger instance
logger = setup_logger()
