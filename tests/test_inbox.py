"""Unit tests for INBOX scanning and message filtering."""

import json
import os

import pytest
from form_producer.inbox import is_text_message, scan_inbox


# ---------------------------------------------------------------------------
# scan_inbox
# ---------------------------------------------------------------------------

def test_nonexistent_directory(tmp_path):
    assert scan_inbox(str(tmp_path / "nonexistent")) == []


def test_empty_directory(tmp_path):
    assert scan_inbox(str(tmp_path)) == []


def test_scans_valid_json_object(tmp_path):
    msg = {"channel": "text", "signal": "hello", "timestamp": "123"}
    (tmp_path / "msg.json").write_text(json.dumps(msg), encoding="utf-8")
    results = scan_inbox(str(tmp_path))
    assert len(results) == 1
    filepath, data = results[0]
    assert data == msg
    assert filepath.endswith("msg.json")


def test_skips_non_json_extension(tmp_path):
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
    assert scan_inbox(str(tmp_path)) == []


def test_skips_incomplete_json(tmp_path):
    (tmp_path / "partial.json").write_text('{"channel": "text"', encoding="utf-8")
    assert scan_inbox(str(tmp_path)) == []


def test_skips_json_array(tmp_path):
    (tmp_path / "array.json").write_text('[1, 2, 3]', encoding="utf-8")
    assert scan_inbox(str(tmp_path)) == []


def test_skips_json_scalar(tmp_path):
    (tmp_path / "scalar.json").write_text('"just a string"', encoding="utf-8")
    assert scan_inbox(str(tmp_path)) == []


def test_returns_multiple_files_sorted(tmp_path):
    for name in ("b.json", "a.json", "c.json"):
        (tmp_path / name).write_text(json.dumps({"channel": "x"}), encoding="utf-8")
    results = scan_inbox(str(tmp_path))
    names = [os.path.basename(fp) for fp, _ in results]
    assert names == ["a.json", "b.json", "c.json"]


def test_incomplete_file_does_not_block_others(tmp_path):
    (tmp_path / "bad.json").write_text('{bad', encoding="utf-8")
    good = {"channel": "text", "signal": "ok", "timestamp": "1"}
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    results = scan_inbox(str(tmp_path))
    assert len(results) == 1
    assert results[0][1] == good


# ---------------------------------------------------------------------------
# is_text_message
# ---------------------------------------------------------------------------

def test_is_text_message_valid():
    assert is_text_message({"channel": "text", "signal": "hello", "timestamp": "1"})


def test_is_text_message_wrong_channel():
    assert not is_text_message({"channel": "other", "signal": "hello"})


def test_is_text_message_signal_not_string():
    assert not is_text_message({"channel": "text", "signal": {"key": "val"}})


def test_is_text_message_signal_null():
    assert not is_text_message({"channel": "text", "signal": None})


def test_is_text_message_signal_list():
    assert not is_text_message({"channel": "text", "signal": ["a", "b"]})


def test_is_text_message_empty_dict():
    assert not is_text_message({})


def test_is_text_message_missing_signal():
    assert not is_text_message({"channel": "text"})


def test_is_text_message_empty_string_signal_is_valid():
    assert is_text_message({"channel": "text", "signal": ""})
