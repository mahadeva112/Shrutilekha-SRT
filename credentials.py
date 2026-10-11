"""Per-Windows-user API key, encrypted with Windows DPAPI. No shipped key."""
import ctypes
import os
from ctypes import wintypes
from app_runtime import user_dir


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Secure key storage currently supports Windows only.")
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


def get_key():
    path = user_dir() / "api-key.dpapi"
    if not path.exists():
        return ""
    return _crypt(path.read_bytes(), decrypt=True).decode("utf-8")


def save_key(key):
    key = key.strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("Paste a valid API key without spaces or line breaks.")
    path = user_dir() / "api-key.dpapi"
    scratch = path.with_suffix(".tmp")
    scratch.write_bytes(_crypt(key.encode("utf-8")))
    os.replace(scratch, path)


def delete_key():
    (user_dir() / "api-key.dpapi").unlink(missing_ok=True)


def configure_worker_key():
    key = get_key()
    if key:
        os.environ["ELEVENLABS_API_KEY"] = key
