import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import credentials
from dpi import attach
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

    def test_connection_layout_fits_compact_and_studio_windows_at_native_scales(self):
        context = attach(self.root, factor=1, watch=False)
        for scale in (.8, 1, 1.25, 1.5, 2):
            context.rescale(scale, (0, 0, 3840, 2160))
            for width, height in ((620, 500), (620, 550), (1040, 720), (1180, 820)):
                with self.subTest(scale=scale, size=(width, height)):
                    self.root.geometry(f'{width}x{height}')
                    self.root.deiconify()
                    panel = ApiSettingsPanel(self.root)
                    try:
                        self.root.update()
                        card = panel._connection_card
                        space = panel._connection_space
                        self.assertGreaterEqual(card.winfo_y(), 0)
                        self.assertLessEqual(card.winfo_y()+card.winfo_height(), space.winfo_height()+2)
                        self.assertLessEqual(card.winfo_x()+card.winfo_width(), space.winfo_width()+2)
                        body = card.body
                        for child in body.winfo_children():
                            if child.winfo_ismapped():
                                self.assertLessEqual(child.winfo_y()+child.winfo_height(), body.winfo_height()+2)
                        self.assertEqual(panel.entry.cget('show'), '•')
                        self.assertEqual(panel.connection_badge.text, 'Not configured')
                    finally:
                        panel.close()

if __name__=='__main__':
    unittest.main()
