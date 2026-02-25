"""FileTalk Form Producer — Tkinter application (tabbed)."""

import datetime
import json
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from .parser import ParseError, parse_spec
from .emitter import EmitError, build_message, emit_message
from .inbox import scan_inbox, is_text_message


# One canonical global bundle.
g = {}

_STATUS_SUCCESS_MS = 4000
_INBOX_POLL_MS = 1000

_HINT_SYNTAX = '<identifier> -- <type>   # channel <ch>   # outbox <path>   # title <title>'
_HINT_TYPES  = 'str<w>  text<w,h>  choice<a,b,...>  bool  int<w>  float<w>  json<w,h>  date  time  "fixed value"'
_HINT_KEYS   = 'Ctrl+Enter: render   Ctrl+E: emit   Ctrl+J: copy JSON   Ctrl+S: save   Ctrl+O: open   Ctrl+N: new tab   Ctrl+W: close tab   Esc: focus tab bar   Ctrl+←/→: prev/next tab   Ctrl+↑/↓: DSL/form'


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(config):
    """Build the tabbed UI and enter the main loop.

    config keys:
        channel     — configured channel (str)
        outbox      — configured OUTBOX path (Path or None)
        inbox       — configured INBOX path (Path or None)
        project_dir — .form-producer/ directory (Path), used as file dialog default
    """
    g["config"] = config
    g["tabs"] = []
    g["untitled_count"] = 0
    g["status_clear_id"] = None
    g["project_dir"] = config.get("project_dir")  # Path or None

    _setup_ui()
    _new_tab()  # Start with one empty tab
    _start_inbox_polling()
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
    root.rowconfigure(0, weight=0)   # hint: syntax
    root.rowconfigure(1, weight=0)   # hint: types
    root.rowconfigure(2, weight=0)   # hint: keybindings
    root.rowconfigure(3, weight=1)   # notebook
    root.rowconfigure(4, weight=0)   # bottom bar

    _build_menubar(root)
    _build_help_hints(root)
    _build_notebook(root)
    _build_bottom_bar(root)

    root.bind("<Control-Return>", handle_ctrl_enter)
    root.bind("<Control-e>", lambda e: handle_emit())
    root.bind("<Control-j>", lambda e: handle_copy_json())
    root.bind("<Control-s>", lambda e: handle_file_save())
    root.bind("<Control-o>", lambda e: handle_file_open())
    root.bind("<Control-n>", lambda e: (_new_tab(), "break")[1])
    root.bind("<Control-w>", lambda e: (handle_tab_close(), "break")[1])
    root.bind("<Control-Right>", handle_next_tab)
    root.bind("<Control-Left>",  handle_prev_tab)
    root.bind("<Control-Down>",  handle_focus_form)
    root.bind("<Control-Up>",    handle_focus_dsl)
    root.bind("<Escape>",        handle_escape)
    root.bind("<Control-l>", handle_ctrl_l)


def _build_menubar(root):
    menubar = tk.Menu(root)

    # ── File ─────────────────────────────────────────────────────────────
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(
        label="Open Description", underline=0, accelerator="Ctrl+O",
        command=handle_file_open,
    )
    file_menu.add_command(
        label="Save Description", underline=0, accelerator="Ctrl+S",
        command=handle_file_save,
    )
    file_menu.add_separator()
    file_menu.add_command(label="Exit", underline=1, command=handle_exit)
    menubar.add_cascade(label="File", menu=file_menu, underline=0)

    # ── Tabs ─────────────────────────────────────────────────────────────
    tabs_menu = tk.Menu(menubar, tearoff=0)
    tabs_menu.add_command(
        label="New Tab",   underline=0, accelerator="Ctrl+N",
        command=lambda: _new_tab(),
    )
    tabs_menu.add_command(
        label="Close Tab", underline=0, accelerator="Ctrl+W",
        command=handle_tab_close,
    )
    tabs_menu.add_separator()
    tabs_menu.add_command(
        label="Next Tab",          accelerator="Ctrl+→",
        command=lambda: handle_next_tab(None),
    )
    tabs_menu.add_command(
        label="Previous Tab",      accelerator="Ctrl+←",
        command=lambda: handle_prev_tab(None),
    )
    tabs_menu.add_command(
        label="Focus Form",        accelerator="Ctrl+↓",
        command=lambda: handle_focus_form(None),
    )
    tabs_menu.add_command(
        label="Focus Description", accelerator="Ctrl+↑",
        command=lambda: handle_focus_dsl(None),
    )
    menubar.add_cascade(label="Tabs", menu=tabs_menu, underline=0)

    # ── Patchboard ───────────────────────────────────────────────────────
    pb_menu = tk.Menu(menubar, tearoff=0)
    pb_menu.add_command(
        label=f"Emit JSON to: {_effective_channel()}",
        underline=0, accelerator="Ctrl+E",
        command=handle_emit,
    )
    pb_menu.add_command(
        label="Emit component card to: card",
        command=handle_emit_card,
    )
    pb_menu.add_separator()
    pb_menu.add_command(
        label="Copy JSON to clipboard",
        underline=0, accelerator="Ctrl+J",
        command=handle_copy_json,
    )
    pb_menu.add_command(
        label="Copy component card to clipboard",
        command=handle_copy_card,
    )
    pb_menu.add_separator()
    pb_menu.add_command(label="Open Inbox",  underline=5, command=handle_open_inbox)
    pb_menu.add_command(label="Open Outbox", underline=5, command=handle_open_outbox)
    menubar.add_cascade(label="Patchboard", menu=pb_menu, underline=0)

    g["patchboard_menu"] = pb_menu
    root.config(menu=menubar)


