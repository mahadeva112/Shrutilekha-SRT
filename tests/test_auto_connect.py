import unittest
from unittest.mock import patch
import app

class AutoConnectTests(unittest.TestCase):
    def test_default_app_delegates_to_resident_helper(self):
        with patch('sys.argv',['app.py']),patch('tray_helper.request_open') as request:
            app.main()
        request.assert_called_once()

    def test_tray_mode_does_not_open_home_or_workflow(self):
        with patch('sys.argv',['app.py','--tray']),patch('tray_helper.run') as run,patch('tray_helper.request_open') as request:
            app.main()
        run.assert_called_once();request.assert_not_called()

    def test_bridge_workflow_bypasses_helper(self):
        with patch('sys.argv',['app.py','--bridge-run']),patch('resolve_bridge.run_workflow') as run,patch('tray_helper.request_open') as request:
            app.main()
        run.assert_called_once();request.assert_not_called()
