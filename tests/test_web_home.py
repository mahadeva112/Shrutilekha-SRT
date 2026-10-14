import os
import unittest
from unittest import mock

import web_home


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

    def test_classic_ui_override_falls_back_to_tk(self):
        with mock.patch.dict(os.environ, {"SRUTILEKHA_CLASSIC_UI": "1"}):
            self.assertFalse(web_home.run())


if __name__ == "__main__":
    unittest.main()
