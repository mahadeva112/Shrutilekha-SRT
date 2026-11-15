"""The popups Resolve opens use the app's WebView2 page, and fall back to Tk."""
import os
import unittest
from pathlib import Path
from unittest import mock

import dialog
import web_notice

UI = Path(__file__).resolve().parent.parent / "ui"


class WebNoticeTest(unittest.TestCase):
    def test_page_uses_the_app_stylesheet(self):
        html = (UI / "notice.html").read_text(encoding="utf-8")
        for asset in ("common.css", "notice.css", "common.js", "notice.js"):
            self.assertIn(asset, html)
            self.assertTrue((UI / asset).exists(), asset)

    def test_classic_ui_override_falls_back_to_tk(self):
        with mock.patch.dict(os.environ, {"SRUTILEKHA_CLASSIC_UI": "1"}):
            self.assertFalse(web_notice.show({"title": "x"}))

    def test_api_hands_the_notice_to_the_page(self):
        notice = {"title": "Open a project to begin", "steps": ["a"]}
        self.assertEqual(web_notice.Api(notice).initial(), notice)

    def test_stopped_run_opens_the_web_popup_with_the_friendly_notice(self):
        with mock.patch("web_notice.show", return_value=True) as show, \
             mock.patch("dialog._dark_window") as tk_window:
            dialog.alert_error("Srutilekha", "No project is open.")
        tk_window.assert_not_called()
        notice = show.call_args[0][0]
        self.assertEqual(notice["title"], "Open a project to begin")
        self.assertEqual(notice["kind"], "error")
        self.assertEqual(notice["details"], "No project is open.")

    def test_plain_alert_opens_the_web_popup(self):
        with mock.patch("web_notice.show", return_value=True) as show, \
             mock.patch("dialog._dark_window") as tk_window:
            dialog.alert("Captions placed", "42 cues added.")
        tk_window.assert_not_called()
        self.assertEqual(show.call_args[0][0]["kind"], "info")
        self.assertEqual(show.call_args[0][0]["button"], "OK")

    def test_web_failure_falls_back_to_tk(self):
        with mock.patch("web_notice.show", side_effect=RuntimeError), \
             mock.patch("dialog._dark_window", side_effect=SystemExit) as tk_window:
            with self.assertRaises(SystemExit):
                dialog.alert_error("Srutilekha", "No project is open.")
        tk_window.assert_called_once()


if __name__ == "__main__":
    unittest.main()
