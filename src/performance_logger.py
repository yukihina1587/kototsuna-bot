# -*- coding: utf-8 -*-
"""
パフォーマンス計測モジュール
処理時間の計測・統計表示を提供する
"""
import time
import statistics
from collections import deque
from contextlib import contextmanager
from typing import Dict, Optional
from src.logger import logger


class PerformanceMetrics:
    """パフォーマンス統計を収集・管理するクラス"""

    def __init__(self, max_samples: int = 1000):
        """
        Args:
            max_samples: 保持するサンプル数の上限
        """
        self._metrics: Dict[str, deque] = {}
        self._max_samples = max_samples

    @contextmanager
    def measure(self, name: str):
        """
        処理時間を計測するコンテキストマネージャー

        Args:
            name: 計測名（例: "translation", "gui_refresh"）

        Usage:
            with perf.measure("translation"):
                result = await translate(text)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._record(name, elapsed_ms)

    def record(self, name: str, elapsed_ms: float) -> None:
        """手動で計測値を記録する"""
        self._record(name, elapsed_ms)

    def _record(self, name: str, elapsed_ms: float) -> None:
        if name not in self._metrics:
            self._metrics[name] = deque(maxlen=self._max_samples)
        self._metrics[name].append(elapsed_ms)

    def get_stats(self, name: str) -> Optional[Dict[str, float]]:
        """
        指定した計測名の統計を取得

        Returns:
            {count, min, max, avg, p95, p99} またはサンプル不足時None
        """
        samples = self._metrics.get(name)
        if not samples:
            return None

        sorted_samples = sorted(samples)
        count = len(sorted_samples)

        result = {
            "count": count,
            "min": round(sorted_samples[0], 2),
            "max": round(sorted_samples[-1], 2),
            "avg": round(statistics.mean(sorted_samples), 2),
        }

        if count >= 20:
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)
            result["p95"] = round(sorted_samples[min(p95_idx, count - 1)], 2)
            result["p99"] = round(sorted_samples[min(p99_idx, count - 1)], 2)

        return result

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """全計測名の統計を取得"""
        result = {}
        for name in self._metrics:
            stats = self.get_stats(name)
            if stats:
                result[name] = stats
        return result

    def format_stats(self, name: str) -> str:
        """統計を見やすい文字列でフォーマット"""
        stats = self.get_stats(name)
        if not stats:
            return f"{name}: データなし"

        parts = [
            f"{name}:",
            f"  回数={stats['count']}",
            f"  平均={stats['avg']:.1f}ms",
            f"  最小={stats['min']:.1f}ms",
            f"  最大={stats['max']:.1f}ms",
        ]
        if "p95" in stats:
            parts.append(f"  P95={stats['p95']:.1f}ms")
            parts.append(f"  P99={stats['p99']:.1f}ms")
        return " ".join(parts)

    def clear(self, name: Optional[str] = None) -> None:
        """統計をクリア"""
        if name:
            self._metrics.pop(name, None)
        else:
            self._metrics.clear()


# グローバルインスタンス
_perf_instance: Optional[PerformanceMetrics] = None


def get_perf() -> PerformanceMetrics:
    """パフォーマンス計測のシングルトンインスタンスを取得"""
    global _perf_instance
    if _perf_instance is None:
        _perf_instance = PerformanceMetrics()
    return _perf_instance
