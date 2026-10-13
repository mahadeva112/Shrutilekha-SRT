"""Cross-platform dialog helper called by audio_to_srt.py on Windows.

Usage:
  python dialog.py alert       <title> <message>
  python dialog.py alert_error <title> <message>
  python dialog.py pick        <title> <prompt> <item1> [item2 ...]
  python dialog.py input       <title> <prompt> <default>
  python dialog.py notify      <title> <message>

Exit code: 0 always (errors are printed to stderr).
For 'pick' and 'input', the chosen/entered value is printed to stdout.
"""

import sys
import tkinter as tk
from tkinter import ttk

# ── Dark palette (mirrors loader.pyw so dialogs match the main UI) ──────────
BG_OUTER     = "#0b0d10"   # window backdrop / 1px border
BG           = "#14171c"   # card interior
BG_INPUT     = "#0f1217"   # text inputs (darker than card)
BG_HOVER     = "#1b2030"
BORDER       = "#1f242d"
BORDER_CARD  = "#23272f"
FG           = "#e6e9ef"
FG_DIM       = "#9aa1b1"
FG_MUTE      = "#7b8190"
FG_LABEL     = "#8a93a4"
ACCENT       = "#eed185"
ACCENT_DARK  = "#c5ab63"
ACCENT_HOVER = "#f0d99a"
CLOSE_HOVER  = "#c42b1c"


def _dark_window(title):
    """Create a frameless dark-themed Tk window matching the main UI.

    Returns (root, body) where `body` is the padded card interior to fill
    with content. A custom title bar (title + close button) is already added
    and made draggable along with the card.
    """
    from dpi import enable, attach
    enable()
    root = tk.Tk()
    attach(root)
    root.title(title)
    root.resizable(False, False)
    root.configure(bg=BG_OUTER)
    try:
        root.overrideredirect(True)
    except Exception:
        pass

    # 1px outer border via the outer bg showing through.
    card = tk.Frame(root, bg=BG, bd=0, highlightthickness=0)
    card.pack(fill="both", expand=True, padx=1, pady=1)

    # ── Custom title bar ────────────────────────────────────────────────
    bar = tk.Frame(card, bg=BG, bd=0, highlightthickness=0)
    bar.pack(fill="x")
    title_lbl = tk.Label(bar, text=title, bg=BG, fg=FG_DIM,
                         font=("Segoe UI", 9), anchor="w")
    title_lbl.pack(side="left", padx=(14, 0), pady=8)

    close = tk.Canvas(bar, width=44, height=30, bg=BG,
                      highlightthickness=0, bd=0, cursor="hand2")
    close.pack(side="right")

    def _draw_close(hover=False):
        close.delete("all")
        bg = CLOSE_HOVER if hover else BG
        close.create_rectangle(0, 0, 44, 30, fill=bg, outline=bg)
        fg = "#ffffff" if hover else FG_DIM
        from ui_icons import photo
        close._image=photo(close,'close',16,fg)
        close.create_image(22,15,image=close._image)

    _draw_close()
    close.bind('<Configure>',lambda e:_draw_close())
    close.bind("<Enter>", lambda e: _draw_close(True))
    close.bind("<Leave>", lambda e: _draw_close(False))
    close.bind("<Button-1>", lambda e: root.destroy())

    # ── Padded body for content ─────────────────────────────────────────
    body = tk.Frame(card, bg=BG, bd=0, highlightthickness=0)
    body.pack(fill="both", expand=True, padx=18, pady=(2, 16))

    return root, body, (bar, title_lbl)


def _accent_button(parent, text, command, width=10, primary=True):
    from settings_ui import RoundedAction
    colors=dict(accent=ACCENT,text=FG,muted=FG_DIM,font='Segoe UI',button_size=-14,
                button_fill='#2b3039',button_hover='#373e49',button_border='#414957',radius=9)
    return RoundedAction(parent,text,command,colors,primary=primary,width=width*9+24,height=38)


