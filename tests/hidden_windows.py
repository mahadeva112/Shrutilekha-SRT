"""Keep the Tk windows the tests open off the user's screen.

Layout tests have to map real windows so Tk reports real sizes, which made the
classic studio, review and settings windows flash over whatever the user was
doing every time the suite ran. Every Tk and Toplevel window made in a test
starts fully transparent instead: it is still mapped and measured, just unseen.
Import this module before any window is created.
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
