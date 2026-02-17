"""CommandStore / CustomCommand のユニットテスト。"""

import json

import pytest
from unittest.mock import patch

from src.commands_store import CommandStore, CustomCommand


# ---------------------------------------------------------------------------
# TestCustomCommand
# ---------------------------------------------------------------------------


class TestCustomCommand:
    """CustomCommand dataclass のテスト。"""

    def test_default_values(self) -> None:
        cmd = CustomCommand(name="hello", response="Hello!")
        assert cmd.name == "hello"
        assert cmd.response == "Hello!"
        assert cmd.permission == 0
        assert cmd.cooldown_global == 5.0
        assert cmd.cooldown_user == 15.0
        assert cmd.enabled is True

    def test_custom_values(self) -> None:
        cmd = CustomCommand(
            name="vip",
            response="VIP only",
            permission=3,
            cooldown_global=10.0,
            cooldown_user=30.0,
            enabled=False,
        )
        assert cmd.name == "vip"
        assert cmd.response == "VIP only"
        assert cmd.permission == 3
        assert cmd.cooldown_global == 10.0
        assert cmd.cooldown_user == 30.0
        assert cmd.enabled is False


# ---------------------------------------------------------------------------
# TestCommandStore
# ---------------------------------------------------------------------------


class TestCommandStore:
    """CommandStore CRUD とファイル永続化のテスト。"""

    def test_load_nonexistent_file_creates_empty_store(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "missing.json")
        store = CommandStore(filepath=filepath)
        assert store.list_all() == []

    def test_add_command_and_get(self, tmp_path: "pytest.TempPathFactory") -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        cmd = CustomCommand(name="greet", response="Hi there!")
        assert store.add(cmd) is True
        assert store.get("greet") is not None
        assert store.get("greet").response == "Hi there!"

    def test_add_duplicate_returns_false(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        cmd = CustomCommand(name="greet", response="Hi!")
        store.add(cmd)
        duplicate = CustomCommand(name="greet", response="Yo!")
        assert store.add(duplicate) is False
        # 元のレスポンスが保持されていること
        assert store.get("greet").response == "Hi!"

    def test_get_is_case_insensitive(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        store.add(CustomCommand(name="Hello", response="world"))
        assert store.get("hello") is not None
        assert store.get("HELLO") is not None
        assert store.get("HeLLo") is not None
        assert store.get("hello").response == "world"

    def test_remove_existing_returns_true(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        store.add(CustomCommand(name="bye", response="Goodbye!"))
        assert store.remove("bye") is True
        assert store.get("bye") is None

    def test_remove_nonexistent_returns_false(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)
        assert store.remove("nope") is False

    def test_update_existing_command_fields(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        store.add(CustomCommand(name="info", response="Original"))
        assert store.update("info", response="Updated", cooldown_global=20.0) is True

        cmd = store.get("info")
        assert cmd.response == "Updated"
        assert cmd.cooldown_global == 20.0
        # 変更していないフィールドは維持される
        assert cmd.permission == 0
        assert cmd.enabled is True

    def test_update_nonexistent_returns_false(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)
        assert store.update("ghost", response="boo") is False

    def test_list_all_returns_sorted_commands(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "cmds.json")
        store = CommandStore(filepath=filepath)

        store.add(CustomCommand(name="cherry", response="c"))
        store.add(CustomCommand(name="apple", response="a"))
        store.add(CustomCommand(name="banana", response="b"))

        result = store.list_all()
        names = [cmd.name for cmd in result]
        assert names == ["apple", "banana", "cherry"]

    def test_json_round_trip(self, tmp_path: "pytest.TempPathFactory") -> None:
        """add したコマンドを保存し、新しい store で読み込んでデータが保持されることを確認。"""
        filepath = str(tmp_path / "cmds.json")
        store1 = CommandStore(filepath=filepath)

        store1.add(CustomCommand(name="cmd1", response="resp1", permission=2))
        store1.add(
            CustomCommand(
                name="cmd2",
                response="resp2",
                cooldown_global=10.0,
                enabled=False,
            )
        )

        # 同じファイルから新しいストアを生成
        store2 = CommandStore(filepath=filepath)
        assert len(store2.list_all()) == 2

        c1 = store2.get("cmd1")
        assert c1 is not None
        assert c1.response == "resp1"
        assert c1.permission == 2

        c2 = store2.get("cmd2")
        assert c2 is not None
        assert c2.response == "resp2"
        assert c2.cooldown_global == 10.0
        assert c2.enabled is False

    def test_invalid_json_file_handled_gracefully(
        self, tmp_path: "pytest.TempPathFactory"
    ) -> None:
        filepath = str(tmp_path / "bad.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("{{{not valid json!!!")

        store = CommandStore(filepath=filepath)
        # 壊れた JSON でもクラッシュせず空ストアで初期化される
        assert store.list_all() == []
