"""Keep any Tk window a test might open off the user's screen.

The app has no Tk windows any more (every window is WebView2), so no test
should create one; this stays as a safety net for the tests that drive app
entry points. The classic studio, review and settings layout tests used to
flash windows over whatever the user was doing every time the suite ran.
Every Tk and Toplevel window made in a test starts fully transparent instead:
it is still mapped and measured, just unseen.

Transparent alone still left a "Srutilekha" button blinking on the taskbar for
each window, and let a window take keyboard focus from whatever the user was
typing in. So on Windows each window is also a tool window (no taskbar button)
that cannot be activated.
Import this module before any window is created.
"""
import sys
import tkinter as tk

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # no size/move/z-order/activate; frame changed


def _user_window():
    """The window the user is working in, if it is not one of ours."""
    import ctypes
    import ctypes.wintypes as wt
    import os
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd if hwnd and pid.value != os.getpid() else None


def _no_activate(window, previous):
    """Stop Windows from giving this window the keyboard focus.

    Tk only builds the real frame when a window is first shown, and Windows
    activates a process's first window then. So the style is applied on Map,
    and if the window got the focus by then it goes straight back."""
    import ctypes
    user32 = ctypes.windll.user32

    def mapped(event):
        if event.widget is not window:
            return
        try:
            hwnd = user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT: Tk's wrapper frame
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)
            if previous and user32.GetForegroundWindow() == hwnd:
                user32.SetForegroundWindow(previous)
        except Exception:
            pass

    try:
        window.bind("<Map>", mapped, add="+")
    except tk.TclError:
        pass


def _hide(window, previous=None):
    try:
        window.attributes("-alpha", 0.0)
        if sys.platform == "win32":
            window.attributes("-toolwindow", True)
    except tk.TclError:
        return
    if sys.platform == "win32":
        _no_activate(window, previous)


def _before():
    try:
        return _user_window() if sys.platform == "win32" else None
    except Exception:
        return None


if not getattr(tk, "_srutilekha_hidden", False):
    tk._srutilekha_hidden = True
    _tk_init = tk.Tk.__init__
    _toplevel_init = tk.Toplevel.__init__

    def _hidden_tk(self, *args, **kwargs):
        previous = _before()
        _tk_init(self, *args, **kwargs)
        _hide(self, previous)

    def _hidden_toplevel(self, *args, **kwargs):
        previous = _before()
        _toplevel_init(self, *args, **kwargs)
        _hide(self, previous)

    tk.Tk.__init__ = _hidden_tk
    tk.Toplevel.__init__ = _hidden_toplevel
    if sys.platform == "win32":
        # The app raises its dialogs with focus_force; in tests that would
        # still pull focus from the user's own window.
        tk.Misc.focus_force = lambda self: None
