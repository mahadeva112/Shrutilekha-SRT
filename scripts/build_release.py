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
    vendor = ROOT / "build" / "vendor"
    config = vendor / "ffmpeg-config.h"
    if not config.is_file() or "#define CONFIG_GPL 0" not in config.read_text():
        raise SystemExit("Build the LGPL FFmpeg first with scripts/build_ffmpeg.sh in MSYS2 UCRT64.")
    source = vendor / "ffmpeg-7.1.1.tar.xz"
    if hashlib.sha256(source.read_bytes()).hexdigest() != "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1":
        raise SystemExit("FFmpeg source checksum mismatch")
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
    for name in (source.name, "ffmpeg-config.log", "ffmpeg-config.h", "ffmpeg-toolchain.txt", "ffmpeg-version.txt"):
        shutil.copy2(vendor / name, output / name)
    shutil.copy2(ROOT / "scripts" / "build_ffmpeg.sh", output / "build_ffmpeg.sh")
    shutil.copy2(ROOT / "installer" / "COPYING.LGPLv2.1", output / "COPYING.LGPLv2.1")
    sums = [hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in sorted(output.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print("Release assets:", setup, output / "SHA256SUMS.txt", sep="\n")


if __name__ == "__main__":
    main()