def _make_draggable(win):
    """Allow dragging the window by clicking anywhere on its background.

    Bindings on the toplevel alone never fire, because the frame and labels
    cover the whole surface and consume the click. So we recursively bind the
    handlers to every non-interactive widget (frames + labels), leaving the
    interactive widgets (buttons, entries, comboboxes, checkbuttons) untouched.
    """
    state = {}

    def on_press(e):
        state["x"] = e.x_root - win.winfo_x()
        state["y"] = e.y_root - win.winfo_y()

    def on_drag(e):
        if "x" in state:
            win.geometry(f"+{e.x_root - state['x']}+{e.y_root - state['y']}")

    draggable = ("TFrame", "Frame", "TLabel", "Label", "Toplevel", "Tk")

    def bind_recursive(widget):
        if widget.winfo_class() in draggable:
            widget.bind("<ButtonPress-1>", on_press, add="+")
            widget.bind("<B1-Motion>", on_drag, add="+")
        for child in widget.winfo_children():
            bind_recursive(child)

    bind_recursive(win)


def _steal_focus(win):
    """Bypass Windows foreground-lock so we can appear over DaVinci Resolve."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.SystemParametersInfoW(0x2001, 0, 0, 2)   # SPI_SETFOREGROUNDLOCKTIMEOUT
        hwnd = int(win.winfo_id())
        u32.ShowWindow(hwnd, 9)            # SW_RESTORE
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
        u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0013)  # HWND_TOPMOST|NOMOVE|NOSIZE|NOACTIVATE
    except Exception:
        pass


def center(win):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    # Frameless (overrideredirect) windows often report 1×1 until mapped;
    # fall back to the requested (layout) size so centering still works.
    if w <= 1:
        w = win.winfo_reqwidth()
    if h <= 1:
        h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    # Include the size in the geometry string: a frameless window that has
    # no explicit size yet ignores a position-only ("+x+y") request and stays
    # pinned at 0,0, so we pass the full "WxH+X+Y" form.
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    win.attributes("-topmost", True)
    win.lift()
    win.after(50, lambda: _steal_focus(win))
    if win.overrideredirect():
        win.after(60, lambda: _round_dialog(win))


def _round_dialog(win):
    """Apply a rounded region to the frameless dialog at native DPI."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        from dpi import pixels
        u=ctypes.windll.user32;g=ctypes.windll.gdi32
        u.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        u.GetAncestor.restype=ctypes.c_void_p
        hwnd=u.GetAncestor(win.winfo_id(),2)
        g.CreateRoundRectRgn.argtypes=[ctypes.c_int]*6;g.CreateRoundRectRgn.restype=ctypes.c_void_p
        u.SetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_bool]
        g.DeleteObject.argtypes=[ctypes.c_void_p]
        region=g.CreateRoundRectRgn(0,0,pixels(win,win.winfo_width())+1,
                                   pixels(win,win.winfo_height())+1,pixels(win,28),pixels(win,28))
        if not u.SetWindowRgn(hwnd,region,True):g.DeleteObject(region)
    except (OSError,tk.TclError,AttributeError):
        pass


