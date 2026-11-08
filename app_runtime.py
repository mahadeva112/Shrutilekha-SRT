"""Locations shared by source, frozen GUI and frozen transcription worker."""
import os
import sys
from pathlib import Path


def frozen():
    return bool(getattr(sys, "frozen", False))


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def install_dir():
    return Path(sys.executable).parent if frozen() else resources()


IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def app_executable():
    """The frozen GUI binary: Srutilekha.exe on Windows, Srutilekha in a .app bundle."""
    return install_dir() / ("Srutilekha.exe" if IS_WINDOWS else "Srutilekha")


def _user_base():
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))
    if IS_MAC:
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def user_dir():
    override = os.environ.get("SRUTILEKHA_USER_DIR")
    base = Path(override) if override else _user_base() / "Srutilekha"
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_support_dir():
    """DaVinci Resolve's per-user folder that holds Fusion profiles and scripts."""
    if IS_WINDOWS:
        return Path(os.environ["APPDATA"]) / "Blackmagic Design" / "DaVinci Resolve" / "Support"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"
    return Path.home() / ".local" / "share" / "DaVinciResolve"


def fusion_prefs():
    """Resolve-managed Fusion preferences; the Lua bridge writes responses here."""
    return resolve_support_dir() / "Fusion" / "Profiles" / "Default" / "Fusion.prefs"


def resolve_scripts_dir():
    """Workspace > Scripts menu folder for per-user Utility scripts."""
    return resolve_support_dir() / "Fusion" / "Scripts" / "Utility"


def data_dir():
    return user_dir() if frozen() else resources()


def prepare_environment():
    binary_dir = resources() / "bin"
    if binary_dir.is_dir():
        os.environ["PATH"] = str(binary_dir) + os.pathsep + os.environ.get("PATH", "")