def _build_help_hints(root):
    _hint_label(root, _HINT_SYNTAX, row=0, pady=(4, 0))
    _hint_label(root, _HINT_TYPES,  row=1, pady=(0, 0))
    _hint_label(root, _HINT_KEYS,   row=2, pady=(0, 4))


def _hint_label(root, text, row, pady):
    tk.Label(
        root,
        text=text,
        font=("Courier", 8),
        fg="#888888",
        anchor="w",
        padx=6,
    ).grid(row=row, column=0, sticky="ew", padx=4, pady=pady)


def _build_notebook(root):
    nb = ttk.Notebook(root)
    nb.grid(row=3, column=0, sticky="nsew", padx=4, pady=0)
    nb.bind("<<NotebookTabChanged>>", _on_tab_changed)
    g["notebook"] = nb


def _build_bottom_bar(root):
    bar = tk.Frame(root)
    bar.grid(row=4, column=0, sticky="ew")
    bar.columnconfigure(0, weight=1)

    var = tk.StringVar(value="Ready — write a form spec above, then press Ctrl+Enter.")
    g["status_var"] = var
    label = tk.Label(bar, textvariable=var, anchor="w", relief="sunken",
                     padx=4, font=("TkDefaultFont", 9))
    label.grid(row=0, column=0, sticky="ew", pady=2, padx=4)
    g["status_label"] = label


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

def _current_tab():
    idx = g["notebook"].index("current")
    return g["tabs"][idx]


