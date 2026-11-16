"""Keep any Tk window a test might open off the user's screen.

The app has no Tk windows any more (every window is WebView2), so no test
should create one; this stays as a safety net for the tests that drive app
entry points. The classic studio, review and settings layout tests used to
flash windows over whatever the user was doing every time the suite ran.
Every Tk and Toplevel window made in a test starts fully transparent instead:
it is still mapped and measured, just unseen. Import this module before any
window is created.
"""
import tkinter as tk


def _hide(window):
    try:
        window.attributes("-alpha", 0.0)
    except tk.TclError:
        pass


if not getattr(tk, "_srutilekha_hidden", False):
    tk._srutilekha_hidden = True
    _tk_init = tk.Tk.__init__
    _toplevel_init = tk.Toplevel.__init__

    def _hidden_tk(self, *args, **kwargs):
        _tk_init(self, *args, **kwargs)
        _hide(self)

    def _hidden_toplevel(self, *args, **kwargs):
        _toplevel_init(self, *args, **kwargs)
        _hide(self)

    tk.Tk.__init__ = _hidden_tk
    tk.Toplevel.__init__ = _hidden_toplevel
