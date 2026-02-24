"""FileTalk Form Producer — Tkinter application."""

import datetime
import json
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from .parser import ParseError, parse_spec
from .emitter import EmitError, emit_message


# One canonical global bundle.
g = {}

_STATUS_SUCCESS_MS = 4000

_HINT_SYNTAX  = '<identifier> -- <type>   # channel <channel>   # outbox <path>'
_HINT_TYPES   = 'str<w>  text<w,h>  choice<a,b,...>  bool  int<w>  float<w>  json<w,h>  date  time  "fixed value"'
_HINT_KEYS    = "Ctrl+Enter: render form      Ctrl+S: save to OUTBOX"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(config):
    """Build the UI and enter the main loop.

    config keys (all optional, None means not set):
        channel   — override default channel
        outbox    — override default OUTBOX path
        spec_path — path to a DSL file to load on startup
    """
    g["config"] = config
    g["fields"] = None      # list of field dicts after a successful parse
    g["directives"] = {}    # directive overrides from last successful parse
    g["widgets"] = {}       # {field_id: widget}
    g["vars"] = {}          # {field_id: BooleanVar} for checkbuttons
    g["status_clear_id"] = None

    _setup_ui()

    if config.get("spec_path"):
        _load_spec_file(config["spec_path"])

    g["root"].mainloop()


# ---------------------------------------------------------------------------
# UI construction
# ---------------------------------------------------------------------------

def _setup_ui():
    root = tk.Tk()
    root.title("FileTalk Form Producer")
    root.minsize(700, 500)
    root.option_add('*tearOff', False)
    g["root"] = root

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)   # top pane
    root.rowconfigure(1, weight=0)   # hint: syntax
    root.rowconfigure(2, weight=0)   # hint: types
    root.rowconfigure(3, weight=0)   # hint: keybindings
    root.rowconfigure(4, weight=1)   # bottom pane
    root.rowconfigure(5, weight=0)   # bottom bar (Open OUTBOX + status)

    _build_top_pane(root)
    _build_help_hints(root)
    _build_bottom_pane(root)
    _build_bottom_bar(root)

    root.bind("<Control-Return>", handle_ctrl_enter)
    root.bind("<Control-s>", handle_ctrl_s)
    root.bind("<Control-l>", handle_ctrl_l)


def _build_top_pane(root):
    frame = tk.Frame(root)
    frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    text = tk.Text(frame, font=("Courier", 10), wrap="none", undo=True)
    text.grid(row=0, column=0, sticky="nsew")

    sy = tk.Scrollbar(frame, orient="vertical", command=text.yview)
    sy.grid(row=0, column=1, sticky="ns")
    sx = tk.Scrollbar(frame, orient="horizontal", command=text.xview)
    sx.grid(row=1, column=0, sticky="ew")
    text.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

    g["top_text"] = text


def _build_help_hints(root):
    _hint_label(root, _HINT_SYNTAX, row=1, pady=(4, 0))
    _hint_label(root, _HINT_TYPES,  row=2, pady=(0, 0))
    _hint_label(root, _HINT_KEYS,   row=3, pady=(0, 4))


def _hint_label(root, text, row, pady):
    tk.Label(
        root,
        text=text,
        font=("Courier", 8),
        fg="#888888",
        anchor="w",
        padx=6,
    ).grid(row=row, column=0, sticky="ew", padx=4, pady=pady)


def _build_bottom_pane(root):
    outer = tk.Frame(root, relief="sunken", borderwidth=1)
    outer.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 2))
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)

    canvas = tk.Canvas(outer, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")

    sy = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    sy.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=sy.set)
    g["bottom_canvas"] = canvas

    inner = tk.Frame(canvas)
    g["bottom_inner"] = inner
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

    # Mousewheel scrolling (Windows + Linux)
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))


