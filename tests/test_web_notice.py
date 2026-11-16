"""Popups Resolve opens use the app's WebView2 page; without WebView2, a
native Windows message box says the same thing."""
import sys
import unittest
from pathlib import Path
from unittest import mock

import dialog
import web_notice
import web_ui

UI = Path(__file__).resolve().parent.parent / "ui"


class FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_winreg(entries):
    """A winreg stand-in holding {(hive, path): pv}."""
    module = mock.Mock(HKEY_LOCAL_MACHINE="HKLM", HKEY_CURRENT_USER="HKCU")

    def open_key(hive, path):
        if (hive, path) not in entries:
            raise FileNotFoundError(path)
        return FakeKey(entries[(hive, path)])
    module.OpenKey.side_effect = open_key
    module.QueryValueEx.side_effect = lambda key, name: (key.values, 1)
    return module


CLIENTS = "Microsoft\\EdgeUpdate\\Clients\\" + web_ui.WEBVIEW2_CLIENT


class WebNoticeTest(unittest.TestCase):
    def test_page_uses_the_app_stylesheet(self):
        html = (UI / "notice.html").read_text(encoding="utf-8")
        for asset in ("common.css", "notice.css", "common.js", "notice.js"):
            self.assertIn(asset, html)
            self.assertTrue((UI / asset).exists(), asset)

    def test_no_webview2_means_no_web_popup(self):
        with mock.patch("web_ui.available", return_value=False):
            self.assertFalse(web_notice.show({"title": "x"}))

    def test_api_hands_the_notice_to_the_page(self):
        notice = {"title": "Open a project to begin", "steps": ["a"]}
        self.assertEqual(web_notice.Api(notice).initial(), notice)

    def test_stopped_run_opens_the_web_popup_with_the_friendly_notice(self):
        with mock.patch("web_notice.show", return_value=True) as show, \
             mock.patch("web_ui.message_box") as box:
            dialog.alert_error("Srutilekha", "No project is open.")
        box.assert_not_called()
        notice = show.call_args[0][0]
        self.assertEqual(notice["title"], "Open a project to begin")
        self.assertEqual(notice["kind"], "error")
        self.assertEqual(notice["details"], "No project is open.")

    def test_plain_alert_opens_the_web_popup(self):
        with mock.patch("web_notice.show", return_value=True) as show, \
             mock.patch("web_ui.message_box") as box:
            dialog.alert("Captions placed", "42 cues added.")
        box.assert_not_called()
        self.assertEqual(show.call_args[0][0]["kind"], "info")
        self.assertEqual(show.call_args[0][0]["button"], "OK")

    def test_web_failure_falls_back_to_a_message_box(self):
        with mock.patch("web_notice.show", side_effect=RuntimeError), \
             mock.patch("web_ui.available", return_value=True), \
             mock.patch("web_ui.message_box") as box:
            dialog.alert_error("Srutilekha", "No project is open.")
        title, text = box.call_args[0]
        self.assertEqual(title, "Open a project to begin")
        self.assertIn("1. Open your project in DaVinci Resolve.", text)
        self.assertIn("Details:\nNo project is open.", text)
        self.assertTrue(box.call_args.kwargs["error"])
        self.assertNotIn(web_ui.WEBVIEW2_DOWNLOAD, text)

    def test_without_webview2_the_box_says_how_to_get_it(self):
        with mock.patch("web_ui.available", return_value=False), \
             mock.patch("web_ui.message_box") as box:
            dialog.alert("Captions placed", "42 cues added.")
        title, text = box.call_args[0]
        self.assertEqual(title, "Captions placed")
        self.assertTrue(text.startswith("42 cues added."))
        self.assertIn(web_ui.WEBVIEW2_DOWNLOAD, text)
        self.assertFalse(box.call_args.kwargs["error"])

    def test_missing_runtime_notice_names_the_installer_and_the_download(self):
        with mock.patch("web_ui.available", return_value=False), \
             mock.patch("web_ui.message_box") as box:
            web_notice.tell(web_notice.MISSING_RUNTIME)
        title, text = box.call_args[0]
        self.assertIn("WebView2", title)
        self.assertIn("installer again", text)
        self.assertEqual(text.count(web_ui.WEBVIEW2_DOWNLOAD), 1)


@unittest.skipUnless(sys.platform == "win32", "Windows registry")
class RuntimeCheckTest(unittest.TestCase):
    def version(self, entries):
        with mock.patch.dict("sys.modules", winreg=fake_winreg(entries)):
            return web_ui.runtime_version()

    def test_per_machine_runtime(self):
        self.assertEqual(self.version({("HKLM", "SOFTWARE\\WOW6432Node\\" + CLIENTS): "131.0.2903.70"}),
                         "131.0.2903.70")

    def test_per_user_runtime(self):
        self.assertEqual(self.version({("HKCU", "Software\\" + CLIENTS): "130.0.1.0"}), "130.0.1.0")

    def test_removed_or_absent_runtime(self):
        self.assertEqual(self.version({("HKLM", "SOFTWARE\\WOW6432Node\\" + CLIENTS): "0.0.0.0",
                                       ("HKCU", "Software\\" + CLIENTS): ""}), "")
        self.assertEqual(self.version({}), "")

    def test_available_needs_the_runtime_not_just_pywebview(self):
        with mock.patch.dict("sys.modules", webview=mock.Mock()):
            with mock.patch("web_ui.runtime_version", return_value=""):
                self.assertFalse(web_ui.available())
            with mock.patch("web_ui.runtime_version", return_value="131.0.2903.70"):
                self.assertTrue(web_ui.available())


if __name__ == "__main__":
    unittest.main()