def build_alert_content(body, title, message, error=False):
    """Shared content builder, also usable in an isolated visual preview."""
    from ui_icons import photo
    header=tk.Frame(body,bg=BG)
    header.pack(fill='x',pady=(8,18))
    icon=tk.Canvas(header,width=48,height=48,bg=BG,highlightthickness=0)
    icon.pack(side='left',padx=(0,14))
    from settings_ui import rounded_rect
    def draw(event=None):
        icon.delete('all')
        rounded_rect(icon,1,1,47,47,14,fill='#382d25' if error else '#343022',outline='#594731')
        icon._image=photo(icon,'warning' if error else 'shield',24,'#eac987')
        icon.create_image(24,24,image=icon._image)
    icon.bind('<Configure>',draw);draw()
    headings=tk.Frame(header,bg=BG);headings.pack(side='left',fill='x',expand=True)
    tk.Label(headings,text='CAPTION STUDIO',font=('Segoe UI',-11,'bold'),fg='#b7a273',bg=BG,
             anchor='w').pack(fill='x')
    tk.Label(headings,text=title,font=('Segoe UI',-20,'bold'),fg=FG,bg=BG,
             anchor='w',wraplength=380,justify='left').pack(fill='x',pady=(4,0))
    tk.Label(body,text=message,bg=BG,fg='#bec4cf',wraplength=450,justify='left',
             font=('Segoe UI',-14)).pack(anchor='w',fill='x',pady=(0,20))
    tk.Frame(body,bg='#2c323c',height=1).pack(fill='x',pady=(0,14))


def alert(title, message, accent=ACCENT):
    root, body, _ = _dark_window(title)
    build_alert_content(body,title,message,error=accent!=ACCENT)
    btn_frm = tk.Frame(body, bg=BG)
    btn_frm.pack(anchor="e")
    btn = _accent_button(btn_frm, "OK", root.destroy, width=8)
    btn.pack()
    root.bind("<Return>", lambda e: root.destroy())
    root.bind("<Escape>", lambda e: root.destroy())
    center(root)
    _make_draggable(root)
    root.lift()
    root.attributes("-topmost", True)
    root.mainloop()


def alert_error(title, message):
    alert(title, message, accent=CLOSE_HOVER)


