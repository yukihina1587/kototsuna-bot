"""
参加者追跡モジュール
チャットのキーワードを検出して参加者を記録

メモリ最適化:
- Dict使用でO(1)ルックアップ
- 参加者数上限設定
"""
import json
from collections import OrderedDict
from datetime import datetime
from typing import List, Dict, Optional
from src.logger import logger

# メモリ最適化: 参加者数の上限
PARTICIPANT_MAX = 1000


class ParticipantTracker:
    """参加者追跡クラス"""

    def __init__(self, keywords: List[str] = None):
        """
        初期化

        Args:
            keywords: 検出するキーワードリスト（デフォルト: ["参加希望", "参加"]）
        """
        self.keywords = keywords or ["参加希望", "参加", "!参加", "!join"]
        # OrderedDictで挿入順を保持しつつO(1)ルックアップ
        self._participants: OrderedDict[str, Dict[str, str]] = OrderedDict()
        self.enabled = False

    def set_keywords(self, keywords: List[str]):
        """キーワードを設定"""
        self.keywords = keywords
        logger.info(f"参加キーワードを設定: {keywords}")

    def add_keyword(self, keyword: str):
        """キーワードを追加"""
        if keyword and keyword not in self.keywords:
            self.keywords.append(keyword)
            logger.info(f"参加キーワードを追加: {keyword}")

    def remove_keyword(self, keyword: str):
        """キーワードを削除"""
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            logger.info(f"参加キーワードを削除: {keyword}")

    def check_message(self, username: str, message: str) -> bool:
        """
        メッセージにキーワードが含まれているかチェック

        Returns:
            参加者として登録した場合True
        """
        if not self.enabled:
            return False

        for keyword in self.keywords:
            if keyword.lower() in message.lower():
                return self.add_participant(username, message, keyword)

        return False

    def add_participant(self, username: str, message: str, keyword: str) -> bool:
        """
        参加者を追加

        Returns:
            追加に成功した場合True（重複の場合False）
        """
        # O(1)で重複チェック
        if username in self._participants:
            logger.debug(f"Already registered: {username}")
            return False

        # 上限チェック - 古い参加者を削除
        while len(self._participants) >= PARTICIPANT_MAX:
            oldest = next(iter(self._participants))
            del self._participants[oldest]
            logger.debug(f"参加者上限到達、古い参加者を削除: {oldest}")

        # 参加者を追加
        self._participants[username] = {
            'username': username,
            'message': message,
            'keyword': keyword,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        logger.info(f"参加者登録: {username} (キーワード: {keyword})")
        return True

    def remove_participant(self, username: str) -> bool:
        """参加者を削除"""
        if username in self._participants:
            del self._participants[username]
            logger.info(f"参加者削除: {username}")
            return True
        return False

    def get_participants(self) -> List[Dict[str, str]]:
        """参加者リストを取得（後方互換性のためリストで返す）"""
        return list(self._participants.values())

    # 後方互換性のためプロパティを追加
    @property
    def participants(self) -> List[Dict[str, str]]:
        """後方互換性のためリストとしてアクセス可能"""
        return list(self._participants.values())

    def get_participant_names(self) -> List[str]:
        """参加者名のリストを取得"""
        return list(self._participants.keys())

    def get_count(self) -> int:
        """参加者数を取得"""
        return len(self._participants)

    def clear(self):
        """参加者リストをクリア"""
        count = len(self._participants)
        self._participants.clear()
        logger.info(f"参加者リストをクリア ({count}人)")

    def move_participant(self, from_index: int, to_index: int) -> bool:
        """参加者の順序を変更"""
        participants_list = list(self._participants.keys())
        if 0 <= from_index < len(participants_list) and 0 <= to_index < len(participants_list):
            # OrderedDictの順序を変更
            username = participants_list[from_index]
            participant_data = self._participants[username]

            # 新しいOrderedDictを作成して順序を変更
            new_participants = OrderedDict()
            keys = list(self._participants.keys())
            keys.remove(username)
            keys.insert(to_index, username)

            for key in keys:
                new_participants[key] = self._participants[key]

            self._participants = new_participants
            logger.debug(f"参加者順序変更: {from_index} → {to_index}")
            return True
        return False

    def update_participant(self, old_username: str, new_username: str) -> bool:
        """参加者のユーザー名を更新"""
        if old_username in self._participants:
            data = self._participants[old_username]
            data['username'] = new_username
            # 順序を保持しつつキーを変更
            new_participants = OrderedDict()
            for key, value in self._participants.items():
                if key == old_username:
                    new_participants[new_username] = data
                else:
                    new_participants[key] = value
            self._participants = new_participants
            logger.info(f"参加者名変更: {old_username} → {new_username}")
            return True
        return False

    def export_to_text(self) -> str:
        """テキスト形式でエクスポート"""
        if not self._participants:
            return "参加者はいません。"

        lines = [
            "=== 参加者リスト ===",
            f"合計: {len(self._participants)}人",
            f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "No. | ユーザー名 | 登録日時 | キーワード",
            "-" * 60
        ]

        for i, participant in enumerate(self._participants.values(), 1):
            lines.append(
                f"{i:3d} | {participant['username']:20s} | "
                f"{participant['timestamp']} | {participant['keyword']}"
            )

        return "\n".join(lines)

    def export_to_file(self, filepath: str) -> bool:
        """ファイルにエクスポート"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.export_to_text())
            logger.info(f"参加者リストをエクスポート: {filepath}")
            return True
        except Exception as e:
            logger.error(f"エクスポート失敗: {e}", exc_info=True)
            return False

    def export_to_json(self, filepath: str) -> bool:
        """JSON形式でエクスポート"""
        try:
            data = {
                'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(self._participants),
                'keywords': self.keywords,
                'participants': list(self._participants.values())
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


def get_tracker() -> ParticipantTracker:
    """グローバル追跡インスタンスを取得"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = ParticipantTracker()
    return _tracker_instance
