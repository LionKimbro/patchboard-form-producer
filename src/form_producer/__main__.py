"""FileTalk Form Producer — entry point."""

import argparse
import os

from .app import run


def main():
    parser = argparse.ArgumentParser(
        prog="form-producer",
        description="Turn a form-spec DSL into a live Tkinter form and emit Patchboard messages.",
    )
    parser.add_argument("--outbox", default=None, help="Override OUTBOX directory path")
    parser.add_argument("--channel", default=None, help="Override default output channel")
    parser.add_argument("--spec", default=None, metavar="FILE",
                        help="DSL spec file to load into the editor on startup")
    args = parser.parse_args()

    config = {
        "outbox": args.outbox or os.environ.get("FORM_PRODUCER_OUTBOX"),
        "channel": args.channel or os.environ.get("FORM_PRODUCER_CHANNEL"),
        "spec_path": args.spec,
    }

    run(config)


if __name__ == "__main__":
    main()