def pick(title, prompt, items):
    result = {"value": None}

    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=prompt).pack(anchor="w", pady=(0, 6))

    combo_var = tk.StringVar(value=items[0] if items else "")
    combo = ttk.Combobox(frm, textvariable=combo_var, values=items,
                         state="readonly", width=45)
    combo.pack(pady=(0, 16))

    btn_frm = ttk.Frame(frm)
    btn_frm.pack(anchor="e")

    def on_ok():
        result["value"] = combo_var.get()
        root.destroy()

    ttk.Button(btn_frm, text="Cancel", width=8, command=root.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(btn_frm, text="OK",     width=8, command=on_ok).pack(side="left")

    center(root)
    _make_draggable(root)
    root.lift()
    root.attributes("-topmost", True)
    root.mainloop()

    if result["value"]:
        print(result["value"])


def input_dialog(title, prompt, default="", checkbox_label="", checkbox_default="0"):
    result = {"value": None, "checkbox": None}

    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=prompt, wraplength=380, justify="left").pack(anchor="w", pady=(0, 6))

    entry_var = tk.StringVar(value=default)
    entry = ttk.Entry(frm, textvariable=entry_var, width=40)
    entry.pack(pady=(0, 16))
    entry.focus()

    if checkbox_label:
        checkbox_var = tk.IntVar(value=int(checkbox_default))
        ttk.Checkbutton(frm, text=checkbox_label, variable=checkbox_var).pack(anchor="w", pady=(0, 16))
    else:
        checkbox_var = None

    btn_frm = ttk.Frame(frm)
    btn_frm.pack(anchor="e")

    def on_ok():
        result["value"] = entry_var.get()
        if checkbox_var is not None:
            result["checkbox"] = checkbox_var.get()
        root.destroy()

    root.bind("<Return>", lambda e: on_ok())

    ttk.Button(btn_frm, text="Cancel",             width=8,  command=root.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(btn_frm, text="Generate Subtitles", width=18, command=on_ok).pack(side="left")

    center(root)
    _make_draggable(root)
    root.lift()
    root.attributes("-topmost", True)
    root.mainloop()

    if result["value"] is not None:
        if result["checkbox"] is not None:
            print(f"{result['value']}|{result['checkbox']}")
        else:
            print(result["value"])


def pick_input(title, prompt_pick, items, prompt_input, default="",
               checkbox_label="", checkbox_default="0"):
    """Combined dialog: dropdown + entry + optional checkbox in one window.

    Output (stdout, tab-separated): <chosen>\\t<entry>\\t<checkbox>
    """
    result = {"chosen": None, "value": None, "checkbox": None}

    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    # ── Track picker ──────────────────────────────────────────────────────
    ttk.Label(frm, text=prompt_pick).pack(anchor="w", pady=(0, 6))
    combo_var = tk.StringVar(value=items[0] if items else "")
    combo = ttk.Combobox(frm, textvariable=combo_var, values=items,
                         state="readonly", width=45)
    combo.pack(fill="x", pady=(0, 14))

    # ── Settings entry ────────────────────────────────────────────────────
    ttk.Label(frm, text=prompt_input, wraplength=380, justify="left").pack(anchor="w", pady=(0, 6))
    entry_var = tk.StringVar(value=default)
    entry = ttk.Entry(frm, textvariable=entry_var, width=40)
    entry.pack(fill="x", pady=(0, 14))

    # ── Optional checkbox ─────────────────────────────────────────────────
    if checkbox_label:
        checkbox_var = tk.IntVar(value=int(checkbox_default))
        ttk.Checkbutton(frm, text=checkbox_label, variable=checkbox_var).pack(anchor="w", pady=(0, 14))
    else:
        checkbox_var = None

    # ── Buttons ───────────────────────────────────────────────────────────
    btn_frm = ttk.Frame(frm)
    btn_frm.pack(anchor="e")

    def on_ok():
        result["chosen"] = combo_var.get()
        result["value"] = entry_var.get()
        if checkbox_var is not None:
            result["checkbox"] = checkbox_var.get()
        root.destroy()

    root.bind("<Return>", lambda e: on_ok())

    ttk.Button(btn_frm, text="Cancel",             width=8,  command=root.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(btn_frm, text="Generate Subtitles", width=18, command=on_ok).pack(side="left")

    entry.focus()
    center(root)
    _make_draggable(root)
    root.lift()
    root.attributes("-topmost", True)
    root.mainloop()

    if result["chosen"] is not None and result["value"] is not None:
        cb = result["checkbox"] if result["checkbox"] is not None else ""
        print("%s\t%s\t%s" % (result["chosen"], result["value"], cb))


def notify(title, message):
    # Lightweight toast — just print; a real Windows toast needs extra libs
    print(f"[{title}] {message}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "alert" and len(sys.argv) >= 4:
        alert(sys.argv[2], sys.argv[3])

    elif cmd == "alert_error" and len(sys.argv) >= 4:
        alert_error(sys.argv[2], sys.argv[3])

    elif cmd == "pick" and len(sys.argv) >= 5:
        title  = sys.argv[2]
        prompt = sys.argv[3]
        items  = sys.argv[4:]
        pick(title, prompt, items)

    elif cmd == "input" and len(sys.argv) >= 5:
        title   = sys.argv[2]
        prompt  = sys.argv[3]
        default = sys.argv[4] if len(sys.argv) > 4 else ""
        checkbox_label = sys.argv[5] if len(sys.argv) > 5 else ""
        checkbox_default = sys.argv[6] if len(sys.argv) > 6 else "0"
        input_dialog(title, prompt, default, checkbox_label, checkbox_default)

    elif cmd == "pick_input" and len(sys.argv) >= 8:
        # Args: title prompt_pick prompt_input default checkbox_label checkbox_default item1 [item2 ...]
        title           = sys.argv[2]
        prompt_pick     = sys.argv[3]
        prompt_input    = sys.argv[4]
        default         = sys.argv[5]
        checkbox_label  = sys.argv[6]
        checkbox_default = sys.argv[7]
        items           = sys.argv[8:]
        pick_input(title, prompt_pick, items, prompt_input,
                   default, checkbox_label, checkbox_default)

    elif cmd == "notify" and len(sys.argv) >= 4:
        notify(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command or missing args: {sys.argv[1:]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
