"""
Logging configuration for KototsunaBot
Provides centralized logging setup with size-based rotating file handler.
"""
import logging
import time
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ログローテーション設定
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_LOG_BACKUP_COUNT = 7               # 最大7世代保持
_LOG_RETENTION_DAYS = 7             # 7日より古いログを削除

_LOGGER_NAME = "KototsunaBot"


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
    for log_file in log_dir.glob("bot_*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass


def setup_logger(name: str = _LOGGER_NAME, level: str = "INFO") -> logging.Logger:
    """
    Setup and configure logger with size-based rotating file handler.
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

    # Create logs directory if it doesn't exist
    log_dir = _get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 古いログファイルをクリーンアップ
    _cleanup_old_logs(log_dir)

    # サイズベースローテーション（10MB上限、7世代保持）
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"bot_{today}.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Add only file handler (no console output)
    logger.addHandler(file_handler)

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
