"""Fresh install/reinstall/uninstall test; restores existing Resolve launchers.

Run only on a development PC. Refuses to replace an existing Srutilekha
installer registration. Personal application data is never removed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import winreg

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tools" / "installer-test"
TARGET = WORK / "app"
GUID = "{0B88D427-1A18-45BD-A516-C576567354F4}_is1"


def main():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + GUID):
            raise SystemExit("An installed Srutilekha app exists; use a separate test Windows user.")
    except FileNotFoundError:
        pass
    WORK.mkdir(parents=True, exist_ok=True)
    assert TARGET.resolve().is_relative_to(ROOT.resolve() / ".tools")
    script_dir = Path(os.environ["APPDATA"]) / "Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility"
    pointer = Path.home() / ".audio_to_srt_path"
    paths = [pointer, script_dir / "Srutilekha.py", script_dir / "Srutilekha.lua"]
    backups = {p: p.read_bytes() if p.exists() else None for p in paths}
    version = json.loads((ROOT / "version.json").read_text())["version"]
    setup = ROOT / "dist" / "release" / ("Srutilekha-Setup-%s.exe" % version)
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW}
    user_data = Path(os.environ["LOCALAPPDATA"]) / "Srutilekha"
    user_data.mkdir(exist_ok=True)
    scratch = tempfile.TemporaryDirectory(prefix="installer-validation-", dir=user_data)
    marker = Path(scratch.name) / "presets.json"
    marker.write_text('{"validation": true}', encoding="utf-8")
    key_file = Path(scratch.name) / "api-key.dpapi"
    sys.path.insert(0, str(ROOT))
    from credentials import _crypt
    key_file.write_bytes(_crypt(b"installer-validation-key"))
    marker_bytes, key_bytes = marker.read_bytes(), key_file.read_bytes()
    previous = ROOT / "dist" / "release" / "Srutilekha-Setup-1.1.0.exe"
    phases = [("fresh-install", setup), ("reinstall", setup)]
    if version != "1.1.0" and previous.is_file():
        phases = [("previous-version", previous), ("upgrade", setup), ("reinstall", setup)]
    try:
        for phase, installer in phases:
            subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                            "/CURRENTUSER", "/DIR=" + str(TARGET), "/LOG=" + str(WORK / (phase + ".log"))],
                           check=True, timeout=180, **flags)
            recorded = pointer.read_text().strip()
            assert Path(recorded).resolve() == TARGET.resolve(), (recorded, str(TARGET))
            assert (script_dir / "Srutilekha.py").exists() or (script_dir / "Srutilekha.lua").exists()
            report = WORK / (phase + ".json")
            env = os.environ.copy()
            windows = os.environ["SystemRoot"]
            env["PATH"] = windows + "\\System32;" + windows
            subprocess.run([str(TARGET / "Srutilekha.exe"), "--self-test", str(report)],
                           env=env, check=True, timeout=60, **flags)
            assert json.loads(report.read_text())["encrypted_key"] == "ok"
            assert marker.read_bytes() == marker_bytes
            assert key_file.read_bytes() == key_bytes
            print(phase + ": OK")
    finally:
        uninstaller = TARGET / "unins000.exe"
        try:
            if uninstaller.exists():
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                               check=True, timeout=120, **flags)
            assert marker.read_bytes() == marker_bytes
            assert key_file.read_bytes() == key_bytes
        finally:
            scratch.cleanup()
            for path, data in backups.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            print("Existing Resolve launcher files and install pointer restored.")


if __name__ == "__main__":
    main()
