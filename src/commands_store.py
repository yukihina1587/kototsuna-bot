"""カスタムチャットコマンドの永続化ストア。

JSON ファイルでカスタムコマンドを管理し、
アトミック書き込みによるデータ安全性を保証する。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, fields
from typing import Optional

from src.logger import logger


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class CustomCommand:
    """カスタムコマンドのデータモデル。

    Attributes:
        name: コマンド名（先頭 ``!`` は含まない想定）。
        response: コマンド応答テンプレート。
        permission: 必要権限レベル (0‑4, PermissionLevel に対応)。
        cooldown_global: グローバルクールダウン（秒）。
        cooldown_user: ユーザー単位クールダウン（秒）。
        enabled: コマンドが有効かどうか。
    """

    name: str
    response: str
    permission: int = 0
    cooldown_global: float = 5.0
    cooldown_user: float = 15.0
    enabled: bool = True


# ---------------------------------------------------------------------------
# ストア
# ---------------------------------------------------------------------------

_FILE_VERSION = 1


class CommandStore:
    """カスタムコマンドの読み書きを担うストアクラス。

    コマンド名は内部で小文字に正規化して管理する。
    ファイル保存はアトミック書き込み（``.tmp`` → ``os.replace``）で行う。
    """

    def __init__(self, filepath: str = "custom_commands.json") -> None:
        """ストアを初期化しファイルから読み込む。

        Args:
            filepath: コマンド定義 JSON のパス。
        """
        self._filepath = filepath
        self._commands: dict[str, CustomCommand] = {}
        self.load()

    # -- 永続化 -------------------------------------------------------------

    def load(self) -> None:
        """JSON ファイルからコマンドを読み込む。

        ファイルが存在しない場合は空のストアとして初期化する。
        """
        if not os.path.exists(self._filepath):
            logger.info("コマンドファイルが存在しないため空で初期化: %s", self._filepath)
            self._commands = {}
            return

        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_commands: list[dict] = data.get("commands", [])
            valid_keys = {field.name for field in fields(CustomCommand)}
            self._commands = {}
            for entry in raw_commands:
                filtered = {k: v for k, v in entry.items() if k in valid_keys}
                cmd = CustomCommand(**filtered)
                self._commands[cmd.name.lower()] = cmd
            logger.info("カスタムコマンドを読み込みました: %d 件", len(self._commands))
        except Exception:
            logger.error("コマンドファイルの読み込みに失敗: %s", self._filepath, exc_info=True)
            self._commands = {}

    def save(self) -> None:
        """現在のコマンドを JSON ファイルへアトミックに書き出す。

        Windows でファイルがロック中でも最大 3 回リトライする。
        """
        payload = {
            "version": _FILE_VERSION,
            "commands": [asdict(cmd) for cmd in self.list_all()],
        }
        tmp_path = self._filepath + ".tmp"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._filepath)
                logger.debug("コマンドファイルを保存しました: %d 件", len(self._commands))
                return
            except PermissionError as exc:
                last_exc = exc
                logger.warning("コマンドファイル保存リトライ (%d/3): %s", attempt + 1, exc)
                time.sleep(0.2 * (attempt + 1))
            except Exception as exc:
                last_exc = exc
                break
        logger.error("コマンドファイルの保存に失敗: %s", last_exc, exc_info=True)

    # -- CRUD ---------------------------------------------------------------

    def get(self, name: str) -> Optional[CustomCommand]:
        """コマンドを名前で取得する（大文字小文字を区別しない）。

        Args:
            name: コマンド名。

        Returns:
            見つかった場合は ``CustomCommand``、なければ ``None``。
        """
        return self._commands.get(name.lower())

    def add(self, cmd: CustomCommand) -> bool:
        """コマンドを追加する。同名が既に存在する場合は追加しない。

        Args:
            cmd: 追加するコマンド。

        Returns:
            追加できた場合 ``True``、既に存在する場合 ``False``。
        """
        key = cmd.name.lower()
        if key in self._commands:
            logger.warning("コマンドは既に存在します: %s", cmd.name)
            return False
        self._commands[key] = cmd
        self.save()
        logger.info("コマンドを追加しました: %s", cmd.name)
        return True

    def update(self, name: str, **kwargs: object) -> bool:
        """既存コマンドのフィールドを更新する。

        Args:
            name: 更新対象のコマンド名。
            **kwargs: 更新するフィールドと値。

        Returns:
            更新できた場合 ``True``、コマンドが見つからない場合 ``False``。
        """
        key = name.lower()
        cmd = self._commands.get(key)
        if cmd is None:
            logger.warning("更新対象のコマンドが見つかりません: %s", name)
            return False

        valid_keys = {field.name for field in fields(CustomCommand)}
        for k, v in kwargs.items():
            if k in valid_keys:
                setattr(cmd, k, v)
        self.save()
        logger.info("コマンドを更新しました: %s", name)
        return True

    def remove(self, name: str) -> bool:
        """コマンドを削除する。

        Args:
            name: 削除するコマンド名。

        Returns:
            削除できた場合 ``True``、見つからない場合 ``False``。
        """
        key = name.lower()
        if key not in self._commands:
            logger.warning("削除対象のコマンドが見つかりません: %s", name)
            return False
        del self._commands[key]
        self.save()
        logger.info("コマンドを削除しました: %s", name)
        return True

    def list_all(self) -> list[CustomCommand]:
        """全コマンドを名前順で返す。

        Returns:
            名前の昇順でソートされたコマンドのリスト。
        """
        return sorted(self._commands.values(), key=lambda c: c.name.lower())
