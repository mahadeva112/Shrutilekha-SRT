import os
import sys
import unittest
from unittest import mock

import web_home
import web_ui


class WebHomeTest(unittest.TestCase):
    def test_initial_state_never_exposes_saved_key(self):
        with mock.patch("credentials.get_key", return_value="secret-key"), \
             mock.patch("tray_helper.startup_enabled", return_value=False):
            state = web_home.Api(False).initial()
        self.assertTrue(state["hasKey"])
        self.assertNotIn("secret-key", repr(state))

    def test_empty_test_uses_saved_key_without_returning_it(self):
        client = mock.Mock()
        with mock.patch("credentials.get_key", return_value="secret-key"), \
             mock.patch("elevenlabs.client.ElevenLabs", return_value=client) as factory:
            result = web_home.Api(False).test_key("")
        factory.assert_called_once_with(api_key="secret-key", timeout=15)
        self.assertTrue(result["ok"])
        self.assertNotIn("secret-key", repr(result))

    def test_invalid_key_is_reported_not_raised(self):
        with mock.patch("credentials.save_key", side_effect=ValueError):
            result = web_home.Api(False).save_key("bad key")
        self.assertFalse(result["ok"])

    def test_no_webview2_opens_no_window(self):
        webview = mock.Mock()
        with mock.patch("web_ui.available", return_value=False), \
             mock.patch.dict("sys.modules", webview=webview):
            self.assertFalse(web_home.run())
        webview.create_window.assert_not_called()

    def test_window_errors_reach_the_caller(self):
        # app.py turns them into a notice; swallowing them left nothing on screen.
        webview = mock.Mock()
        webview.start.side_effect = RuntimeError("WebView2 failed to start")
        with mock.patch("web_ui.available", return_value=True), \
             mock.patch("credentials.get_key", return_value="k"), \
             mock.patch.dict("sys.modules", webview=webview):
            with self.assertRaises(RuntimeError):
                web_home.run()

    def test_classic_ui_switch_is_gone(self):
        with mock.patch.dict(os.environ, {"SRUTILEKHA_CLASSIC_UI": "1"}), \
             mock.patch("web_ui.runtime_version", return_value="130.0.0.0"):
            self.assertEqual(web_ui.available(), sys.platform == "win32")


if __name__ == "__main__":
    unittest.main()
