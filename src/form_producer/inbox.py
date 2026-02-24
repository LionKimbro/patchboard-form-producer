"""INBOX directory scanning for Patchboard file-transport messages."""

import json
import os


def scan_inbox(inbox_path):
    """Scan inbox_path for parseable Patchboard message files.

    Returns a list of (filepath, message_dict) for each .json file that
    successfully parses as a JSON object.  Files that fail to parse are
    skipped and left in place (they may be incomplete; retry on next poll).
    """
    if not os.path.isdir(inbox_path):
        return []

    try:
        entries = sorted(os.listdir(inbox_path))
    except OSError:
        return []

    results = []
    for filename in entries:
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(inbox_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue  # incomplete or unreadable — retry next poll
        if isinstance(data, dict):
            results.append((filepath, data))

    return results


def is_text_message(message):
    """Return True if message is a channel='text' Patchboard message with a string signal."""
    return (
        isinstance(message, dict)
        and message.get('channel') == 'text'
        and isinstance(message.get('signal'), str)
    )
