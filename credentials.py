"""Per-user API key: Windows DPAPI file, or the macOS login Keychain. No shipped key."""
import ctypes
import getpass
import os
import subprocess
import sys
from ctypes import wintypes
from app_runtime import user_dir

KEYCHAIN_SERVICE = "Srutilekha ElevenLabs API key"


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Secure key storage supports Windows and macOS only.")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                  ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def _keychain(*args, stdin=None):
    return subprocess.run(["/usr/bin/security", *args], input=stdin, capture_output=True,
                          text=True, timeout=20)


def _keychain_account():
    return getpass.getuser()


def _keychain_get():
    result = _keychain("find-generic-password", "-a", _keychain_account(),
                       "-s", KEYCHAIN_SERVICE, "-w")
    if result.returncode == 44:  # errSecItemNotFound
        return ""
    if result.returncode:
        raise OSError("Keychain read failed: " + (result.stderr.strip() or str(result.returncode)))
    return result.stdout.rstrip("\n")


def _keychain_quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _keychain_save(key):
    # `security -i` reads the command from stdin, so the key never appears in argv
    # where other processes could see it.
    command = "add-generic-password -U -a %s -s %s -w %s\n" % (
        _keychain_quote(_keychain_account()), _keychain_quote(KEYCHAIN_SERVICE), _keychain_quote(key))
    result = _keychain("-i", stdin=command)
    if result.returncode or "error" in (result.stderr or "").lower():
        raise OSError("Keychain write failed: " + (result.stderr.strip() or str(result.returncode)))


def _keychain_delete():
    result = _keychain("delete-generic-password", "-a", _keychain_account(), "-s", KEYCHAIN_SERVICE)
    if result.returncode not in (0, 44):
        raise OSError("Keychain delete failed: " + (result.stderr.strip() or str(result.returncode)))


def get_key():
    if sys.platform == "darwin":
        return _keychain_get()
    path = user_dir() / "api-key.dpapi"
    if not path.exists():
        return ""
    return _crypt(path.read_bytes(), decrypt=True).decode("utf-8")


def save_key(key):
    key = key.strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("Paste a valid API key without spaces or line breaks.")
    if sys.platform == "darwin":
        _keychain_save(key)
        return
    path = user_dir() / "api-key.dpapi"
    scratch = path.with_suffix(".tmp")
    scratch.write_bytes(_crypt(key.encode("utf-8")))
    os.replace(scratch, path)


def delete_key():
    if sys.platform == "darwin":
        _keychain_delete()
        return
    (user_dir() / "api-key.dpapi").unlink(missing_ok=True)


def configure_worker_key():
    key = get_key()
    if key:
        os.environ["ELEVENLABS_API_KEY"] = key
