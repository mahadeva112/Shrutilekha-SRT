import tempfile
from pathlib import Path
import unittest
import threading
from unittest.mock import patch, Mock

import tray_helper as tray
from resolve_bridge import BridgeError


class TrayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch('tray_helper.user_dir', return_value=Path(self.temp.name))
        env.start(); self.addCleanup(env.stop)

    def test_script_click_opens_once_and_next_click_reopens(self):
        controller = tray.TrayController()
        with patch.object(controller, 'active_caption', return_value=False), \
             patch('tray_helper.resolve_identity', return_value=(1, 100)), \
             patch('tray_helper.launch_signal', return_value=('click-a',101)) as signal, \
             patch('tray_helper.probe_connection', return_value={'session':'server'}), \
             patch('tray_helper.launch') as launch:
            launch.return_value.poll.return_value = 0
            controller.tick(); controller.tick()
            launch.assert_called_once_with('--bridge-run')
            signal.return_value = ('click-b',102)
            controller.tick()
            self.assertEqual(launch.call_count,2)

    def test_existing_caption_is_raised_without_duplicate(self):
        controller = tray.TrayController()
        with patch.object(controller, 'active_caption', return_value=True), patch('tray_helper.launch') as launch:
            self.assertTrue(controller.open())
        self.assertTrue((Path(self.temp.name)/'raise-caption.flag').exists())
        launch.assert_not_called()

    def test_idle_and_stale_markers_do_not_contact_resolve(self):
        controller = tray.TrayController()
        with patch('tray_helper.resolve_identity', return_value=None), patch('tray_helper.probe_connection') as probe:
            controller.tick();probe.assert_not_called()
        with patch('tray_helper.resolve_identity', return_value=(1,200)), \
             patch('tray_helper.launch_signal', return_value=('old',100)), patch('tray_helper.probe_connection') as probe:
            controller.tick();probe.assert_not_called()

    def test_open_before_script_does_not_block_later_auto_launch(self):
        controller = tray.TrayController()
        with patch.object(controller,'active_caption',return_value=False), \
             patch('tray_helper.launch') as launch, patch('tray_helper.probe_connection',side_effect=BridgeError('waiting')) as probe:
            self.assertFalse(controller.open())
            launch.assert_called_once_with('--home')
            probe.side_effect=None;probe.return_value={'session':'ready'}
            self.assertTrue(controller.open(automatic=True))
            self.assertEqual(launch.call_args.args,('--bridge-run',))

    def test_commands_are_atomic_and_startup_toggle_preserves_other_values(self):
        tray.queue_command('open')
        folder=Path(self.temp.name)/'tray-commands'
        self.assertEqual(len(list(folder.glob('*.json'))),1)
        self.assertFalse(list(folder.glob('*.tmp')))
        import winreg
        key=Mock();key.__enter__=Mock(return_value=key);key.__exit__=Mock(return_value=False)
        with patch.object(winreg,'CreateKey',return_value=key), \
             patch.object(winreg,'SetValueEx') as write, patch.object(winreg,'DeleteValue') as delete:
            tray.set_startup(True);write.assert_called_once()
            self.assertEqual(write.call_args.args[1], 'Srutilekha')
            tray.set_startup(False);delete.assert_called_once_with(key,'Srutilekha')
            self.assertTrue((Path(self.temp.name)/'tray-startup-disabled.flag').exists())

    def test_single_helper_lock_is_released_on_exit(self):
        with tray.mailbox_lock(Path(self.temp.name)/'tray.lock'):
            with patch('tray_helper.make_icon') as icon:
                tray.run();icon.assert_not_called()
        icon=Mock();icon.run.return_value=None
        with patch('tray_helper.make_icon',return_value=icon):tray.run()
        icon.run.assert_called_once()

    def test_quit_helper_leaves_caption_job_running(self):
        controller=tray.TrayController()
        controller.child=Mock()
        stop=threading.Event()
        icon=Mock()
        with patch('pystray.Icon',return_value=icon) as constructor:
            tray.make_icon(controller,stop)
        menu=constructor.call_args.kwargs['menu']
        list(menu)[-1](icon)
        self.assertTrue(stop.is_set())
        icon.stop.assert_called_once()
        controller.child.terminate.assert_not_called()
        controller.child.kill.assert_not_called()
