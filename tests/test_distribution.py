import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app_runtime
import credentials
import release_updater as updates


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"SRUTILEKHA_USER_DIR": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_key_roundtrip_replace_and_remove(self):
        key = "test-key-no-real-credentials"
        credentials.save_key(key)
        ciphertext = (Path(self.temp.name) / "api-key.dpapi").read_bytes()
        self.assertNotIn(key.encode(), ciphertext)
        self.assertEqual(credentials.get_key(), key)
        credentials.save_key("second-test-key")
        self.assertEqual(credentials.get_key(), "second-test-key")
        credentials.delete_key()
        self.assertEqual(credentials.get_key(), "")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_corrupted_key_rejected(self):
        (Path(self.temp.name) / "api-key.dpapi").write_bytes(b"invalid")
        with self.assertRaises(OSError):
            credentials.get_key()

    def info(self, data):
        base = "https://github.com/mahadeva112/Shrutilekha-SRT/releases/download/v9.0.0/"
        name = updates.installer_name("9.0.0")
        return {"version": "9.0.0", "name": name,
                "installer": base + name,
                "checksums": base + "SHA256SUMS.txt", "size": len(data)}

    def test_download_verified_and_personal_data_preserved(self):
        data = b"test installer bytes"
        info = self.info(data)
        personal = Path(self.temp.name) / "api-key.dpapi"
        personal.write_bytes(b"keep")
        checksum = (hashlib.sha256(data).hexdigest() + "  " + info["name"]).encode()
        with patch.object(updates, "_request", side_effect=[io.BytesIO(checksum), io.BytesIO(data)]):
            result = updates.download(info)
        self.assertEqual(result.read_bytes(), data)
        self.assertEqual(personal.read_bytes(), b"keep")

    def test_bad_checksum_never_installs(self):
        data = b"installer"
        info = self.info(data)
        checksum = ("0" * 64 + "  " + info["name"]).encode()
        with patch.object(updates, "_request", side_effect=[io.BytesIO(checksum), io.BytesIO(data)]), patch.object(updates.subprocess, "Popen") as launch:
            with self.assertRaises(updates.UpdateError):
                updates.install(info)
            launch.assert_not_called()
        self.assertFalse(list(Path(self.temp.name).rglob("*.download")))

    def test_truncated_download_rejected(self):
        info = self.info(b"long installer")
        data = b"short"
        checksum = (hashlib.sha256(data).hexdigest() + "  " + info["name"]).encode()
        with patch.object(updates, "_request", side_effect=[io.BytesIO(checksum), io.BytesIO(data)]):
            with self.assertRaises(updates.UpdateError):
                updates.download(info)

    def test_foreign_asset_rejected(self):
        info = self.info(b"test")
        info["installer"] = "https://example.org/installer.exe"
        with self.assertRaises(updates.UpdateError):
            updates.download(info)

    def test_version_comparison(self):
        self.assertGreater(updates.version("v1.10.0"), updates.version("1.9.0"))
        with self.assertRaises(updates.UpdateError):
            updates.version("v2.0.0-beta")

    def test_legacy_lua_calls_packaged_app_and_uses_user_logs(self):
        from scripts.package_lua import package
        target = Path(self.temp.name) / "Srutilekha.lua"
        package(Path(__file__).resolve().parents[1] / "audio_to_srt.lua", target)
        text = target.read_text(encoding="utf-8")
        self.assertIn('local PYTHONW = APP_EXE', text)
        self.assertIn('local LOADER_PY = "--resolve"', text)
        self.assertIn('local DIALOG_PY = "--dialog"', text)
        self.assertNotIn('PROJECT_DIR .. SEP .. "logs"', text)

    def test_only_stable_newer_release_with_assets(self):
        data = b"test"
        info = self.info(data)
        release = {"tag_name": "v9.0.0", "body": "New release", "assets": [
            {"name": info["name"], "browser_download_url": info["installer"], "size": len(data)},
            {"name": "SHA256SUMS.txt", "browser_download_url": info["checksums"]}]}
        with patch.object(updates, "_request", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertEqual(updates.check()["version"], "9.0.0")
        release["prerelease"] = True
        with patch.object(updates, "_request", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertIsNone(updates.check())

    def test_installer_name_per_platform(self):
        with patch.object(updates.sys, "platform", "darwin"):
            self.assertEqual(updates.installer_name("9.0.0"), "Srutilekha-9.0.0-macOS.dmg")
        with patch.object(updates.sys, "platform", "win32"):
            self.assertEqual(updates.installer_name("9.0.0"), "Srutilekha-Setup-9.0.0.exe")

    def test_mac_ignores_release_without_dmg(self):
        base = "https://github.com/mahadeva112/Shrutilekha-SRT/releases/download/v9.0.0/"
        release = {"tag_name": "v9.0.0", "assets": [
            {"name": "Srutilekha-Setup-9.0.0.exe", "browser_download_url": base + "Srutilekha-Setup-9.0.0.exe"},
            {"name": "SHA256SUMS.txt", "browser_download_url": base + "SHA256SUMS.txt"}]}
        with patch.object(updates.sys, "platform", "darwin"), \
             patch.object(updates, "_request", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertIsNone(updates.check())

    def test_mac_install_opens_disk_image(self):
        with patch.object(updates.sys, "platform", "darwin"):
            data = b"dmg bytes"
            info = self.info(data)
            checksum = (hashlib.sha256(data).hexdigest() + "  " + info["name"]).encode()
            with patch.object(updates, "_request", side_effect=[io.BytesIO(checksum), io.BytesIO(data)]), \
                 patch.object(updates.subprocess, "Popen") as launch:
                target = updates.install(info)
        self.assertTrue(target.endswith("Srutilekha-9.0.0-macOS.dmg"))
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/open", target])


if __name__ == "__main__":
    unittest.main()