def _build_bottom_bar(root):
    bar = tk.Frame(root)
    bar.grid(row=5, column=0, sticky="ew")
    bar.columnconfigure(1, weight=1)

    btn = tk.Button(bar, text="Open OUTBOX", command=handle_open_outbox)
    btn.grid(row=0, column=0, padx=(4, 4), pady=2)

    var = tk.StringVar(value="Ready — write a form spec above, then press Ctrl+Enter.")
    g["status_var"] = var
    label = tk.Label(bar, textvariable=var, anchor="w", relief="sunken",
                     padx=4, font=("TkDefaultFont", 9))
    label.grid(row=0, column=1, sticky="ew", pady=2, padx=(0, 4))
    g["status_label"] = label


# ---------------------------------------------------------------------------
# Key binding handlers
# ---------------------------------------------------------------------------

def handle_ctrl_enter(event):
    text = g["top_text"].get("1.0", "end-1c")
    try:
        directives, fields = parse_spec(text)
    except ParseError as e:
        show_status(str(e), error=True)
        return "break"

    g["fields"] = fields
    g["directives"] = directives
    render_form(fields)

    channel = _effective_channel()
    outbox = _effective_outbox()
    show_status(f"Parsed {len(fields)} field(s).  channel={channel!r}  outbox={outbox!r}")
    return "break"


def handle_ctrl_s(event):
    if g["fields"] is None:
        show_status("No form rendered — press Ctrl+Enter first.", error=True)
        return "break"

    signal = _collect_values()
    if signal is None:
        return "break"

    channel = _effective_channel()
    outbox = _effective_outbox()

    try:
        filename = emit_message(signal, channel, outbox)
    except EmitError as e:
        show_status(str(e), error=True)
        return "break"

    show_status(f"Wrote {os.path.join(outbox, filename)}")
    return "break"


def handle_ctrl_l(event):
    _clear_status()
    return "break"


def handle_open_outbox():
    outbox = _effective_outbox()
    outbox_abs = os.path.abspath(outbox)
    if not os.path.isdir(outbox_abs):
        show_status(f"OUTBOX does not exist yet: {outbox_abs}", error=True)
        return
    _open_directory(outbox_abs)


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------

def render_form(fields):
    inner = g["bottom_inner"]

    for widget in inner.winfo_children():
        widget.destroy()
    g["widgets"] = {}
    g["vars"] = {}

    inner.columnconfigure(0, weight=0)
    inner.columnconfigure(1, weight=1)

    first_widget = None

    for row, field in enumerate(fields):
        fid = field["id"]

        lbl = tk.Label(inner, text=fid + ":", font=("Courier", 10), anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=(6, 4), pady=3)

        widget = _make_widget(inner, field)
        # Entry-based and fixed-width widgets use sticky="w" so width= is respected.
        # Multi-line and choice widgets stretch to fill the column.
        if field["type"] in ("text", "json", "choice"):
            sticky = "ew"
        else:
            sticky = "w"
        widget.grid(row=row, column=1, sticky=sticky, padx=(0, 6), pady=3)
        g["widgets"][fid] = widget

        if first_widget is None:
            first_widget = widget

    if first_widget is not None:
        first_widget.focus_set()


def _make_widget(parent, field):
    ftype = field["type"]

    if ftype == "str":
        return tk.Entry(parent, width=field["width"], font=("Courier", 10))

    if ftype == "text":
        return tk.Text(parent, width=field["width"], height=field["height"],
                       font=("Courier", 10), wrap="none")

    if ftype == "choice":
        items = field["items"]
        w = ttk.Combobox(parent, values=items, state="readonly", font=("Courier", 10))
        w.set(items[0])
        return w

    if ftype == "bool":
        var = tk.BooleanVar(value=False)
        g["vars"][field["id"]] = var
        return tk.Checkbutton(parent, variable=var)

    if ftype == "int":
        vcmd = (parent.register(_validate_int_keypress), '%P')
        return tk.Entry(parent, width=field["width"], font=("Courier", 10),
                        validate="key", validatecommand=vcmd)

    if ftype == "float":
        return tk.Entry(parent, width=field["width"], font=("Courier", 10))

    if ftype == "json":
        return tk.Text(parent, width=field["width"], height=field["height"],
                       font=("Courier", 10), wrap="none")

    if ftype == "date":
        w = tk.Entry(parent, width=10, font=("Courier", 10))
        w.insert(0, datetime.date.today().isoformat())
        return w

    if ftype == "time":
        w = tk.Entry(parent, width=8, font=("Courier", 10))
        w.insert(0, datetime.datetime.now().strftime("%H:%M:%S"))
        return w

    if ftype == "fixed":
        var = tk.StringVar(value=field["value"])
        return tk.Entry(parent, textvariable=var, state="readonly",
                        font=("Courier", 10), fg="#555555",
                        readonlybackground="#f0f0f0")

    raise RuntimeError(f"Unknown field type: {ftype!r}")


