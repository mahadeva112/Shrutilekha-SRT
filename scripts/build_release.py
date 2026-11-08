"""Build the app and its release assets.

Windows: dist/Srutilekha and, if ISCC is present, the Setup.exe installer.
macOS: dist/Srutilekha.app and an unsigned .dmg.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAC = sys.platform == "darwin"
FFMPEG_SHA256 = "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"


def mac_dmg_name(version):
    return "Srutilekha-%s-macOS.dmg" % version


def check_ffmpeg(vendor):
    config = vendor / ("ffmpeg-macos-config.h" if MAC else "ffmpeg-config.h")
    script = "scripts/build_ffmpeg_macos.sh" if MAC else "scripts/build_ffmpeg.sh in MSYS2 UCRT64"
    if not config.is_file() or "#define CONFIG_GPL 0" not in config.read_text():
        raise SystemExit("Build the LGPL FFmpeg first with " + script + ".")
    source = vendor / "ffmpeg-7.1.1.tar.xz"
    if hashlib.sha256(source.read_bytes()).hexdigest() != FFMPEG_SHA256:
        raise SystemExit("FFmpeg source checksum mismatch")
    return source


def build_windows_installer(version):
    candidates = [os.environ.get("ISCC", ""), shutil.which("ISCC") or "",
                  r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    compiler = next((p for p in candidates if p and Path(p).is_file()), None)
    if not compiler:
        raise SystemExit("App built in dist/Srutilekha. Install Inno Setup 6 or set ISCC to build Setup.exe.")
    subprocess.run([compiler, "/DAppVersion=" + version, "installer/Srutilekha.iss"], cwd=ROOT, check=True)
    return ROOT / "dist" / "release" / ("Srutilekha-Setup-%s.exe" % version)


def build_mac_dmg(version):
    app = ROOT / "dist" / "Srutilekha.app"
    if not app.is_dir():
        raise SystemExit("PyInstaller did not produce dist/Srutilekha.app")
    output = ROOT / "dist" / "release"
    output.mkdir(parents=True, exist_ok=True)
    dmg = output / mac_dmg_name(version)
    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging)
        # ditto keeps the bundle's symlinks and signatures intact.
        subprocess.run(["ditto", str(app), str(stage / "Srutilekha.app")], check=True)
        (stage / "Applications").symlink_to("/Applications")
        shutil.copy2(ROOT / "docs" / "macos-install.txt", stage / "Read me first.txt")
        subprocess.run(["hdiutil", "create", "-volname", "Srutilekha " + version, "-srcfolder", str(stage),
                        "-ov", "-format", "UDZO", str(dmg)], check=True)
    return dmg


def main():
    vendor = ROOT / "build" / "vendor"
    source = check_ffmpeg(vendor)
    if not MAC:
        from package_lua import package
        package(ROOT / "audio_to_srt.lua", ROOT / "build" / "Srutilekha.lua")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "Srutilekha.spec"], cwd=ROOT, check=True)
    version = json.loads((ROOT / "version.json").read_text())["version"]
    deliverable = build_mac_dmg(version) if MAC else build_windows_installer(version)
    output = ROOT / "dist" / "release"
    if MAC:
        extras = ("ffmpeg-macos-config.log", "ffmpeg-macos-config.h", "ffmpeg-macos-toolchain.txt", "ffmpeg-macos-version.txt")
        script = "build_ffmpeg_macos.sh"
    else:
        extras = ("ffmpeg-config.log", "ffmpeg-config.h", "ffmpeg-toolchain.txt", "ffmpeg-version.txt")
        script = "build_ffmpeg.sh"
    for name in (source.name,) + extras:
        shutil.copy2(vendor / name, output / name)
    shutil.copy2(ROOT / "scripts" / script, output / script)
    shutil.copy2(ROOT / "installer" / "COPYING.LGPLv2.1", output / "COPYING.LGPLv2.1")
    sums = [hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in sorted(output.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print("Release assets:", deliverable, output / "SHA256SUMS.txt", sep="\n")


if __name__ == "__main__":
    main()
