"""Shared pywebview plumbing for the WebView2 windows (home and studio).

Pages call these methods through window.pywebview.api. The saved API key never
crosses into a page: JavaScript only learns whether one exists.
"""
import os
import sys
import threading

import credentials
from app_runtime import resources


def available():
    """True when the web UI can be used on this machine."""
    if sys.platform != "win32" or os.environ.get("SRUTILEKHA_CLASSIC_UI") == "1":
        return False
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


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
            from elevenlabs.client import ElevenLabs
            ElevenLabs(api_key=key, timeout=15).user.get()
            return {"ok": True, "message": "Connection successful. Transcription uses your account credits."}
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            return {"ok": False, "message":
                    "API key rejected. Check your key." if code == 401 else
                    "Profile access denied. Check the key permissions; speech-to-text access may differ." if code == 403 else
                    "Could not connect. Check your internet connection and API permissions."}

    def save_key(self, key):
        try:
            credentials.save_key(key or "")
        except Exception:
            return {"ok": False, "message": "Could not save the key. Enter a valid key and try again."}
        return {"ok": True, "message": "API key saved and encrypted for this Windows account."}

    def remove_key(self):
        try:
            credentials.delete_key()
        except Exception:
            return {"ok": False, "message": "Could not remove the saved key. Try again."}
        return {"ok": True, "message": "Saved API key removed."}

    # ── updates ───────────────────────────────────────────────────────────
    def check_updates(self):
        if self._updater is None:
            return {"ok": False, "message": "Update check unavailable."}
        try:
            info = self._updater.check()
        except Exception:
            return {"ok": False, "message": "Update check unavailable. Try again later."}
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
            return {"ok": False, "message": "No update is ready to install."}
        try:
            self._updater.install(self._update)
        except Exception:
            return {"ok": False, "message": "Update failed. Your installation and API key are unchanged."}
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
