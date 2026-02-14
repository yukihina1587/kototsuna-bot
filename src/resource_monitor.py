# -*- coding: utf-8 -*-
"""
リソース監視モジュール
メモリ使用量、CPU使用率、スレッド数などを監視する
"""

import threading
import time
from typing import Dict, Optional, Callable
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
    PSUTIL_IMPORT_ERROR = None
except ImportError as e:
    psutil = None
    PSUTIL_AVAILABLE = False
    PSUTIL_IMPORT_ERROR = str(e)
except Exception as e:
    psutil = None
    PSUTIL_AVAILABLE = False
    PSUTIL_IMPORT_ERROR = f"Unexpected error: {str(e)}"

from src.logger import logger


class ResourceMonitor:
    """リソース監視クラス"""

    # デフォルトの警告閾値
    DEFAULT_MEMORY_WARNING_THRESHOLD_MB = 500  # 500MB
    DEFAULT_CPU_WARNING_THRESHOLD_PERCENT = 80  # 80%

    def __init__(
        self,
        memory_warning_threshold_mb: Optional[float] = None,
        cpu_warning_threshold_percent: Optional[float] = None,
        warning_callback: Optional[Callable[[str, Dict], None]] = None
    ):
        """
        リソース監視を初期化

        Args:
            memory_warning_threshold_mb: メモリ警告閾値（MB）
            cpu_warning_threshold_percent: CPU警告閾値（%）
            warning_callback: 警告発生時のコールバック関数
        """
        if not PSUTIL_AVAILABLE:
            error_msg = PSUTIL_IMPORT_ERROR or "不明なエラー"
            logger.warning(f"psutilが利用できません。リソース監視機能は制限されます。(Error: {error_msg})")

        self.memory_warning_threshold_mb = (
            memory_warning_threshold_mb or self.DEFAULT_MEMORY_WARNING_THRESHOLD_MB
        )
        self.cpu_warning_threshold_percent = (
            cpu_warning_threshold_percent or self.DEFAULT_CPU_WARNING_THRESHOLD_PERCENT
        )
        self.warning_callback = warning_callback

        # 自動再起動設定
        self.auto_restart_enabled = False
        self.auto_restart_threshold_mb = 1000  # デフォルト1000MB

        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._cpu_collector_thread: Optional[threading.Thread] = None
        self._last_warning_time: Dict[str, float] = {}
        self._warning_cooldown = 60  # 同じ警告を60秒間隔で抑制

        # 非ブロッキングCPU統計キャッシュ
        self._cached_cpu_percent: float = 0.0
        self._cached_system_cpu_percent: float = 0.0
        self._cpu_lock = threading.Lock()
        self._cpu_collecting = False

        # プロセス情報
        try:
            self._process = psutil.Process() if PSUTIL_AVAILABLE else None
        except Exception as e:
            logger.error(f"プロセス情報の取得に失敗: {e}")
            self._process = None

        # CPU統計のバックグラウンド収集を開始
        if PSUTIL_AVAILABLE and self._process:
            self._start_cpu_collector()
    
    def _start_cpu_collector(self) -> None:
        """CPU統計をバックグラウンドで収集するスレッドを開始"""
        self._cpu_collecting = True
        self._cpu_collector_thread = threading.Thread(
            target=self._cpu_collect_loop,
            daemon=True,
            name="CPUCollector",
        )
        self._cpu_collector_thread.start()

    def _cpu_collect_loop(self) -> None:
        """CPU統計を定期収集するループ（バックグラウンドスレッド、約2秒間隔）"""
        # 初回プライミング（以降のinterval=None呼び出し用）
        if PSUTIL_AVAILABLE:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass
        while self._cpu_collecting:
            try:
                if self._process and PSUTIL_AVAILABLE:
                    # cpu_percent(interval=2.0)で2秒間のCPU使用率を計測
                    proc_cpu = self._process.cpu_percent(interval=2.0)
                    sys_cpu = psutil.cpu_percent(interval=None)
                    with self._cpu_lock:
                        self._cached_cpu_percent = proc_cpu
                        self._cached_system_cpu_percent = sys_cpu
            except Exception:
                time.sleep(2.0)

    def _stop_cpu_collector(self) -> None:
        """CPU統計収集スレッドを停止"""
        self._cpu_collecting = False
        if self._cpu_collector_thread and self._cpu_collector_thread.is_alive():
            self._cpu_collector_thread.join(timeout=2.0)

    def get_resource_stats(self) -> Dict:
        """
        現在のリソース統計を取得（非ブロッキング）

        Returns:
            リソース統計の辞書
        """
        if not PSUTIL_AVAILABLE:
            return {
                "available": False,
                "error": f"psutilが利用できません (Import Error: {PSUTIL_IMPORT_ERROR})"
            }

        if self._process is None:
            return {
                "available": False,
                "error": "psutilプロセス情報の初期化に失敗しました"
            }

        try:
            # メモリ情報（非ブロッキング）
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)

            # CPU使用率はキャッシュから取得（非ブロッキング）
            with self._cpu_lock:
                cpu_percent = self._cached_cpu_percent
                system_cpu_percent = self._cached_system_cpu_percent

            # スレッド数
            thread_count = threading.active_count()

            # システムメモリ情報（非ブロッキング）
            system_memory = psutil.virtual_memory()

            stats = {
                "available": True,
                "timestamp": datetime.now().isoformat(),
                "process": {
                    "memory_mb": round(memory_mb, 2),
                    "memory_percent": round(self._process.memory_percent(), 2),
                    "cpu_percent": round(cpu_percent, 2),
                    "thread_count": thread_count,
                    "num_fds": getattr(self._process, "num_fds", None),
                },
                "system": {
                    "cpu_percent": round(system_cpu_percent, 2),
                    "memory_total_mb": round(system_memory.total / (1024 * 1024), 2),
                    "memory_available_mb": round(system_memory.available / (1024 * 1024), 2),
                    "memory_used_percent": round(system_memory.percent, 2),
                },
                "warnings": {
                    "memory_warning": memory_mb > self.memory_warning_threshold_mb,
                    "cpu_warning": cpu_percent > self.cpu_warning_threshold_percent,
                }
            }

            # 警告チェック
            self._check_warnings(stats)

            return stats

        except Exception as e:
            logger.error(f"リソース統計の取得に失敗: {e}")
            return {
                "available": False,
                "error": str(e)
            }
    
    def _check_warnings(self, stats: Dict) -> None:
        """警告をチェックして、必要に応じてコールバックを呼び出す"""
        if not stats.get("available", False):
            return

        current_time = time.time()
        warnings = stats.get("warnings", {})
        process_stats = stats.get("process", {})

        # メモリ警告
        if warnings.get("memory_warning", False):
            memory_mb = process_stats.get("memory_mb", 0)
            warning_key = "memory"
            if self._should_trigger_warning(warning_key, current_time):
                message = (
                    f"メモリ使用量が警告閾値を超えています: "
                    f"{memory_mb:.2f}MB (閾値: {self.memory_warning_threshold_mb}MB)"
                )
                self._trigger_warning("memory", message, stats)

        # CPU警告
        if warnings.get("cpu_warning", False):
            cpu_percent = process_stats.get("cpu_percent", 0)
            warning_key = "cpu"
            if self._should_trigger_warning(warning_key, current_time):
                message = (
                    f"CPU使用率が警告閾値を超えています: "
                    f"{cpu_percent:.2f}% (閾値: {self.cpu_warning_threshold_percent}%)"
                )
                self._trigger_warning("cpu", message, stats)

        # 自動再起動チェック
        if self.auto_restart_enabled:
            memory_mb = process_stats.get("memory_mb", 0)
            if memory_mb > self.auto_restart_threshold_mb:
                warning_key = "auto_restart"
                if self._should_trigger_warning(warning_key, current_time):
                    message = (
                        f"メモリ使用量が自動再起動閾値を超えました: "
                        f"{memory_mb:.2f}MB (閾値: {self.auto_restart_threshold_mb}MB)"
                    )
                    self._trigger_warning("auto_restart", message, stats)
    
    def _should_trigger_warning(self, warning_key: str, current_time: float) -> bool:
        """警告を発火すべきかチェック（クールダウン期間を考慮）"""
        last_time = self._last_warning_time.get(warning_key, 0)
        return (current_time - last_time) >= self._warning_cooldown
    
    def _trigger_warning(self, warning_type: str, message: str, stats: Dict) -> None:
        """警告を発火"""
        current_time = time.time()
        self._last_warning_time[warning_type] = current_time
        
        logger.warning(f"[リソース監視] {message}")
        
        if self.warning_callback:
            try:
                self.warning_callback(warning_type, {
                    "message": message,
                    "stats": stats,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"警告コールバックの実行に失敗: {e}")
    
    def start_monitoring(self, interval: float = 5.0) -> None:
        """
        バックグラウンドでの監視を開始
        
        Args:
            interval: 監視間隔（秒）
        """
        if not PSUTIL_AVAILABLE:
            logger.warning("psutilが利用できないため、監視を開始できません。")
            return
        
        if self._monitoring:
            logger.warning("監視は既に開始されています。")
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True,
            name="ResourceMonitor"
        )
        self._monitor_thread.start()
        logger.info(f"リソース監視を開始しました（間隔: {interval}秒）")
    
    def stop_monitoring(self) -> None:
        """バックグラウンドでの監視を停止"""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self._stop_cpu_collector()
        logger.info("リソース監視を停止しました")
    
    def _monitor_loop(self, interval: float) -> None:
        """監視ループ（バックグラウンドスレッドで実行）"""
        while self._monitoring:
            try:
                stats = self.get_resource_stats()
                # ログには定期的に記録（デバッグモード時のみ詳細ログ）
                if stats.get("available", False):
                    process_stats = stats.get("process", {})
                    memory_mb = process_stats.get("memory_mb", 0)
                    cpu_percent = process_stats.get("cpu_percent", 0)
                    logger.debug(
                        f"リソース監視: メモリ={memory_mb:.2f}MB, "
                        f"CPU={cpu_percent:.2f}%, "
                        f"スレッド={process_stats.get('thread_count', 0)}"
                    )
            except Exception as e:
                logger.error(f"監視ループでエラーが発生: {e}")
            
            time.sleep(interval)
    
    def get_detailed_debug_info(self) -> Dict:
        """
        デバッグモード用の詳細情報を取得
        
        Returns:
            詳細なデバッグ情報の辞書
        """
        if not PSUTIL_AVAILABLE or self._process is None:
            return {
                "available": False,
                "error": "psutilが利用できません"
            }
        
        try:
            stats = self.get_resource_stats()
            
            # 追加のデバッグ情報
            debug_info = {
                **stats,
                "debug": {
                    "process_name": self._process.name(),
                    "process_id": self._process.pid,
                    "process_status": self._process.status(),
                    "process_create_time": datetime.fromtimestamp(
                        self._process.create_time()
                    ).isoformat(),
                    "open_files": len(self._process.open_files()) if hasattr(self._process, "open_files") else None,
                    "connections": len(self._process.connections()) if hasattr(self._process, "connections") else None,
                },
                "threads": {
                    "active_count": threading.active_count(),
                    "main_thread": threading.main_thread().name,
                },
                "monitoring": {
                    "active": self._monitoring,
                    "memory_threshold_mb": self.memory_warning_threshold_mb,
                    "cpu_threshold_percent": self.cpu_warning_threshold_percent,
                }
            }
            
            return debug_info
            
        except Exception as e:
            logger.error(f"デバッグ情報の取得に失敗: {e}")
            return {
                "available": False,
                "error": str(e)
            }


# シングルトンインスタンス
_monitor_instance: Optional[ResourceMonitor] = None


def get_monitor() -> ResourceMonitor:
    """リソース監視のシングルトンインスタンスを取得"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = ResourceMonitor()
    return _monitor_instance
