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


def user_dir():
    override = os.environ.get("SRUTILEKHA_USER_DIR")
    base = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Srutilekha"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_dir():
    return user_dir() if frozen() else resources()


def prepare_environment():
    binary_dir = resources() / "bin"
    if binary_dir.is_dir():
        os.environ["PATH"] = str(binary_dir) + os.pathsep + os.environ.get("PATH", "")
