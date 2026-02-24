"""Unit tests for the message emitter."""

import json
import os
import uuid

import pytest
from form_producer.emitter import EmitError, emit_message


def test_emits_json_file(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({"x": 1}, "test-channel", outbox)
    assert filename.endswith(".json")
    filepath = os.path.join(outbox, filename)
    assert os.path.exists(filepath)


def test_emitted_file_is_valid_json(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({"x": 1}, "test-channel", outbox)
    with open(os.path.join(outbox, filename), encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_emitted_message_has_required_keys(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({"x": 1}, "my-channel", outbox)
    with open(os.path.join(outbox, filename), encoding="utf-8") as f:
        data = json.load(f)
    assert "channel" in data
    assert "timestamp" in data
    assert "signal" in data


def test_emitted_channel_matches(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({}, "hello", outbox)
    with open(os.path.join(outbox, filename), encoding="utf-8") as f:
        data = json.load(f)
    assert data["channel"] == "hello"


def test_emitted_signal_matches(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    signal = {"name": "Alice", "count": 3, "active": True}
    filename = emit_message(signal, "ch", outbox)
    with open(os.path.join(outbox, filename), encoding="utf-8") as f:
        data = json.load(f)
    assert data["signal"] == signal


def test_timestamp_is_string(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({}, "ch", outbox)
    with open(os.path.join(outbox, filename), encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data["timestamp"], str)


def test_filename_is_uuid4(tmp_path):
    outbox = str(tmp_path / "OUTBOX")
    filename = emit_message({}, "ch", outbox)
    stem = filename[:-5]  # strip .json
    parsed = uuid.UUID(stem, version=4)
    assert str(parsed) == stem


def test_creates_outbox_if_missing(tmp_path):
    outbox = str(tmp_path / "deep" / "OUTBOX")
    assert not os.path.exists(outbox)
    emit_message({}, "ch", outbox)
    assert os.path.isdir(outbox)


def test_emit_error_on_bad_path():
    # Use a path that cannot be created (file exists where dir should be)
    import tempfile
    with tempfile.NamedTemporaryFile() as f:
        bad_outbox = f.name  # a file, not a directory
        with pytest.raises(EmitError):
            emit_message({}, "ch", os.path.join(bad_outbox, "subdir"))
