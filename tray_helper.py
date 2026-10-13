"""Resident Windows tray helper. Idle monitoring never calls Resolve APIs."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from app_runtime import install_dir, resources, user_dir
from resolve_bridge import BridgeError, mailbox_lock, probe_connection

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'Srutilekha'


def app_command(*args):
    if getattr(sys, 'frozen', False):
        return [str(install_dir() / 'Srutilekha.exe'), *args]
    return [sys.executable, str(resources() / 'app.py'), *args]


def launch(*args):
    return subprocess.Popen(app_command(*args), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
        return value in (subprocess.list2cmdline(app_command('--tray')), '"%s" --tray' % app_command()[0])
    except OSError:
        return False


def set_startup(enabled):
    import winreg
    marker = user_dir() / 'tray-startup-disabled.flag'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(app_command('--tray')))
            marker.unlink(missing_ok=True)
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
            marker.write_text('disabled', encoding='utf-8')


def queue_command(action):
    folder = user_dir() / 'tray-commands'
    folder.mkdir(exist_ok=True)
    path = folder / (uuid.uuid4().hex + '.json')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'action':action, 'time':time.time()}), encoding='utf-8')
    os.replace(temp, path)


def request_open():
    queue_command('open')
    launch('--tray')  # The resident lock makes repeated starts harmless.


def request_raise():
    (user_dir() / 'raise-caption.flag').write_text('raise', encoding='utf-8')


def resolve_identity():
    import psutil
    for process in psutil.process_iter(['name', 'pid', 'create_time']):
        if (process.info['name'] or '').lower() == 'resolve.exe':
            return process.info['pid'], process.info['create_time']
    return None


def launch_signal():
    # Constructing a client is unnecessary during idle monitoring.
    prefs = Path(os.environ['APPDATA']) / 'Blackmagic Design/DaVinci Resolve/Support/Fusion/Profiles/Default/Fusion.prefs'
    try:
        content = prefs.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    match = re.search(r'SrutilekhaBridgeLaunch\s*=\s*"([A-Za-z0-9]+)"', content)
    launched = re.search(r'SrutilekhaBridgeLaunchTime\s*=\s*(\d+)', content)
    return (match.group(1), int(launched.group(1))) if match and launched else None


class TrayController:
    def __init__(self):
        self.seen = None
        self.resolve = None
        self.child = None
        self.home = None
        self.lock = threading.Lock()

    def active_caption(self):
        try:
            with mailbox_lock(user_dir() / 'resolve-bridge' / 'workflow.lock'):
                return False
        except BridgeError:
            return True

    def open(self, automatic=False):
        with self.lock:
            if self.active_caption():
                request_raise()
                return True
            if self.child and self.child.poll() is None:
                return True
            try:
                info = probe_connection()
            except (BridgeError, OSError):
                if not automatic:
                    if not self.home or self.home.poll() is not None:
                        self.home = launch('--home')
                return False
            self.seen = info['session']
            self.child = launch('--bridge-run')
            return True

    def tick(self):
        identity = resolve_identity()
        if identity != self.resolve:
            self.resolve, self.seen = identity, None
        if not identity:
            return
        packet = launch_signal()
        if not packet or packet[1] < identity[1] - 2:
            return  # Ignore persisted markers from an earlier Resolve process.
        signal = packet[0]
        if signal != self.seen:
            if self.open(automatic=True):
                self.seen = signal


def make_icon(controller, stop):
    import pystray
    from PIL import Image
    def quit_helper(icon, item):
        stop.set()
        icon.stop()  # Caption jobs belong to a separate process and keep running.
    def toggle_startup(icon, item):
        set_startup(not startup_enabled())
        icon.update_menu()
    return pystray.Icon('Srutilekha', Image.open(resources() / 'icon.ico'), 'Srutilekha — ready for Resolve', menu=pystray.Menu(
        pystray.MenuItem('Open captions', lambda icon,item: controller.open(), default=True),
        pystray.MenuItem('API settings', lambda icon,item: launch('--home', '--api-settings')),
        pystray.MenuItem('Updates', lambda icon,item: launch('--home')),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Start with Windows', toggle_startup, checked=lambda item: startup_enabled()),
        pystray.MenuItem('Quit helper', quit_helper),
    ))


def run():
    try:
        with mailbox_lock(user_dir() / 'tray.lock'):
            stop = threading.Event()
            controller = TrayController()
            icon = make_icon(controller, stop)
            def monitor():
                folder = user_dir() / 'tray-commands'
                folder.mkdir(exist_ok=True)
                while not stop.is_set():
                    for path in folder.glob('*.json'):
                        try:
                            command = json.loads(path.read_text(encoding='utf-8'))
                            path.unlink(missing_ok=True)
                            if time.time() - command['time'] > 30:
                                continue
                            if command['action'] == 'stop':
                                stop.set(); icon.stop(); return
                            if command['action'] == 'open':
                                controller.open()
                        except (OSError, ValueError, KeyError):
                            pass
                    try:
                        controller.tick()
                    except Exception:
                        # A closing Resolve or transient prefs write is retried later.
                        pass
                    stop.wait(1)
            def ready(icon):
                icon.visible = True
                threading.Thread(target=monitor, daemon=True).start()
            try:
                icon.run(setup=ready)
            finally:
                stop.set()
    except BridgeError:
        pass  # Another helper owns the tray; queued commands reach it.


def self_test(output):
    """Verify the real native tray backend without touching startup or Resolve."""
    stop = threading.Event()
    icon = make_icon(TrayController(), stop)
    def ready(icon):
        icon.visible = True
        Path(output).write_text(json.dumps({'tray':'native Windows icon', 'menu_items':len(list(icon.menu)), 'visible':icon.visible}), encoding='utf-8')
        icon.stop()
    icon.run(setup=ready)
