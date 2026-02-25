"""FileTalk Form Producer — entry point."""

import lionscliapp as app

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


app.declare_app("form-producer", "0.1.0")
app.describe_app("Turn a form-spec DSL into a live Tkinter form and emit Patchboard messages.")
app.declare_projectdir(".form-producer")
app.declare_key("path.outbox", "OUTBOX")
app.describe_key("path.outbox", "OUTBOX directory path for emitted messages")
app.declare_key("path.inbox", "INBOX")
app.describe_key("path.inbox", "INBOX directory path to watch for incoming messages")
app.declare_key("channel", "output")
app.describe_key("channel", "Default output channel name")
app.declare_cmd("", _run_command)


def main():
    app.main()


if __name__ == "__main__":
    main()