def _validate_int_keypress(new_value):
    """Allow only characters that can appear in a base-10 integer."""
    if new_value in ('', '-'):
        return True
    try:
        int(new_value)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Value collection and validation
# ---------------------------------------------------------------------------

def _collect_values():
    """Collect and validate all widget values.

    Returns a signal dict on success, or None if any field fails validation
    (the error is shown in the status bar and the offending widget focused).
    """
    signal = {}

    for field in g["fields"]:
        fid = field["id"]
        ftype = field["type"]
        widget = g["widgets"][fid]
        raw = _read_widget(fid, ftype)

        if ftype == "bool":
            signal[fid] = raw

        elif ftype == "int":
            try:
                signal[fid] = int(raw.strip())
            except ValueError:
                widget.focus_set()
                show_status(f"'{fid}': must be an integer", error=True)
                return None

        elif ftype == "float":
            try:
                val = float(raw.strip())
            except ValueError:
                widget.focus_set()
                show_status(f"'{fid}': must be a number", error=True)
                return None
            if not math.isfinite(val):
                widget.focus_set()
                show_status(f"'{fid}': NaN and Infinity are not allowed", error=True)
                return None
            signal[fid] = val

        elif ftype == "json":
            try:
                signal[fid] = json.loads(raw)
            except json.JSONDecodeError as e:
                widget.focus_set()
                show_status(f"'{fid}': invalid JSON — {e}", error=True)
                return None

        elif ftype == "date":
            try:
                datetime.date.fromisoformat(raw.strip())
            except ValueError:
                widget.focus_set()
                show_status(f"'{fid}': must be a date in yyyy-mm-dd format", error=True)
                return None
            signal[fid] = raw.strip()

        elif ftype == "time":
            try:
                datetime.time.fromisoformat(raw.strip())
            except ValueError:
                widget.focus_set()
                show_status(f"'{fid}': must be a time in hh:mm:ss format", error=True)
                return None
            signal[fid] = raw.strip()

        elif ftype == "fixed":
            signal[fid] = field["value"]

        else:  # str, text, choice
            signal[fid] = raw

    return signal


def _read_widget(fid, ftype):
    """Read the raw value from a widget."""
    if ftype == "bool":
        return g["vars"][fid].get()
    if ftype in ("text", "json"):
        return g["widgets"][fid].get("1.0", "end-1c")
    if ftype == "fixed":
        return None  # handled directly from field["value"] in _collect_values
    return g["widgets"][fid].get()


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _effective_channel():
    """Resolve channel: CLI/env config > DSL directive > default."""
    return g["config"].get("channel") or g["directives"].get("channel") or "output"


def _effective_outbox():
    """Resolve OUTBOX path: CLI/env config > DSL directive > default."""
    return g["config"].get("outbox") or g["directives"].get("outbox") or "OUTBOX"


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _open_directory(path):
    """Open path in the OS file manager."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

def show_status(msg, error=False):
    if g["status_clear_id"] is not None:
        g["root"].after_cancel(g["status_clear_id"])
        g["status_clear_id"] = None

    g["status_var"].set(msg)
    g["status_label"].configure(fg="red" if error else "black")

    if not error:
        g["status_clear_id"] = g["root"].after(_STATUS_SUCCESS_MS, _clear_status)


def _clear_status():
    g["status_var"].set("")
    g["status_label"].configure(fg="black")
    g["status_clear_id"] = None


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _load_spec_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        g["top_text"].insert("1.0", content)
    except OSError as e:
        show_status(f"Could not load spec file: {e}", error=True)
