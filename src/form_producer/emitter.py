"""Message building and file writing."""

import json
import os
import time
import uuid


class EmitError(Exception):
    pass


def emit_message(signal, channel, outbox_path):
    """Build a Patchboard core message and write it to outbox_path.

    Writes directly to the final filename (no temp-file + rename) per the
    file-transport profile.  Returns the written filename (basename only).
    """
    message = {
        "channel": channel,
        "timestamp": str(time.time()),
        "signal": signal,
    }

    try:
        os.makedirs(outbox_path, exist_ok=True)
    except OSError as e:
        raise EmitError(f"Cannot create OUTBOX directory '{outbox_path}': {e}")

    filename = str(uuid.uuid4()) + ".json"
    filepath = os.path.join(outbox_path, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(message, f, ensure_ascii=False)
            f.write('\n')
    except OSError as e:
        raise EmitError(f"Cannot write file '{filepath}': {e}")

    return filename
