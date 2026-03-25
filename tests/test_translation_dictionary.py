"""tests for TranslationDictionary"""
import json
import os
import tempfile
from pathlib import Path
import pytest
from src.translation_dictionary import TranslationDictionary, _parse_onecomme_regex


# --- _parse_onecomme_regex ---

def test_parse_regex_with_g_flag():
    assert _parse_onecomme_regex("/wwwwww+/g") == "wwwwww+"

def test_parse_regex_without_g_flag():
    assert _parse_onecomme_regex("/888+$/") == "888+$"

def test_parse_regex_plain_word():
    assert _parse_onecomme_regex("onecomme") is None

def test_parse_regex_empty():
    assert _parse_onecomme_regex("") is None


# --- TranslationDictionary ---

@pytest.fixture
def tmp_dict(tmp_path):
    return TranslationDictionary(file_path=tmp_path / "test_dict.json")


def test_add_plain_entry(tmp_dict):
    ok, err = tmp_dict.add("foo", "bar")
    assert ok
    assert err == ""
    entries = tmp_dict.get_all()
    assert len(entries) == 1
    assert entries[0] == {"source": "foo", "target": "bar", "is_regex": False}


def test_add_regex_entry(tmp_dict):
    ok, err = tmp_dict.add("w+$", "笑", is_regex=True)
    assert ok
    entries = tmp_dict.get_all()
    assert entries[0]["is_regex"] is True


def test_add_invalid_regex(tmp_dict):
    ok, err = tmp_dict.add("[invalid", "x", is_regex=True)
    assert not ok
    assert "正規表現エラー" in err


def test_remove_entry(tmp_dict):
    tmp_dict.add("foo", "bar")
    removed = tmp_dict.remove(0)
    assert removed["source"] == "foo"
    assert len(tmp_dict.get_all()) == 0


def test_apply_plain(tmp_dict):
    tmp_dict.add("hello", "こんにちは")
    assert tmp_dict.apply("hello world") == "こんにちは world"


def test_apply_regex(tmp_dict):
    tmp_dict.add("w+$", "笑", is_regex=True)
    assert tmp_dict.apply("わははwww") == "わはは笑"          # w+$ matches www at end
    assert tmp_dict.apply("わははwwwとか") == "わははwwwとか"  # $ anchors to end, so no match


def test_apply_regex_wwww(tmp_dict):
    tmp_dict.add("wwwww+", "大草原", is_regex=True)
    assert tmp_dict.apply("わははwwwwwww") == "わははwwwwwww".replace("wwwwwww", "大草原")


def test_migrate_from_config(tmp_dict):
    entries = [
        {"source": "foo", "target": "bar"},
        {"before": "baz", "after": "qux"},  # legacy format
    ]
    added = tmp_dict.migrate_from_config(entries)
    assert added == 2
    assert len(tmp_dict.get_all()) == 2


def test_migrate_skips_duplicates(tmp_dict):
    tmp_dict.add("foo", "bar")
    added = tmp_dict.migrate_from_config([{"source": "foo", "target": "baz"}])
    assert added == 0


def test_persist_and_reload(tmp_path):
    d1 = TranslationDictionary(file_path=tmp_path / "dict.json")
    d1.add("x", "y")
    d2 = TranslationDictionary(file_path=tmp_path / "dict.json")
    assert len(d2.get_all()) == 1
    assert d2.get_all()[0]["source"] == "x"
