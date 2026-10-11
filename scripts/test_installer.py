"""Fresh install/reinstall/uninstall test; restores existing Resolve launchers.

Run only on a development PC. Refuses to replace an existing Srutilekha
installer registration. Personal application data is never removed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
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
    try:
        for phase in ("fresh-install", "reinstall"):
            subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
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
            print(phase + ": OK")
    finally:
        uninstaller = TARGET / "unins000.exe"
        try:
            if uninstaller.exists():
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                               check=True, timeout=120, **flags)
        finally:
            for path, data in backups.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            print("Existing Resolve launcher files and install pointer restored.")


if __name__ == "__main__":
    main()
