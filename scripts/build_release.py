"""Build the Windows app and, if ISCC is present, the release installer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    from package_lua import package
    package(ROOT / "audio_to_srt.lua", ROOT / "build" / "Srutilekha.lua")
    import imageio_ffmpeg
    vendor = ROOT / "build" / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), vendor / "ffmpeg.exe")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "Srutilekha.spec"], cwd=ROOT, check=True)
    version = json.loads((ROOT / "version.json").read_text())["version"]
    candidates = [os.environ.get("ISCC", ""), shutil.which("ISCC") or "",
                  r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    compiler = next((p for p in candidates if p and Path(p).is_file()), None)
    if not compiler:
        raise SystemExit("App built in dist/Srutilekha. Install Inno Setup 6 or set ISCC to build Setup.exe.")
    subprocess.run([compiler, "/DAppVersion=" + version, "installer/Srutilekha.iss"], cwd=ROOT, check=True)
    output = ROOT / "dist" / "release"
    setup = output / ("Srutilekha-Setup-%s.exe" % version)
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(digest + "  " + setup.name + "\n", encoding="utf-8")
    print("Release assets:", setup, output / "SHA256SUMS.txt", sep="\n")


if __name__ == "__main__":
    main()
