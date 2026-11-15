"""WebView2 popup for the alerts Resolve's script opens through dialog.py.

The page (ui/notice.*) uses the studio's own stylesheet, so a paused run or a
short message looks like the rest of the app. The window starts hidden; once
the page has laid itself out it reports its height, and the window is sized
to it, centred on the monitor under the mouse (where Resolve is) and brought
in front of Resolve. show() returns False whenever WebView2 cannot be used,
and dialog.py then draws the Tk version instead.
"""
import ctypes
import ctypes.wintypes
import sys
import threading

import web_ui

WIDTH = 540            # CSS pixels
_HWND_TOPMOST = -1
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", ctypes.c_ulong)]


def _work_area_under_cursor():
    u32 = ctypes.windll.user32
    point = ctypes.wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(point))
    u32.MonitorFromPoint.restype = ctypes.c_void_p
    monitor = u32.MonitorFromPoint(point, 2)          # MONITOR_DEFAULTTONEAREST
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u32.GetMonitorInfoW(monitor, ctypes.byref(info))
    return info.rcWork


def _round_corners(hwnd):
    """Windows 11 rounds the frameless popup like its own dialogs and draws
    a soft gold edge; older Windows keeps the page's own 1px border."""
    try:
        dwm = ctypes.windll.dwmapi
        corner = ctypes.c_int(2)                       # DWMWCP_ROUND
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(corner), 4)
        border = ctypes.c_uint(0x0034475A)             # COLORREF (BGR) of #5a4734, muted gold
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 34, ctypes.byref(border), 4)
    except (AttributeError, OSError):
        pass


def _bring_forward(hwnd):
    """Resolve has the foreground; let the popup take it, as dialog.py does."""
    try:
        u32 = ctypes.windll.user32
        u32.SystemParametersInfoW(0x2001, 0, 0, 2)     # SPI_SETFOREGROUNDLOCKTIMEOUT
        u32.BringWindowToTop(ctypes.c_void_p(hwnd))
        u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    except (AttributeError, OSError):
        pass


class Api:
    def __init__(self, notice):
        self._notice = notice
        self._window = None
        self._placed = False
        self.shown = threading.Event()

    def initial(self):
        return self._notice

    def _hwnd(self):
        return int(self._window.native.Handle.ToInt64())

    def fit(self, height, scale=1):
        """Size the window to the page (CSS pixels at `scale`). The first call
        centres it and shows it; later ones (Show details) keep its top edge."""
        if not self._window:
            return False
        try:
            hwnd = self._hwnd()
            scale = float(scale) or 1.0
            work = _work_area_under_cursor()
            w = int(round(WIDTH * scale))
            h = min(int(round(float(height) * scale)), work.bottom - work.top - 24)
            u32 = ctypes.windll.user32
            if self._placed:
                rect = _Rect()
                u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
                x, y = rect.left, min(rect.top, work.bottom - h)
            else:
                x = work.left + (work.right - work.left - w) // 2
                y = work.top + (work.bottom - work.top - h) // 2
                _round_corners(hwnd)
            u32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(_HWND_TOPMOST),
                             x, y, w, h, _SWP_NOACTIVATE)
        except Exception:
            pass
        self._show()
        return True

    def _show(self):
        if self._placed:
            return
        self._placed = True
        try:
            self._window.show()
            _bring_forward(self._hwnd())
        except Exception:
            pass
        self.shown.set()

    def close(self):
        if self._window:
            self._window.destroy()


def show(notice):
    """Show `notice` ({kind, kicker, title, message, steps, details, button})
    and block until it is closed. False when WebView2 is not available."""
    page = web_ui.page("notice.html")
    if not web_ui.available() or page is None:
        return False
    try:
        import webview
    except ImportError:
        return False
    api = Api(dict(notice))
    # A rough centre for now: giving a position makes WinForms keep the one
    # fit() sets, where it would otherwise move the window on its first Show().
    try:
        work = _work_area_under_cursor()
        dpi = ctypes.windll.user32.GetDpiForSystem() / 96.0 or 1.0
        x = int((work.left + (work.right - work.left) / 2) / dpi - WIDTH / 2)
        y = int((work.top + (work.bottom - work.top) / 2) / dpi - 210)
    except (AttributeError, OSError):
        x = y = None
    try:
        api._window = webview.create_window(
            notice.get("title") or "Srutilekha", url=str(page), js_api=api,
            width=WIDTH, height=420, x=x, y=y, frameless=True, easy_drag=False,
            resizable=False, on_top=True, hidden=True, background_color="#16191b")

        def safety_net():
            # If the page never reports its size, show the window anyway
            # rather than leave the message unseen.
            if not api.shown.wait(4):
                api._show()
        api._window.events.loaded += lambda *a: threading.Thread(target=safety_net, daemon=True).start()
        webview.start(gui="edgechromium", private_mode=True)
    except Exception:
        return api.shown.is_set()
    return True


if __name__ == "__main__" and len(sys.argv) > 1:
    import notices
    show(dict(notices.describe(" ".join(sys.argv[1:])), kind="error", kicker="One more step"))
