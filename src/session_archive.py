"""セッションアーカイブ — 配信ごとのコメントログをSQLiteに保存する。"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.logger import logger

# ---------------------------------------------------------------------------
# DB パス解決
# ---------------------------------------------------------------------------

def _get_archive_dir() -> Path:
    """アーカイブDBを格納するディレクトリを返す。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "Kototsuna" / "sessions"


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time  TEXT    NOT NULL,
    end_time    TEXT,
    channel     TEXT    NOT NULL,
    platform    TEXT    NOT NULL DEFAULT 'twitch'
);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    timestamp       TEXT    NOT NULL,
    username        TEXT    NOT NULL,
    display_name    TEXT,
    original_text   TEXT    NOT NULL,
    translated_text TEXT,
    source_lang     TEXT,
    bits            INTEGER DEFAULT 0,
    is_sub          INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_comments_session_id ON comments(session_id);
CREATE INDEX IF NOT EXISTS idx_comments_timestamp  ON comments(timestamp);
CREATE INDEX IF NOT EXISTS idx_comments_username   ON comments(username);
"""

# ---------------------------------------------------------------------------
# SessionArchive
# ---------------------------------------------------------------------------

FLUSH_INTERVAL_SEC = 5.0


class SessionArchive:
    """配信セッションのコメントをSQLiteに保存・検索するクラス。

    - WALモードでリアルタイム書き込みと読み取りを並行可能
    - バッチINSERT（キュー方式）で配信中のI/O負荷を最小化
    """

    def __init__(self) -> None:
        self._db_path: Path | None = None
        self._conn: sqlite3.Connection | None = None
        self._current_session_id: int | None = None

        # バッチINSERT用キューとタイマー
        self._queue: list[tuple] = []
        self._queue_lock = threading.Lock()
        self._flush_timer: threading.Timer | None = None
        self._stopped = False

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def open(self) -> None:
        """DBを開き、スキーマを初期化する。"""
        archive_dir = _get_archive_dir()
        archive_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = archive_dir / "archive.db"

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        self._stopped = False
        logger.info(f"SessionArchive opened: {self._db_path}")

    def close(self) -> None:
        """残りのキューをフラッシュしてDBを閉じる。"""
        self._stopped = True
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None
        self._flush_queue()
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.warning(f"SessionArchive close error: {e}")
            self._conn = None
        logger.info("SessionArchive closed")

    # ------------------------------------------------------------------
    # セッション管理
    # ------------------------------------------------------------------

    def start_session(self, channel: str, platform: str = "twitch") -> int:
        """新しいセッションを開始し、session_idを返す。"""
        if not self._conn:
            self.open()
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO sessions (start_time, channel, platform) VALUES (?, ?, ?)",
            (now, channel, platform),
        )
        self._conn.commit()
        self._current_session_id = cursor.lastrowid
        self._schedule_flush()
        logger.info(f"Archive session started: id={self._current_session_id}, channel={channel}")
        return self._current_session_id

    def end_session(self) -> None:
        """現在のセッションを終了する。"""
        if not self._conn or self._current_session_id is None:
            return
        self._flush_queue()
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE sessions SET end_time = ? WHERE id = ?",
            (now, self._current_session_id),
        )
        self._conn.commit()
        logger.info(f"Archive session ended: id={self._current_session_id}")
        self._current_session_id = None

    # ------------------------------------------------------------------
    # コメント書き込み（バッチ）
    # ------------------------------------------------------------------

    def add_comment(
        self,
        username: str,
        display_name: str | None,
        original_text: str,
        translated_text: str | None = None,
        source_lang: str | None = None,
        bits: int = 0,
        is_sub: bool = False,
    ) -> None:
        """コメントをキューに追加する。定期的にバッチINSERTでDBに書き込まれる。"""
        if self._current_session_id is None:
            return
        now = datetime.now().isoformat()
        row = (
            self._current_session_id,
            now,
            username,
            display_name,
            original_text,
            translated_text,
            source_lang,
            bits,
            1 if is_sub else 0,
        )
        with self._queue_lock:
            self._queue.append(row)

    def _flush_queue(self) -> None:
        """キュー内のコメントをDBに一括INSERT。"""
        with self._queue_lock:
            batch = self._queue[:]
            self._queue.clear()
        if not batch or not self._conn:
            return
        try:
            self._conn.executemany(
                "INSERT INTO comments "
                "(session_id, timestamp, username, display_name, "
                "original_text, translated_text, source_lang, bits, is_sub) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            self._conn.commit()
            logger.debug(f"Archive flushed {len(batch)} comments")
        except Exception as e:
            logger.error(f"Archive flush error: {e}", exc_info=True)

    def _schedule_flush(self) -> None:
        """定期フラッシュタイマーを開始する。"""
        if self._stopped:
            return
        self._flush_timer = threading.Timer(FLUSH_INTERVAL_SEC, self._on_flush_timer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _on_flush_timer(self) -> None:
        """タイマー発火時にフラッシュして次のタイマーをスケジュール。"""
        if self._stopped:
            return
        self._flush_queue()
        self._schedule_flush()

    # ------------------------------------------------------------------
    # 読み取り・検索
    # ------------------------------------------------------------------

    def get_sessions(self, limit: int = 50) -> list[dict]:
        """セッション一覧を新しい順に取得する。"""
        if not self._conn:
            return []
        cursor = self._conn.execute(
            "SELECT s.id, s.start_time, s.end_time, s.channel, s.platform, "
            "  (SELECT COUNT(*) FROM comments c WHERE c.session_id = s.id) AS comment_count "
            "FROM sessions s ORDER BY s.start_time DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "channel": row[3],
                "platform": row[4],
                "comment_count": row[5],
            }
            for row in cursor.fetchall()
        ]

    def get_comments_by_session(self, session_id: int) -> list[dict]:
        """指定セッションのコメントを時系列で取得する。"""
        if not self._conn:
            return []
        cursor = self._conn.execute(
            "SELECT id, timestamp, username, display_name, "
            "original_text, translated_text, source_lang, bits, is_sub "
            "FROM comments WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
        return [
            {
                "id": row[0],
                "timestamp": row[1],
                "username": row[2],
                "display_name": row[3],
                "original_text": row[4],
                "translated_text": row[5],
                "source_lang": row[6],
                "bits": row[7],
                "is_sub": bool(row[8]),
            }
            for row in cursor.fetchall()
        ]

    def search_comments(
        self,
        keyword: str | None = None,
        username: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """コメントを検索する。"""
        if not self._conn:
            return []
        conditions: list[str] = []
        params: list = []
        if keyword:
            conditions.append(
                "(c.original_text LIKE ? OR c.translated_text LIKE ?)"
            )
            like = f"%{keyword}%"
            params.extend([like, like])
        if username:
            conditions.append("(c.username LIKE ? OR c.display_name LIKE ?)")
            user_like = f"%{username}%"
            params.extend([user_like, user_like])
        if date_from:
            conditions.append("c.timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("c.timestamp <= ?")
            params.append(date_to)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT c.id, c.session_id, c.timestamp, c.username, c.display_name, "
            f"c.original_text, c.translated_text, c.source_lang, c.bits, c.is_sub, "
            f"s.channel "
            f"FROM comments c JOIN sessions s ON c.session_id = s.id "
            f"WHERE {where} ORDER BY c.timestamp DESC LIMIT ?"
        )
        params.append(limit)
        cursor = self._conn.execute(sql, params)
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "timestamp": row[2],
                "username": row[3],
                "display_name": row[4],
                "original_text": row[5],
                "translated_text": row[6],
                "source_lang": row[7],
                "bits": row[8],
                "is_sub": bool(row[9]),
                "channel": row[10],
            }
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # クリーンアップ
    # ------------------------------------------------------------------

    def cleanup(self, retention_days: int) -> int:
        """保持期間を超えたセッション・コメントを削除する。

        Returns: 削除されたセッション数
        """
        if not self._conn or retention_days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        cursor = self._conn.execute(
            "SELECT id FROM sessions WHERE start_time < ?", (cutoff,)
        )
        old_ids = [row[0] for row in cursor.fetchall()]
        if not old_ids:
            return 0

        placeholders = ",".join("?" * len(old_ids))
        self._conn.execute(
            f"DELETE FROM comments WHERE session_id IN ({placeholders})", old_ids
        )
        self._conn.execute(
            f"DELETE FROM sessions WHERE id IN ({placeholders})", old_ids
        )
        self._conn.commit()
        logger.info(f"Archive cleanup: removed {len(old_ids)} sessions older than {retention_days} days")

        # VACUUM でDBファイルサイズを縮小
        try:
            self._conn.execute("VACUUM")
        except Exception as e:
            logger.warning(f"Archive VACUUM failed: {e}")

        return len(old_ids)


# ---------------------------------------------------------------------------
# シングルトン
# ---------------------------------------------------------------------------

_instance: SessionArchive | None = None
_instance_lock = threading.Lock()


def get_session_archive() -> SessionArchive:
    """SessionArchiveのシングルトンインスタンスを返す。"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SessionArchive()
    return _instance
