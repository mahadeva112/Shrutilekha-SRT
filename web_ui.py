"""Shared pywebview plumbing for the WebView2 windows (home, studio, notices).

Pages call these methods through window.pywebview.api. The saved API key never
crosses into a page: JavaScript only learns whether one exists.

Every Srutilekha window is a WebView2 page; there is no other interface. Setup
installs the WebView2 Evergreen runtime when a PC lacks it. If it is missing
anyway, message_box() tells the user with a plain Windows message box, the one
window that needs no WebView2.
"""
import os
import sys
import threading

import credentials
from app_runtime import resources

# Microsoft's WebView2 Evergreen runtime: its EdgeUpdate client id, and the
# permanent link to its bootstrapper (installer/Srutilekha.iss uses both too).
WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def runtime_version():
    """The installed WebView2 runtime's version, or "" when there is none.

    Microsoft's documented check: the EdgeUpdate client key's "pv" value, per
    machine (32- and 64-bit views) or per user. Empty or 0.0.0.0 means the
    runtime was removed. pywebview cannot be asked instead: without the runtime
    it quietly draws the pages in Internet Explorer's engine."""
    if sys.platform != "win32":
        return ""
    import winreg
    keys = ((winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\"),
            (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\"),
            (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\EdgeUpdate\\Clients\\"))
    for hive, clients in keys:
        path = clients + WEBVIEW2_CLIENT
        try:
            with winreg.OpenKey(hive, path) as key:
                version = str(winreg.QueryValueEx(key, "pv")[0] or "").strip()
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return version
    return ""


def available():
    """True when the WebView2 windows can open on this machine."""
    if sys.platform != "win32":
        return False
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return bool(runtime_version())


def message_box(title, text, error=True):
    """A native Windows message box, for when no WebView2 window can open.

    Topmost and brought to the front, so it is seen over Resolve. Elsewhere it
    prints to stderr."""
    if sys.platform == "win32":
        import ctypes
        flags = 0x10 if error else 0x40                  # MB_ICONERROR / MB_ICONINFORMATION
        flags |= 0x40000 | 0x10000                       # MB_TOPMOST | MB_SETFOREGROUND
        try:
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), flags)
            return
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        print("%s\n%s" % (title, text), file=sys.stderr)


def page(name):
    path = resources() / "ui" / name
    return path if path.exists() else None


class BaseApi:
    def __init__(self, updater=None):
        self._window = None
        self._update = None
        self._updater = updater
        self._busy = threading.Lock()

    def _has_key(self):
        try:
            return bool(credentials.get_key())
        except Exception:
            return False

    # ── API key ───────────────────────────────────────────────────────────
    def key_state(self):
        return {"hasKey": self._has_key()}

    def test_key(self, key):
        key = (key or "").strip()
        if not key:
            try:
                key = credentials.get_key()
            except Exception:
                key = ""
        if not key:
            return {"ok": False, "message": "Paste your API key first."}
        try:
            from app_runtime import ensure_trust
            ensure_trust()
            from elevenlabs.client import ElevenLabs
            ElevenLabs(api_key=key, timeout=15).user.get()
            return {"ok": True, "message": "Connection successful. Transcription uses your account credits."}
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            return {"ok": False, "message":
                    "ElevenLabs is asking for a current key. Copy a fresh one from elevenlabs.io and paste it here." if code == 401 else
                    "Your key is valid. Allow its profile access at elevenlabs.io to run this check; captions may already work." if code == 403 else
                    "Let's get online first: check this PC's internet connection, then test again."}

    def save_key(self, key):
        try:
            credentials.save_key(key or "")
        except Exception:
            return {"ok": False, "message": "Paste the full key, then press Save key again."}
        return {"ok": True, "message": "API key saved and encrypted for this Windows account."}

    def remove_key(self):
        try:
            credentials.delete_key()
        except Exception:
            return {"ok": False, "message": "The key is still saved. Press Remove once more."}
        return {"ok": True, "message": "Saved API key removed."}

    # ── updates ───────────────────────────────────────────────────────────
    def check_updates(self):
        if self._updater is None:
            return {"ok": False, "message": "Updates are checked in the installed app."}
        try:
            info = self._updater.check()
        except Exception:
            return {"ok": False, "message": "Updates will be checked again shortly. You are all set for now."}
        self._update = info
        version = self._updater.VERSION
        if not info:
            return {"ok": True, "available": False, "version": version,
                    "message": "Up to date · v" + version}
        return {"ok": True, "available": True, "version": info["version"],
                "released": info.get("released", ""), "notes": list(info.get("notes") or [])[:12],
                "message": "Update available: v" + info["version"]}

    def install_update(self):
        if not self._update or not self._busy.acquire(blocking=False):
            return {"ok": False, "message": "You are on the latest version."}
        try:
            self._updater.install(self._update)
        except Exception:
            return {"ok": False, "message": "Your current version and API key are kept. Try installing the update again in a moment."}
        finally:
            self._busy.release()
        self._after_update()
        return {"ok": True}

    def _after_update(self):
        self.close()

    # ── window chrome ─────────────────────────────────────────────────────
    def minimize(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize(self):
        if not self._window:
            return False
        maximized = getattr(self, "_maximized", False)
        (self._window.restore if maximized else self._window.maximize)()
        self._maximized = not maximized
        return self._maximized

    def close(self):
        if self._window:
            self._window.destroy()
