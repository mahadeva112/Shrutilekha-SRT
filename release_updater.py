"""Stable GitHub releases only. Verify the installer before launching Setup."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from app_runtime import resources, user_dir
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

OWNER = "mahadeva112"
REPO = "Shrutilekha-SRT"
MAX_INSTALLER_BYTES = 500 * 1024 * 1024
VERSION = json.loads((resources() / "version.json").read_text(encoding="utf-8"))["version"]


class UpdateError(Exception):
    pass


def version(value):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise UpdateError("Invalid release version.")
    return tuple(map(int, value.lstrip("v").split(".")))


def _request(url, timeout=15):
    return urlopen(Request(url, headers={"User-Agent": "Srutilekha/" + VERSION,
                                        "Accept": "application/vnd.github+json"}), timeout=timeout)


def _release_asset(asset, tag, name):
    expected = "https://github.com/%s/%s/releases/download/%s/%s" % (OWNER, REPO, tag, name)
    if asset.get("browser_download_url") != expected:
        raise UpdateError("Unexpected release download address.")
    return expected


def check():
    url = "https://api.github.com/repos/%s/%s/releases/latest" % (OWNER, REPO)
    try:
        with _request(url) as response:
            release = json.loads(response.read(1024 * 1024))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError("GitHub update check is unavailable.") from exc
    tag = release.get("tag_name", "")
    remote = version(tag)
    if release.get("draft") or release.get("prerelease") or remote <= version(VERSION):
        return None
    name = "Srutilekha-Setup-%s.exe" % tag.lstrip("v")
    assets = {a["name"]: a for a in release.get("assets", [])}
    if name not in assets or "SHA256SUMS.txt" not in assets:
        raise UpdateError("Release installer or checksum is missing.")
    return {"version": tag.lstrip("v"), "notes": (release.get("body") or "").splitlines(),
            "released": (release.get("published_at") or "")[:10],
            "installer": _release_asset(assets[name], tag, name),
            "checksums": _release_asset(assets["SHA256SUMS.txt"], tag, "SHA256SUMS.txt"),
            "name": name, "size": assets[name].get("size", 0)}


def download(info, report=lambda message: None):
    tag = "v" + info["version"]
    version(tag)
    name = "Srutilekha-Setup-%s.exe" % info["version"]
    if info["name"] != name:
        raise UpdateError("Unexpected installer name.")
    for key, filename in (("installer", name), ("checksums", "SHA256SUMS.txt")):
        _release_asset({"browser_download_url": info[key]}, tag, filename)
    report("Verifying release metadata…")
    with _request(info["checksums"]) as response:
        checksums = response.read(65537)
    if len(checksums) > 65536:
        raise UpdateError("Checksum file is too large.")
    hashes = {}
    for line in checksums.decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            hashes[parts[1].lstrip("*")] = parts[0].lower()
    expected = hashes.get(name)
    if not expected:
        raise UpdateError("Installer checksum is missing.")
    target_dir = user_dir() / "updates"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / name
    scratch = target.with_suffix(".download")
    digest = hashlib.sha256()
    size = 0
    try:
        with _request(info["installer"], timeout=180) as response, scratch.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_INSTALLER_BYTES:
                    raise UpdateError("Installer exceeds the download limit.")
                output.write(block)
                digest.update(block)
                report("Downloaded %.1f MB…" % (size / 1048576))
        if not size or (info.get("size") and size != info["size"]):
            raise UpdateError("Installer download is incomplete.")
        if digest.hexdigest() != expected:
            raise UpdateError("Installer checksum did not match. Please retry.")
        os.replace(scratch, target)
        return target
    finally:
        scratch.unlink(missing_ok=True)


def install(info, report=lambda message: None):
    target = download(info, report)
    report("Opening Setup. Close Srutilekha to finish the update.")
    subprocess.Popen([str(target), "/CURRENTUSER", "/SP-"], close_fds=True)
    return str(target)
