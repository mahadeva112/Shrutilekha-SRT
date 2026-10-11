import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import credentials
from settings_ui import ApiSettingsPanel

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, SRUTILEKHA_USER_DIR=self.scratch.name)
        self.env.start()
        self.root=tk.Tk()
        self.root.withdraw()
        self.root.bind('<Return>', lambda e: None)
        self.root.bind('<Escape>', lambda e: None)
        self.bindings={k:self.root.bind(k) for k in ('<Return>','<Escape>')}
    def tearDown(self):
        self.root.destroy()
        self.env.stop()
        self.scratch.cleanup()
    def test_save_keeps_host_and_restores_shortcuts(self):
        panel=ApiSettingsPanel(self.root)
        self.assertIs(panel.winfo_toplevel(),self.root)
        self.assertNotEqual(self.root.bind('<Return>'),self.bindings['<Return>'])
        panel.value.set('test-key-not-a-real-credential')
        panel.save()
        self.assertEqual(credentials.get_key(),'test-key-not-a-real-credential')
        self.assertTrue(self.root.winfo_exists())
        for key, binding in self.bindings.items():
            self.assertEqual(self.root.bind(key),binding)
    def test_back_does_not_save_edits_and_cancels_poll(self):
        credentials.save_key('old-test-key')
        panel=ApiSettingsPanel(self.root)
        panel.value.set('unsaved-test-key')
        job=panel._poll_job
        panel.close()
        self.assertEqual(credentials.get_key(),'old-test-key')
        self.assertNotIn(job,self.root.tk.call('after','info'))
    def test_remove_and_connection_result_stay_inside_panel(self):
        credentials.save_key('old-test-key')
        panel=ApiSettingsPanel(self.root)
        panel.remove()
        self.assertFalse(credentials.get_key())
        panel.test()
        self.assertEqual(panel.status.get(),'Paste your API key first.')
        self.assertTrue(panel.winfo_exists())
    def test_reveal_toggle_and_disabled_connection_action(self):
        panel=ApiSettingsPanel(self.root)
        panel._toggle_reveal()
        self.assertEqual(panel.entry.cget('show'),'')
        panel._toggle_reveal()
        self.assertEqual(panel.entry.cget('show'),'•')
        with patch.object(panel.test_button,'command') as command:
            panel.test_button.configure(state='disabled')
            panel.test_button._invoke()
            command.assert_not_called()
            panel.test_button.configure(state='normal')
            panel.test_button._invoke()
            command.assert_called_once()

    def test_failed_save_keeps_panel_open(self):
        panel=ApiSettingsPanel(self.root)
        with patch('credentials.save_key',side_effect=OSError('test failure')):
            panel.save()
        self.assertTrue(panel.winfo_exists())
        self.assertIn('Could not save',panel.status.get())

if __name__=='__main__':
    unittest.main()
