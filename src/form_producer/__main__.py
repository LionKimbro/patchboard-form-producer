"""FileTalk Form Producer — entry point."""

import json
import sys
from pathlib import Path

import lionscliapp as app
from lionscliapp import override_inputs

from .app import run


def _run_command():
    from lionscliapp import ctx, get_path
    config = {
        "outbox": ctx.get("path.outbox"),    # Path (resolved by lionscliapp)
        "inbox": ctx.get("path.inbox"),      # Path (resolved by lionscliapp)
        "channel": ctx.get("channel"),       # str
        "project_dir": get_path(".", "p"),   # Path to .form-producer/
    }
    run(config)


def _make_card_command():
    """Output a Patchboard component ID card describing this form-producer instance."""
    from lionscliapp import ctx

    inbox   = ctx.get("path.inbox")    # Path
    outbox  = ctx.get("path.outbox")   # Path
    channel = ctx.get("channel") or "output"

    card = {
        "schema_version": 1,
        "title": "FileTalk Form Producer",
        "inbox":  str(inbox),
        "outbox": str(outbox),
        "channels": {
            "in":  ["text"],
            "out": [channel],
        },
    }

    # --card-path is a transient CLI option, not persisted to config.
    card_path_str = override_inputs.cli_overrides.get("card-path")
    if card_path_str:
        out_path = Path(card_path_str)
    else:
        out_path = Path.cwd() / "form-producer.card.json"

    try:
        out_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"Error writing card to {out_path}: {e}", file=sys.stderr)
        sys.exit(3)

    print(f"Card written to {out_path}")


app.declare_app("form-producer", "0.1.0")
app.describe_app("Turn a form-spec DSL into a live Tkinter form and emit Patchboard messages.")
app.declare_projectdir(".form-producer")
app.declare_key("path.outbox", ".form-producer/OUTBOX")
app.describe_key("path.outbox", "OUTBOX directory path for emitted messages")
app.declare_key("path.inbox", ".form-producer/INBOX")
app.describe_key("path.inbox", "INBOX directory path to watch for incoming messages")
app.declare_key("channel", "output")
app.describe_key("channel", "Default output channel name")
app.declare_cmd("", _run_command)
app.declare_cmd("make-card", _make_card_command)
app.describe_cmd("make-card", "Output a Patchboard component ID card. Pass --card-path to override output location.")


def main():
    app.main()


if __name__ == "__main__":
    main()
