"""視聴者データの永続化ストア。

視聴回数トラッキングと VOICEVOX ボイス割り当てを管理する。
JSON ファイルでデータを永続化し、アトミック書き込みでデータ安全性を保証する。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from src.logger import logger


VoiceId = Union[int, str]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ViewerData:
    """視聴者データモデル。

    Attributes:
        display_name: 表示名
        visit_count: 視聴回数（1枠=1回）
        first_seen: 初回検出日時 (ISO 8601)
        last_seen: 最終検出日時 (ISO 8601)
        last_session_id: 最後に検出されたセッションID
        assigned_voice: ボイス割り当て情報（None=未割り当て）
    """

    display_name: str
    visit_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    last_session_id: str = ""
    assigned_voice: Optional[dict] = None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

_FILE_VERSION = 1


class ViewerStore:
    """視聴者データの永続化ストア。

    Bot 起動時にセッション ID を生成し、各ユーザーの初回メッセージで
    visit_count をインクリメントする。ボイス割り当ての CRUD も提供する。
    """

    def __init__(self, filepath: Optional[str] = None) -> None:
        if filepath is None:
            from src.config import CONFIG_FILE
            config_dir = os.path.dirname(os.path.abspath(CONFIG_FILE))
            filepath = os.path.join(config_dir, "viewer_data.json")

        self._filepath = filepath
        self._viewers: dict[str, ViewerData] = {}
        self._session_id = datetime.now().isoformat()
        self._seen_this_session: set[str] = set()
        self._lock = threading.Lock()
        self.load()

    @property
    def session_id(self) -> str:
        """現在のセッション ID"""
        return self._session_id

    # -- Persistence --------------------------------------------------------

    def load(self) -> None:
        """JSON ファイルから視聴者データを読み込む。"""
        if not os.path.exists(self._filepath):
            self._viewers = {}
            return

        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_viewers: dict = data.get("viewers", {})
            self._viewers = {}
            for username, vd in raw_viewers.items():
                self._viewers[username.lower()] = ViewerData(
                    display_name=vd.get("display_name", username),
                    visit_count=vd.get("visit_count", 0),
                    first_seen=vd.get("first_seen", ""),
                    last_seen=vd.get("last_seen", ""),
                    last_session_id=vd.get("last_session_id", ""),
                    assigned_voice=vd.get("assigned_voice"),
                )
            logger.info("視聴者データを読み込みました: %d 人", len(self._viewers))
        except Exception:
            logger.error(
                "視聴者データの読み込みに失敗: %s", self._filepath, exc_info=True
            )
            self._viewers = {}

    def save(self) -> None:
        """現在の視聴者データを JSON ファイルへアトミックに書き出す。"""
        payload: dict = {"version": _FILE_VERSION, "viewers": {}}
        for username, viewer in sorted(self._viewers.items()):
            payload["viewers"][username] = {
                "display_name": viewer.display_name,
                "visit_count": viewer.visit_count,
                "first_seen": viewer.first_seen,
                "last_seen": viewer.last_seen,
                "last_session_id": viewer.last_session_id,
                "assigned_voice": viewer.assigned_voice,
            }

        tmp_path = self._filepath + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._filepath)
            logger.debug("視聴者データを保存しました: %d 人", len(self._viewers))
        except Exception:
            logger.error("視聴者データの保存に失敗", exc_info=True)

    # -- Visit tracking -----------------------------------------------------

    def record_visit(self, username: str, display_name: str) -> int:
        """訪問を記録する。同一セッション内では 1 回だけカウント。

        Args:
            username: Twitch ユーザー名（小文字正規化される）
            display_name: 表示名

        Returns:
            更新後の visit_count
        """
        key = username.lower()
        now = datetime.now().isoformat()

        with self._lock:
            if key not in self._viewers:
                self._viewers[key] = ViewerData(
                    display_name=display_name,
                    first_seen=now,
                    last_seen=now,
                )

            viewer = self._viewers[key]
            viewer.display_name = display_name
            viewer.last_seen = now

            if key not in self._seen_this_session:
                self._seen_this_session.add(key)
                viewer.visit_count += 1
                viewer.last_session_id = self._session_id
                self.save()
                logger.info(
                    "視聴回数を記録: %s (%s) = %d回目",
                    display_name,
                    username,
                    viewer.visit_count,
                )

            return viewer.visit_count

    # -- Viewer queries -----------------------------------------------------

    def get_viewer(self, username: str) -> Optional[ViewerData]:
        """ユーザー名で視聴者データを取得する。"""
        with self._lock:
            return self._viewers.get(username.lower())

    def get_visit_count(self, username: str) -> int:
        """ユーザーの視聴回数を返す。未記録なら 0。"""
        viewer = self.get_viewer(username)
        return viewer.visit_count if viewer else 0

    # -- Voice assignment ---------------------------------------------------

    def get_assigned_voice(self, username: str) -> Optional[VoiceId]:
        """ユーザーに割り当てられた voice_id を返す。なければ None。

        後方互換: 旧フォーマット（``speaker_id`` のみ）と新フォーマット
        （``voice_id``+``engine``）の両方を読める。エンジン情報が必要な場合は
        ``get_assigned_voice_spec`` を使う。

        ``voice_id`` は int（VOICEVOX 系）または str（edge-tts 等）のどちらか。
        """
        viewer = self.get_viewer(username)
        if viewer and viewer.assigned_voice:
            voice = viewer.assigned_voice
            return voice.get("voice_id", voice.get("speaker_id"))
        return None

    def get_assigned_voice_spec(self, username: str) -> Optional[dict]:
        """割り当てられたボイス情報を ``{engine, voice_id, voice_name}`` で返す。

        旧フォーマット（engine キーなし）は ``engine="voicevox"`` として解釈する。
        """
        viewer = self.get_viewer(username)
        if not (viewer and viewer.assigned_voice):
            return None
        voice = viewer.assigned_voice
        return {
            "engine": voice.get("engine", "voicevox"),
            "voice_id": voice.get("voice_id", voice.get("speaker_id")),
            "voice_name": voice.get("voice_name", voice.get("speaker_name", "")),
        }

    def assign_voice(
        self,
        username: str,
        speaker_id: VoiceId,
        speaker_name: str,
        assigned_by: str,
        engine: str = "voicevox",
    ) -> bool:
        """ユーザーにボイスを割り当てる。

        Args:
            username: 対象ユーザー名
            speaker_id: 現行エンジンの voice ID（int または str）
            speaker_name: 表示名
            assigned_by: 割り当てた人の名前
            engine: TTS エンジン識別子（voicevox / coeiroink / aivisspeech / sharevox / edge-tts）

        Returns:
            常に True
        """
        key = username.lower()
        now = datetime.now().isoformat()

        with self._lock:
            viewer = self._viewers.get(key)
            if viewer is None:
                viewer = ViewerData(
                    display_name=username,
                    first_seen=now,
                    last_seen=now,
                )
                self._viewers[key] = viewer

            viewer.assigned_voice = {
                # 新フォーマット
                "engine": engine,
                "voice_id": speaker_id,
                "voice_name": speaker_name,
                # 旧フォーマット（後方互換のため残す）
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "assigned_by": assigned_by,
                "assigned_at": now,
            }
            self.save()
            logger.info(
                "ボイス割り当て: %s -> %s (%s ID: %d) by %s",
                username,
                speaker_name,
                engine,
                speaker_id,
                assigned_by,
            )
        return True

    def remove_voice(self, username: str) -> bool:
        """ユーザーのボイス割り当てを解除する。

        Returns:
            解除できた場合 True、割り当てがなかった場合 False
        """
        key = username.lower()
        with self._lock:
            viewer = self._viewers.get(key)
            if viewer is None or viewer.assigned_voice is None:
                return False
            viewer.assigned_voice = None
            self.save()
            logger.info("ボイス割り当て解除: %s", username)
        return True

    def get_viewers_with_voice(self) -> list[tuple[str, dict]]:
        """ボイスが割り当てられている視聴者のリストを返す。"""
        with self._lock:
            result = []
            for username, viewer in self._viewers.items():
                if viewer.assigned_voice:
                    result.append((username, viewer.assigned_voice))
            return sorted(result, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_viewer_store: Optional[ViewerStore] = None


def get_viewer_store() -> ViewerStore:
    """グローバル ViewerStore インスタンスを取得または生成する。"""
    global _viewer_store
    if _viewer_store is None:
        _viewer_store = ViewerStore()
    return _viewer_store
