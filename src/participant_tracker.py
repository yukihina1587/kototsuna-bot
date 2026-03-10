"""
参加者追跡モジュール
チャットのキーワードを検出して参加者を記録
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from src.logger import logger


class ParticipantTracker:
    """参加者追跡クラス"""

    DEFAULT_MAX_PARTICIPANTS = 1000

    def __init__(self, keywords: List[str] = None, max_participants: int = None):
        """
        初期化

        Args:
            keywords: 検出するキーワードリスト（デフォルト: ["参加希望", "参加"]）
            max_participants: 参加者数の上限（デフォルト: 1000）
        """
        self.keywords = keywords or ["参加希望", "参加", "!参加", "!join"]
        self.participants: List[Dict[str, str]] = []
        self.max_participants = max_participants or self.DEFAULT_MAX_PARTICIPANTS
        self.enabled = False
        # ラウンド内で既に試合に参加済みのユーザー名セット
        self.participated: set = set()

    def set_keywords(self, keywords: List[str]):
        """
        キーワードを設定

        Args:
            keywords: 検出するキーワードリスト
        """
        self.keywords = keywords
        logger.info(f"参加キーワードを設定: {keywords}")

    def add_keyword(self, keyword: str):
        """
        キーワードを追加

        Args:
            keyword: 追加するキーワード
        """
        if keyword and keyword not in self.keywords:
            self.keywords.append(keyword)
            logger.info(f"参加キーワードを追加: {keyword}")

    def remove_keyword(self, keyword: str):
        """
        キーワードを削除

        Args:
            keyword: 削除するキーワード
        """
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            logger.info(f"参加キーワードを削除: {keyword}")

    def check_message(self, username: str, message: str) -> bool:
        """
        メッセージにキーワードが含まれているかチェック

        Args:
            username: ユーザー名
            message: メッセージ内容

        Returns:
            参加者として登録した場合True
        """
        if not self.enabled:
            return False

        # メッセージにキーワードが含まれているかチェック
        for keyword in self.keywords:
            if message.strip().lower() == keyword.lower():
                return self.add_participant(username, message, keyword)

        return False

    def add_participant(self, username: str, message: str, keyword: str) -> bool:
        """
        参加者を追加

        Args:
            username: ユーザー名
            message: メッセージ内容
            keyword: 検出されたキーワード

        Returns:
            追加に成功した場合True（重複の場合False）
        """
        # 既に登録されているかチェック
        if any(p['username'] == username for p in self.participants):
            logger.debug(f"Already registered: {username}")
            return False

        # 参加済み（今ラウンドで試合に出た）かチェック
        if username.lower() in self.participated:
            logger.debug(f"Already participated this round: {username}")
            return False

        # 上限チェック
        if len(self.participants) >= self.max_participants:
            logger.warning(f"参加者数上限({self.max_participants})に達しています: {username}")
            return False

        # 参加者を追加
        participant = {
            'username': username,
            'message': message,
            'keyword': keyword,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.participants.append(participant)
        logger.info(f"参加者登録: {username} (キーワード: {keyword})")
        return True

    def remove_participant(self, username: str) -> bool:
        """
        参加者を削除

        Args:
            username: ユーザー名

        Returns:
            削除に成功した場合True
        """
        original_count = len(self.participants)
        self.participants = [p for p in self.participants if p['username'] != username]

        if len(self.participants) < original_count:
            logger.info(f"参加者削除: {username}")
            return True
        return False

    def get_participants(self) -> List[Dict[str, str]]:
        """
        参加者リストを取得

        Returns:
            参加者情報のリスト
        """
        return self.participants.copy()

    def get_participant_names(self) -> List[str]:
        """
        参加者名のリストを取得

        Returns:
            参加者名のリスト
        """
        return [p['username'] for p in self.participants]

    def get_count(self) -> int:
        """
        参加者数を取得

        Returns:
            参加者数
        """
        return len(self.participants)

    def clear(self):
        """参加者リストをクリア"""
        count = len(self.participants)
        self.participants.clear()
        logger.info(f"参加者リストをクリア ({count}人)")

    def mark_as_participated(self, username: str) -> bool:
        """
        指定ユーザーを参加済みとしてマーク（待機リストから除去 → participated に追加）

        Args:
            username: ユーザー名

        Returns:
            成功した場合True（待機リストに存在した場合）
        """
        found = self.remove_participant(username)
        self.participated.add(username.lower())
        logger.info(f"参加済みマーク: {username}")
        return found

    def mark_all_as_participated(self):
        """
        現在の待機参加者を全員参加済みとしてマークし、待機リストをクリアする。
        （ラウンド開始時に呼び出す: 今の待機者を全員「出場済み」へ移動）
        """
        for p in self.participants:
            self.participated.add(p['username'].lower())
        count = len(self.participants)
        self.participants.clear()
        logger.info(f"全員参加済みマーク＆待機リストクリア ({count}人)")

    def reset_participated(self):
        """
        参加済みセットをリセットする。
        全員が1周した後など、次のラウンドで再参加を許可したい場合に呼び出す。
        """
        count = len(self.participated)
        self.participated.clear()
        logger.info(f"参加済みセットをリセット ({count}人分)")

    def get_participated_names(self) -> List[str]:
        """
        参加済みユーザー名のリストを取得

        Returns:
            参加済みユーザー名のリスト（小文字）
        """
        return sorted(self.participated)

    def get_participated_count(self) -> int:
        """
        参加済みユーザー数を取得

        Returns:
            参加済みユーザー数
        """
        return len(self.participated)

    def move_participant(self, from_index: int, to_index: int) -> bool:
        """
        参加者の順序を変更

        Args:
            from_index: 移動元のインデックス
            to_index: 移動先のインデックス

        Returns:
            成功した場合True
        """
        if 0 <= from_index < len(self.participants) and 0 <= to_index < len(self.participants):
            participant = self.participants.pop(from_index)
            self.participants.insert(to_index, participant)
            logger.debug(f"参加者順序変更: {from_index} → {to_index}")
            return True
        return False

    def update_participant(self, old_username: str, new_username: str) -> bool:
        """
        参加者のユーザー名を更新

        Args:
            old_username: 元のユーザー名
            new_username: 新しいユーザー名

        Returns:
            成功した場合True
        """
        for participant in self.participants:
            if participant['username'] == old_username:
                participant['username'] = new_username
                logger.info(f"参加者名変更: {old_username} → {new_username}")
                return True
        return False

    def export_to_text(self) -> str:
        """
        テキスト形式でエクスポート

        Returns:
            参加者リストのテキスト
        """
        if not self.participants:
            return "参加者はいません。"

        lines = [
            "=== 参加者リスト ===",
            f"合計: {len(self.participants)}人",
            f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "No. | ユーザー名 | 登録日時 | キーワード",
            "-" * 60
        ]

        for i, participant in enumerate(self.participants, 1):
            lines.append(
                f"{i:3d} | {participant['username']:20s} | "
                f"{participant['timestamp']} | {participant['keyword']}"
            )

        return "\n".join(lines)

    def export_to_file(self, filepath: str) -> bool:
        """
        ファイルにエクスポート

        Args:
            filepath: 出力先ファイルパス

        Returns:
            成功した場合True
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.export_to_text())
            logger.info(f"参加者リストをエクスポート: {filepath}")
            return True
        except Exception as e:
            logger.error(f"エクスポート失敗: {e}", exc_info=True)
            return False

    def export_to_json(self, filepath: str) -> bool:
        """
        JSON形式でエクスポート

        Args:
            filepath: 出力先ファイルパス

        Returns:
            成功した場合True
        """
        try:
            data = {
                'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(self.participants),
                'keywords': self.keywords,
                'participants': self.participants
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"参加者リストをJSONエクスポート: {filepath}")
            return True
        except Exception as e:
            logger.error(f"JSONエクスポート失敗: {e}", exc_info=True)
            return False

    def enable(self):
        """参加者追跡を有効化"""
        self.enabled = True
        logger.info("参加者追跡を有効化")

    def disable(self):
        """参加者追跡を無効化"""
        self.enabled = False
        logger.info("参加者追跡を無効化")


# グローバルインスタンス
_tracker_instance = None


def get_tracker(max_participants: int = None) -> ParticipantTracker:
    """グローバル追跡インスタンスを取得"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = ParticipantTracker(max_participants=max_participants)
    elif max_participants is not None:
        _tracker_instance.max_participants = max_participants
    return _tracker_instance
