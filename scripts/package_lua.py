"""Adapt the legacy Resolve orchestration without changing source installs."""
from pathlib import Path


def package(source, target):
    text = Path(source).read_text(encoding="utf-8")
    replacements = {
        'local PROJECT_DIR = get_project_dir()':
            'local PROJECT_DIR = get_project_dir()\nlocal USER_DATA_DIR = os.getenv("LOCALAPPDATA") .. "\\\\Srutilekha"\nlocal APP_EXE = PROJECT_DIR .. SEP .. "Srutilekha.exe"',
        'local DIALOG_PY     = PROJECT_DIR .. SEP .. "dialog.py"': 'local DIALOG_PY = "--dialog"',
        'local LOADER_PY     = PROJECT_DIR .. SEP .. "loader.pyw"': 'local LOADER_PY = "--resolve"',
        'local PYTHONW = find_pythonw()': 'local PYTHONW = APP_EXE',
        'io.open(LOADER_PY)': 'io.open(APP_EXE)',
        'PROJECT_DIR .. SEP .. "logs"': 'USER_DATA_DIR .. SEP .. "logs"',
        'PROJECT_DIR .. SEP .. "subtitle_style.json"': 'USER_DATA_DIR .. SEP .. "subtitle_style.json"',
        ".. PROJECT_DIR .. '\\\\logs": ".. USER_DATA_DIR .. '\\\\logs",
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError("Legacy launcher changed; review packaging replacement: " + old)
        text = text.replace(old, new)
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(text, encoding="utf-8")
