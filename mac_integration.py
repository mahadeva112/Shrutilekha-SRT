"""First-run setup for the packaged macOS app, which has no installer.

Windows does this in Inno Setup; on macOS the app does it itself each time it
starts (GUI or menu bar helper), so it also repairs a deleted script.
"""
from app_runtime import IS_MAC, frozen, resolve_scripts_dir, resolve_support_dir, user_dir

BRIDGE_NAME = 'Srutilekha.lua'


def install_bridge_script():
    """Write the Lua bridge into Resolve's Scripts menu. Returns the path, or None
    when Resolve has never run for this user (its support folder is missing)."""
    from resolve_bridge import launcher_text
    if not resolve_support_dir().is_dir():
        return None
    target = resolve_scripts_dir() / BRIDGE_NAME
    text = launcher_text()
    try:
        if target.read_text(encoding='utf-8') == text:
            return target
    except OSError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_suffix('.tmp')
    scratch.write_text(text, encoding='utf-8')
    scratch.replace(target)
    return target


def enable_startup_once():
    """Start the helper at login unless the user turned that off before."""
    from tray_helper import set_startup, startup_enabled
    if (user_dir() / 'tray-startup-disabled.flag').exists() or startup_enabled():
        return
    set_startup(True)


def ensure():
    if not (IS_MAC and frozen()):
        return
    for step in (install_bridge_script, enable_startup_once):
        try:
            step()
        except OSError:
            pass  # Retried at the next launch; never block the app on setup.
