"""翻訳辞書モジュール - CRUD・正規表現・わんこめインポート"""
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional
from src.logger import logger


def _get_dict_file_path() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    path = Path(base) / "Kototsuna"
    path.mkdir(parents=True, exist_ok=True)
    return path / "translation_dict.json"


def _parse_onecomme_regex(pattern: str) -> Optional[str]:
    """わんこめ形式 /pattern/g → Python正規表現パターンを返す。変換不可はNone。"""
    m = re.match(r'^/(.+)/g?$', pattern)
    if not m:
        return None
    return m.group(1)


class TranslationDictionary:
    """翻訳前置換辞書。スレッドセーフ。"""

    def __init__(self, file_path: Optional[Path] = None):
        self._file_path = file_path or _get_dict_file_path()
        self._entries: list[dict] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self._file_path.exists():
                return
            try:
                with open(self._file_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("entries", [])
                logger.info(f"Translation dictionary loaded: {len(self._entries)} entries")
            except Exception as e:
                logger.error(f"Failed to load translation dictionary: {e}")
                self._entries = []

    def _save(self) -> None:
        with self._lock:
            try:
                data = {"version": 1, "entries": self._entries}
                with open(self._file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save translation dictionary: {e}")

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def add(self, source: str, target: str, is_regex: bool = False) -> tuple[bool, str]:
        """エントリを追加する。成功時 (True, ""). 失敗時 (False, reason)."""
        source = source.strip()
        if not source:
            return False, "元の文言を入力してください"
        if is_regex:
            try:
                re.compile(source)
            except re.error as e:
                return False, f"正規表現エラー: {e}"
        with self._lock:
            self._entries.append({"source": source, "target": target, "is_regex": is_regex})
            self._save()
        return True, ""

    def remove(self, index: int) -> Optional[dict]:
        with self._lock:
            if 0 <= index < len(self._entries):
                removed = self._entries.pop(index)
                self._save()
                return removed
        return None

    def clear(self) -> None:
        with self._lock:
            self._entries = []
            self._save()

    def apply(self, text: str) -> str:
        """辞書置換を適用する。"""
        if not text:
            return text
        result = text
        with self._lock:
            entries = list(self._entries)
        for entry in entries:
            src = entry.get("source", "")
            tgt = entry.get("target", "")
            if not src:
                continue
            if entry.get("is_regex", False):
                try:
                    result = re.sub(src, tgt, result)
                except re.error:
                    pass
            else:
                result = result.replace(src, tgt)
        return result

    def migrate_from_config(self, entries: list[dict]) -> int:
        """config.json の translation_dictionary からマイグレーション。追加件数を返す。"""
        added = 0
        with self._lock:
            existing = {e["source"] for e in self._entries}
            for e in entries:
                src = str(e.get("source", e.get("before", ""))).strip()
                tgt = str(e.get("target", e.get("after", ""))).strip()
                if src and src not in existing:
                    self._entries.append({"source": src, "target": tgt, "is_regex": False})
                    existing.add(src)
                    added += 1
            if added:
                self._save()
        return added

    def import_from_onecomme(self) -> tuple[int, int, str]:
        """
        わんこめ辞書をインポートする。
        Returns: (added, skipped, message)
        """
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        dict_files = [
            Path(base) / "onecomme" / "word.dict",
            Path(base) / "onecomme" / "speech.dict",
        ]

        all_entries: list[tuple[str, str, bool]] = []
        for dict_file in dict_files:
            if not dict_file.exists():
                continue
            try:
                with open(dict_file, encoding="utf-8") as f:
                    data = json.load(f)
                for pair in data.get("dictionary", []):
                    if not isinstance(pair, list) or len(pair) < 2:
                        continue
                    raw_src, raw_tgt = str(pair[0]), str(pair[1])
                    if not raw_src:
                        continue
                    py_pattern = _parse_onecomme_regex(raw_src)
                    if py_pattern is not None:
                        # 正規表現エントリ
                        try:
                            re.compile(py_pattern)
                            all_entries.append((py_pattern, raw_tgt, True))
                        except re.error:
                            pass
                    else:
                        all_entries.append((raw_src, raw_tgt, False))
            except Exception as e:
                logger.warning(f"Failed to read {dict_file}: {e}")

        if not all_entries:
            return 0, 0, "わんこめの辞書ファイルが見つかりませんでした"

        added = 0
        skipped = 0
        with self._lock:
            existing = {e["source"] for e in self._entries}
            for src, tgt, is_regex in all_entries:
                if src in existing:
                    skipped += 1
                    continue
                self._entries.append({"source": src, "target": tgt, "is_regex": is_regex})
                existing.add(src)
                added += 1
            if added:
                self._save()

        return added, skipped, ""

    @staticmethod
    def onecomme_available() -> bool:
        """わんこめがインストールされているか確認する。"""
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return (Path(base) / "onecomme").exists()