def _new_tab(text="", filename=None):
    """Create a new tab with a DSL editor and form canvas. Returns the tab dict."""
    g["untitled_count"] += 1
    tab = {
        "number":     g["untitled_count"],
        "filename":   filename,
        "directives": {},
        "fields":     None,
        "widgets":    {},
        "vars":       {},
        "text_widget": None,
        "canvas":     None,
        "inner":      None,
        "frame":      None,
    }

    frame = tk.Frame(g["notebook"])
    tab["frame"] = frame
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)

    # ── Top half: DSL editor ──────────────────────────────────────────────
    top_frame = tk.Frame(frame)
    top_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 2))
    top_frame.columnconfigure(0, weight=1)
    top_frame.rowconfigure(0, weight=1)

    text_widget = tk.Text(top_frame, font=("Courier", 10), wrap="none", undo=True)
    text_widget.grid(row=0, column=0, sticky="nsew")
    if text:
        text_widget.insert("1.0", text)

    sy = tk.Scrollbar(top_frame, orient="vertical", command=text_widget.yview)
    sy.grid(row=0, column=1, sticky="ns")
    sx = tk.Scrollbar(top_frame, orient="horizontal", command=text_widget.xview)
    sx.grid(row=1, column=0, sticky="ew")
    text_widget.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tab["text_widget"] = text_widget

    # ── Bottom half: scrollable form canvas ───────────────────────────────
    outer = tk.Frame(frame, relief="sunken", borderwidth=1)
    outer.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 2))
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)

    canvas = tk.Canvas(outer, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")

    sy2 = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    sy2.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=sy2.set)
    tab["canvas"] = canvas

    inner = tk.Frame(canvas)
    tab["inner"] = inner
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    canvas.bind("<Button-4>",   lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>",   lambda e: canvas.yview_scroll(1, "units"))

    # ── Register and select ───────────────────────────────────────────────
    g["tabs"].append(tab)
    g["notebook"].add(frame, text=_tab_label(tab))
    g["notebook"].select(frame)

    return tab


def _tab_label(tab):
    title = tab["directives"].get("title")
    if title:
        return title
    if tab["filename"]:
        return os.path.basename(tab["filename"])
    return f"Untitled #{tab['number']}"


def _update_tab_label(tab):
    idx = g["tabs"].index(tab)
    g["notebook"].tab(idx, text=_tab_label(tab))


def _on_tab_changed(event):
    """Auto-render the form whenever a tab is selected."""
    try:
        tab = _current_tab()
    except (IndexError, tk.TclError):
        return
    _auto_render_tab(tab)


def _auto_render_tab(tab):
    """Parse the tab's DSL and render the form. Silent on parse failure."""
    text = tab["text_widget"].get("1.0", "end-1c")
    try:
        directives, fields = parse_spec(text)
    except ParseError:
        return
    tab["fields"] = fields
    tab["directives"] = directives
    _update_tab_label(tab)
    _render_form_in_tab(tab, fields, focus=False)
    _update_emit_label()


def _update_emit_label():
    """Refresh the 'Emit JSON to: <channel>' menu item to reflect the current tab."""
    if "patchboard_menu" not in g:
        return
    tab = _safe_current_tab()
    channel = _effective_channel(tab)
    g["patchboard_menu"].entryconfig(0, label=f"Emit JSON to: {channel}")


def _build_card():
    """Build a Patchboard component ID card dict from the current config.

    channels.out is assembled by scanning all open tabs: each tab contributes
    its effective output channel (# channel: directive, else configured default).
    "card" is always included since the component can emit on that channel too.
    """
    inbox           = g["config"].get("inbox")  or "INBOX"
    outbox          = g["config"].get("outbox") or "OUTBOX"
    default_channel = g["config"].get("channel") or "output"

    out_channels = []
    for tab in g.get("tabs") or []:
        ch = tab["directives"].get("channel") or default_channel
        if ch not in out_channels:
            out_channels.append(ch)
    if not out_channels:
        out_channels.append(default_channel)
    if "card" not in out_channels:
        out_channels.append("card")

    return {
        "schema_version": 1,
        "title": "FileTalk Form Producer",
        "inbox":  os.path.abspath(str(inbox)),
        "outbox": os.path.abspath(str(outbox)),
        "channels": {
            "in":  ["text"],
            "out": out_channels,
        },
    }


# ---------------------------------------------------------------------------
# Key binding handlers
# ---------------------------------------------------------------------------

def handle_ctrl_enter(event):
    tab = _current_tab()
    text = tab["text_widget"].get("1.0", "end-1c")
    try:
        directives, fields = parse_spec(text)
    except ParseError as e:
        show_status(str(e), error=True)
        return "break"

    tab["fields"] = fields
    tab["directives"] = directives
    _update_tab_label(tab)
    _render_form_in_tab(tab, fields)
    _update_emit_label()

    channel = _effective_channel(tab)
    outbox  = _effective_outbox(tab)
    show_status(f"Parsed {len(fields)} field(s).  channel={channel!r}  outbox={str(outbox)!r}")
    return "break"


def handle_emit():
    tab = _current_tab()
    if tab["fields"] is None:
        show_status("No form rendered — press Ctrl+Enter first.", error=True)
        return

    signal = _collect_values_from_tab(tab)
    if signal is None:
        return

    channel = _effective_channel(tab)
    outbox  = str(_effective_outbox(tab))

    try:
        filename = emit_message(signal, channel, outbox)
    except EmitError as e:
        show_status(str(e), error=True)
        return

    show_status(f"Wrote {os.path.join(outbox, filename)}")


def handle_ctrl_l(event):
    _clear_status()
    return "break"


def handle_escape(event):
    """Move focus to the notebook tab bar, freeing it from any text widget."""
    g["notebook"].focus_set()
    return "break"


def handle_exit():
    g["root"].destroy()


def handle_copy_json():
    tab = _current_tab()
    if tab["fields"] is None:
        show_status("No form rendered — press Ctrl+Enter first.", error=True)
        return

    signal = _collect_values_from_tab(tab)
    if signal is None:
        return

    json_str = json.dumps(signal, ensure_ascii=False, indent=2)
    g["root"].clipboard_clear()
    g["root"].clipboard_append(json_str)
    show_status("JSON copied to clipboard.")


def handle_file_open():
    path = filedialog.askopenfilename(
        title="Open spec file",
        initialdir=_file_dialog_initialdir(),
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError as e:
        show_status(f"Could not open file: {e}", error=True)
        return
    tab = _new_tab(text=content, filename=path)
    _auto_render_tab(tab)
    show_status(f"Opened {path}")


def handle_file_save():
    tab = _current_tab()
    if tab["filename"]:
        _write_spec_file(tab, tab["filename"])
    else:
        path = filedialog.asksaveasfilename(
            title="Save spec file",
            initialdir=_file_dialog_initialdir(),
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        tab["filename"] = path
        _update_tab_label(tab)
        _write_spec_file(tab, path)


def handle_tab_close():
    if len(g["tabs"]) <= 1:
        show_status("Cannot close the last tab.", error=True)
        return
    tab = _current_tab()
    idx = g["tabs"].index(tab)
    g["notebook"].forget(tab["frame"])
    g["tabs"].pop(idx)


def handle_next_tab(event):
    # Don't steal Ctrl+Right from text/entry widgets where it moves the cursor.
    if isinstance(g["root"].focus_get(), (tk.Text, tk.Entry, ttk.Combobox)):
        return
    if len(g["tabs"]) > 1:
        idx = g["notebook"].index("current")
        g["notebook"].select((idx + 1) % len(g["tabs"]))
    return "break"


def handle_prev_tab(event):
    # Don't steal Ctrl+Left from text/entry widgets where it moves the cursor.
    if isinstance(g["root"].focus_get(), (tk.Text, tk.Entry, ttk.Combobox)):
        return
    if len(g["tabs"]) > 1:
        idx = g["notebook"].index("current")
        g["notebook"].select((idx - 1) % len(g["tabs"]))
    return "break"


def handle_focus_form(event):
    # Don't steal Ctrl+Down from Text widgets where it moves the cursor.
    if isinstance(g["root"].focus_get(), tk.Text):
        return
    tab = _safe_current_tab()
    if tab:
        widget = _first_editable_widget(tab)
        if widget:
            widget.focus_set()
    return "break"


def handle_focus_dsl(event):
    # Don't steal Ctrl+Up from Text widgets where it moves the cursor.
    if isinstance(g["root"].focus_get(), tk.Text):
        return
    g["notebook"].focus_set()
    return "break"


def handle_emit_card():
    """Emit the component ID card as a Patchboard message to the OUTBOX."""
    card = _build_card()
    tab = _safe_current_tab()
    outbox = str(_effective_outbox(tab))
    try:
        filename = emit_message(card, "card", outbox)
    except EmitError as e:
        show_status(str(e), error=True)
        return
    show_status(f"Card emitted to {os.path.join(outbox, filename)}")


def handle_copy_card():
    """Copy the component ID card JSON to the clipboard."""
    card = _build_card()
    json_str = json.dumps(card, indent=2)
    g["root"].clipboard_clear()
    g["root"].clipboard_append(json_str)
    show_status("Component card copied to clipboard.")


def handle_open_inbox():
    inbox_abs = os.path.abspath(str(_effective_inbox()))
    if not os.path.isdir(inbox_abs):
        try:
            os.makedirs(inbox_abs)
        except OSError as e:
            show_status(f"Could not create Inbox: {e}", error=True)
            return
    _open_directory(inbox_abs)


def handle_open_outbox():
    tab = _safe_current_tab()
    outbox_abs = os.path.abspath(str(_effective_outbox(tab)))
    if not os.path.isdir(outbox_abs):
        try:
            os.makedirs(outbox_abs)
        except OSError as e:
            show_status(f"Could not create Outbox: {e}", error=True)
            return
    _open_directory(outbox_abs)


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------

def _first_editable_widget(tab):
    """Return the first non-fixed widget in the rendered form, or None."""
    for field in (tab["fields"] or []):
        if field["type"] != "fixed":
            widget = tab["widgets"].get(field["id"])
            if widget:
                return widget
    return None


def _render_form_in_tab(tab, fields, focus=True):
    inner = tab["inner"]

    for widget in inner.winfo_children():
        widget.destroy()
    tab["widgets"] = {}
    tab["vars"] = {}

    inner.columnconfigure(0, weight=0)
    inner.columnconfigure(1, weight=1)

    first_widget = None

    for row, field in enumerate(fields):
        fid = field["id"]

        lbl = tk.Label(inner, text=fid + ":", font=("Courier", 10), anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=(6, 4), pady=3)

        widget = _make_widget(inner, field, tab)
        # Entry-based widgets use sticky="w" so width= is respected.
        # Multi-line and choice widgets stretch full width.
        if field["type"] in ("text", "json", "choice"):
            sticky = "ew"
        else:
            sticky = "w"
        widget.grid(row=row, column=1, sticky=sticky, padx=(0, 6), pady=3)
        tab["widgets"][fid] = widget

        if first_widget is None and field["type"] != "fixed":
            first_widget = widget

    if first_widget is not None and focus:
        first_widget.focus_set()


def _make_widget(parent, field, tab):
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
        tab["vars"][field["id"]] = var
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

def _collect_values_from_tab(tab):
    """Collect and validate all widget values for a tab.

    Returns a signal dict on success, or None if validation fails
    (the error is shown in the status bar and the offending widget focused).
    """
    signal = {}

    for field in tab["fields"]:
        fid   = field["id"]
        ftype = field["type"]
        widget = tab["widgets"][fid]
        raw = _read_widget_from_tab(tab, fid, ftype)

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


def _read_widget_from_tab(tab, fid, ftype):
    """Read the raw value from a widget."""
    if ftype == "bool":
        return tab["vars"][fid].get()
    if ftype in ("text", "json"):
        return tab["widgets"][fid].get("1.0", "end-1c")
    if ftype == "fixed":
        return None  # handled directly from field["value"]
    return tab["widgets"][fid].get()


# ---------------------------------------------------------------------------
# INBOX polling
# ---------------------------------------------------------------------------

def _start_inbox_polling():
    g["root"].after(_INBOX_POLL_MS, _poll_inbox)


def _poll_inbox():
    inbox_path = str(_effective_inbox())
    for filepath, message in scan_inbox(inbox_path):
        if is_text_message(message):
            _handle_inbox_text(message['signal'])
        # Delete every successfully parsed message regardless of channel.
        try:
            os.remove(filepath)
        except OSError:
            pass
    g["root"].after(_INBOX_POLL_MS, _poll_inbox)


def _handle_inbox_text(text):
    """Load text from INBOX into a new tab and auto-render."""
    tab = _new_tab(text=text)
    _auto_render_tab(tab)
    count = len(tab["fields"]) if tab["fields"] is not None else 0
    show_status(f"INBOX: received text message, rendered {count} field(s).")


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _effective_channel(tab=None):
    """DSL directive > configured channel > default 'output'."""
    if tab and tab["directives"].get("channel"):
        return tab["directives"]["channel"]
    return g["config"].get("channel") or "output"


def _effective_outbox(tab=None):
    """DSL directive > configured outbox > default 'OUTBOX'."""
    if tab and tab["directives"].get("outbox"):
        return tab["directives"]["outbox"]
    outbox = g["config"].get("outbox")
    return outbox if outbox is not None else "OUTBOX"


def _effective_inbox():
    """Configured inbox > default 'INBOX'."""
    inbox = g["config"].get("inbox")
    return inbox if inbox is not None else "INBOX"


def _safe_current_tab():
    """Return current tab, or None if the notebook has no tabs."""
    try:
        return _current_tab()
    except (IndexError, tk.TclError):
        return None


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _load_file_into_tab(tab, path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError as e:
        show_status(f"Could not open file: {e}", error=True)
        return
    tab["text_widget"].delete("1.0", "end")
    tab["text_widget"].insert("1.0", content)


def _write_spec_file(tab, path):
    content = tab["text_widget"].get("1.0", "end-1c")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except OSError as e:
        show_status(f"Could not save file: {e}", error=True)
        return
    show_status(f"Saved {path}")


def _file_dialog_initialdir():
    project_dir = g.get("project_dir")
    if project_dir is not None:
        try:
            if project_dir.is_dir():
                return str(project_dir)
        except (OSError, AttributeError):
            pass
    return None


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
