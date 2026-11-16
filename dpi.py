"""Per-monitor DPI awareness for the process.

Called before any window opens, so the WebView2 windows and the native message
box render at the monitor's real resolution instead of being bitmap-stretched.
"""
import ctypes
import sys


def enable():
    if sys.platform != 'win32':
        return
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]; fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):                 # PER_MONITOR_AWARE_V2
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
