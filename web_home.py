"""WebView2 home window: connection, API key, updates and startup.

The page lives in ui/home.*; key, update and window handling is shared with
the studio through web_ui.BaseApi.
"""
import subprocess
import sys

import credentials
import release_updater
import web_ui
from app_runtime import install_dir, resources


class Api(web_ui.BaseApi):
    def __init__(self, open_settings):
        super().__init__(release_updater)
        self._open_settings = open_settings

    def initial(self):
        from tray_helper import startup_enabled
        return {"version": release_updater.VERSION, "hasKey": self._has_key(),
                "startup": startup_enabled(), "openSettings": self._open_settings,
                "home": "--home" in sys.argv}

    # ── Resolve connection ────────────────────────────────────────────────
    def probe(self):
        from resolve_bridge import probe_connection, BridgeError
        try:
            probe_connection()
            return {"ready": True}
        except BridgeError as exc:
            if "Another Srutilekha operation" in str(exc):
                return {"ready": False, "message": "Your caption window is already open. Close it to reconnect here."}
        except Exception:
            pass
        return {"ready": False, "message": "Waiting for Resolve. Start Workspace → Scripts → Srutilekha; this app will connect automatically."}

    def connect_resolve(self):
        command = ([str(install_dir() / "Srutilekha.exe"), "--bridge-run"] if getattr(sys, "frozen", False)
                   else [sys.executable, str(resources() / "app.py"), "--bridge-run"])
        subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.close()

    def set_startup(self, enabled):
        from tray_helper import set_startup
        set_startup(bool(enabled))
        return True


def run():
    """Show the home window. Returns False when WebView2 is unavailable."""
    page = web_ui.page("home.html")
    if not web_ui.available() or page is None:
        return False
    import webview
    open_settings = "--api-settings" in sys.argv
    if not open_settings:
        try:
            open_settings = not credentials.get_key()
        except Exception:
            open_settings = True
    api = Api(open_settings)
    try:
        api._window = webview.create_window(
            "Srutilekha", url=str(page), js_api=api, width=940, height=660,
            min_size=(760, 560), frameless=True, easy_drag=False,
            background_color="#0d0f10")
        webview.start(gui="edgechromium", private_mode=True)
    except Exception:
        return False
    return True
