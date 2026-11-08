"""Platform-specific paths, locks and key storage, testable on any OS."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app_runtime
import credentials
from resolve_bridge import BridgeError, mailbox_lock


class PathTests(unittest.TestCase):
    def test_mac_locations(self):
        with patch.object(app_runtime, "IS_WINDOWS", False), patch.object(app_runtime, "IS_MAC", True),              patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SRUTILEKHA_USER_DIR", None)
            support = Path.home() / "Library" / "Application Support"
            self.assertEqual(app_runtime._user_base(), support)
            resolve = support / "Blackmagic Design" / "DaVinci Resolve"
            self.assertEqual(app_runtime.fusion_prefs(), resolve / "Fusion" / "Profiles" / "Default" / "Fusion.prefs")
            self.assertEqual(app_runtime.resolve_scripts_dir(), resolve / "Fusion" / "Scripts" / "Utility")
            self.assertEqual(app_runtime.app_executable().name, "Srutilekha")

    def test_windows_locations_unchanged(self):
        with patch.object(app_runtime, "IS_WINDOWS", True), patch.object(app_runtime, "IS_MAC", False),              patch.dict(os.environ, {"APPDATA": "C:/Roaming", "LOCALAPPDATA": "C:/Local"}):
            self.assertEqual(app_runtime._user_base(), Path("C:/Local"))
            self.assertEqual(app_runtime.fusion_prefs(), Path(
                "C:/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Profiles/Default/Fusion.prefs"))
            self.assertEqual(app_runtime.app_executable().name, "Srutilekha.exe")


class LockTests(unittest.TestCase):
    def test_lock_is_exclusive_across_processes_and_released(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.lock"
            probe = ("import sys; from pathlib import Path; sys.path.insert(0, %r)\n"
                     "from resolve_bridge import mailbox_lock, BridgeError\n"
                     "try:\n    with mailbox_lock(Path(%r)): print('free')\n"
                     "except BridgeError: print('busy')\n") % (str(Path(__file__).resolve().parents[1]), str(path))
            run = lambda: subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60).stdout.strip()
            with mailbox_lock(path):
                self.assertEqual(run(), "busy")
            self.assertEqual(run(), "free")


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class KeychainTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(credentials.sys, "platform", "darwin"); p.start(); self.addCleanup(p.stop)

    def test_save_keeps_key_out_of_argv(self):
        with patch("credentials.subprocess.run", return_value=Completed()) as run:
            credentials.save_key('sk_ab"c\\d')
        argv, stdin = run.call_args.args[0], run.call_args.kwargs["input"]
        self.assertEqual(argv, ["/usr/bin/security", "-i"])
        self.assertNotIn("sk_ab", " ".join(argv))
        self.assertIn('-w "sk_ab\\"c\\\\d"', stdin)
        self.assertIn('-s "Srutilekha ElevenLabs API key"', stdin)

    def test_get_missing_and_present(self):
        with patch("credentials.subprocess.run", return_value=Completed(44)):
            self.assertEqual(credentials.get_key(), "")
        with patch("credentials.subprocess.run", return_value=Completed(0, "sk_test\n")) as run:
            self.assertEqual(credentials.get_key(), "sk_test")
        self.assertIn("find-generic-password", run.call_args.args[0])

    def test_delete_ignores_missing_and_reports_errors(self):
        with patch("credentials.subprocess.run", return_value=Completed(44)):
            credentials.delete_key()
        with patch("credentials.subprocess.run", return_value=Completed(51, stderr="denied")):
            with self.assertRaises(OSError):
                credentials.delete_key()

    def test_invalid_key_rejected_before_keychain(self):
        with patch("credentials.subprocess.run") as run, self.assertRaises(ValueError):
            credentials.save_key("has space")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
