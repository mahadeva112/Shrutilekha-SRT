import tkinter as tk
import unittest
from unittest.mock import patch

import app
from resolve_bridge import BridgeError


class AutoConnectTests(unittest.TestCase):
    def run_home(self, result=None, error=None):
        original = tk.Tk
        def create_root():
            root = original()
            root.withdraw()
            original_destroy = root.destroy
            def destroy():
                for job in root.tk.call('after', 'info'):
                    root.after_cancel(job)
                original_destroy()
            root.destroy = destroy
            root.after(800, root.destroy)
            return root
        with patch('sys.argv', ['app.py']), patch('tkinter.Tk', side_effect=create_root), \
             patch('credentials.get_key', return_value='test-only'), \
             patch('release_updater.check', return_value=None), \
             patch('resolve_bridge.probe_connection', return_value=result, side_effect=error), \
             patch('subprocess.Popen') as launch:
            app.main()
            return launch

    def test_ready_opens_captions_once_without_click(self):
        launch = self.run_home(result={'version':'21.1.1'})
        launch.assert_called_once()
        self.assertIn('--bridge-run', launch.call_args.args[0])

    def test_missing_bridge_waits_without_opening_or_error_popup(self):
        self.run_home(error=BridgeError('Resolve bridge is not responding')).assert_not_called()

    def test_existing_caption_workflow_is_not_duplicated(self):
        self.run_home(error=BridgeError('Another Srutilekha operation is running')).assert_not_called()
