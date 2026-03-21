"""SessionArchive のユニットテスト。"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.session_archive import SessionArchive


@pytest.fixture
def archive(tmp_path):
    """一時ディレクトリにアーカイブDBを作成するフィクスチャ。"""
    with patch("src.session_archive._get_archive_dir", return_value=tmp_path):
        arc = SessionArchive()
        arc.open()
        yield arc
        arc.close()


class TestSessionLifecycle:
    """セッション開始・終了のテスト。"""

    def test_start_and_end_session(self, archive):
        sid = archive.start_session("test_channel")
        assert sid is not None
        assert archive._current_session_id == sid

        archive.end_session()
        assert archive._current_session_id is None

        sessions = archive.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["channel"] == "test_channel"
        assert sessions[0]["end_time"] is not None

    def test_multiple_sessions(self, archive):
        archive.start_session("channel_a")
        archive.end_session()
        archive.start_session("channel_b")
        archive.end_session()

        sessions = archive.get_sessions()
        assert len(sessions) == 2
        # 新しい順に返る
        assert sessions[0]["channel"] == "channel_b"
        assert sessions[1]["channel"] == "channel_a"


class TestCommentArchiving:
    """コメント書き込み・読み取りのテスト。"""

    def test_add_and_retrieve_comments(self, archive):
        sid = archive.start_session("test_channel")
        archive.add_comment(
            username="user1",
            display_name="User One",
            original_text="hello",
            translated_text="こんにちは",
            source_lang="en",
        )
        archive.add_comment(
            username="user2",
            display_name=None,
            original_text="おはよう",
        )
        # フラッシュして読み取り
        archive._flush_queue()

        comments = archive.get_comments_by_session(sid)
        assert len(comments) == 2
        assert comments[0]["username"] == "user1"
        assert comments[0]["translated_text"] == "こんにちは"
        assert comments[1]["username"] == "user2"
        assert comments[1]["translated_text"] is None

    def test_comment_without_session_is_ignored(self, archive):
        # セッション開始前にコメントを追加
        archive.add_comment(
            username="orphan",
            display_name=None,
            original_text="should be ignored",
        )
        archive._flush_queue()
        # セッションが無いのでcommentsテーブルは空
        cursor = archive._conn.execute("SELECT COUNT(*) FROM comments")
        assert cursor.fetchone()[0] == 0

    def test_bits_and_sub_fields(self, archive):
        archive.start_session("test_channel")
        archive.add_comment(
            username="donor",
            display_name="Donor",
            original_text="cheer100",
            bits=100,
            is_sub=True,
        )
        archive._flush_queue()

        comments = archive.get_comments_by_session(archive._current_session_id)
        assert comments[0]["bits"] == 100
        assert comments[0]["is_sub"] is True

    def test_session_comment_count(self, archive):
        archive.start_session("test_channel")
        for i in range(10):
            archive.add_comment(
                username=f"user{i}",
                display_name=None,
                original_text=f"message {i}",
            )
        archive._flush_queue()

        sessions = archive.get_sessions()
        assert sessions[0]["comment_count"] == 10


class TestSearch:
    """コメント検索のテスト。"""

    def test_search_by_keyword(self, archive):
        archive.start_session("test_channel")
        archive.add_comment(username="a", display_name=None, original_text="apple pie")
        archive.add_comment(username="b", display_name=None, original_text="banana split")
        archive.add_comment(username="c", display_name=None, original_text="apple juice", translated_text="りんごジュース")
        archive._flush_queue()

        results = archive.search_comments(keyword="apple")
        assert len(results) == 2

    def test_search_by_username(self, archive):
        archive.start_session("test_channel")
        archive.add_comment(username="alice", display_name="Alice", original_text="hi")
        archive.add_comment(username="bob", display_name="Bob", original_text="hey")
        archive._flush_queue()

        results = archive.search_comments(username="alice")
        assert len(results) == 1
        assert results[0]["username"] == "alice"

    def test_search_by_translated_text(self, archive):
        archive.start_session("test_channel")
        archive.add_comment(username="a", display_name=None, original_text="hello", translated_text="こんにちは")
        archive.add_comment(username="b", display_name=None, original_text="goodbye", translated_text="さようなら")
        archive._flush_queue()

        results = archive.search_comments(keyword="こんにちは")
        assert len(results) == 1


class TestCleanup:
    """保持期間に基づくクリーンアップのテスト。"""

    def test_cleanup_removes_old_sessions(self, archive):
        # 古いセッションを手動で挿入
        old_time = (datetime.now() - timedelta(days=100)).isoformat()
        archive._conn.execute(
            "INSERT INTO sessions (start_time, end_time, channel, platform) VALUES (?, ?, ?, ?)",
            (old_time, old_time, "old_channel", "twitch"),
        )
        archive._conn.execute(
            "INSERT INTO comments (session_id, timestamp, username, original_text) VALUES (?, ?, ?, ?)",
            (1, old_time, "old_user", "old message"),
        )
        archive._conn.commit()

        # 新しいセッション
        archive.start_session("new_channel")
        archive.add_comment(username="new_user", display_name=None, original_text="new message")
        archive._flush_queue()

        removed = archive.cleanup(retention_days=90)
        assert removed == 1

        sessions = archive.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["channel"] == "new_channel"

        # 古いコメントも削除されている
        cursor = archive._conn.execute("SELECT COUNT(*) FROM comments WHERE session_id = 1")
        assert cursor.fetchone()[0] == 0

    def test_cleanup_with_zero_retention_does_nothing(self, archive):
        archive.start_session("test_channel")
        archive.add_comment(username="a", display_name=None, original_text="msg")
        archive._flush_queue()

        removed = archive.cleanup(retention_days=0)
        assert removed == 0
