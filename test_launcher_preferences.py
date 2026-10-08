import json
import os
from pathlib import Path
import tempfile
import shutil
import time
import unittest
from unittest.mock import patch, Mock
import launcher


class PreferencesTests(unittest.TestCase):
    def test_migration_and_folder_independent_save(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'LOCALAPPDATA': root}):
            old = Path(root, 'old')
            old.mkdir()
            (old / launcher.CONFIG_FILE).write_text(json.dumps({'last_server_ip': '26.1.2.3', 'game_dir': 'test'}))
            cfg = launcher.load_config(str(old))
            self.assertEqual(cfg['last_server_ip'], '26.1.2.3')
            launcher.save_config(str(old), cfg)
            self.assertEqual(launcher.load_config(str(Path(root, 'new'))), cfg)
            cfg['last_server_ip'] = '26.4.5.6'
            launcher.save_config(str(old), cfg)
            self.assertEqual(launcher.load_config(str(old)), cfg)

    def test_hidden_server_and_reap_before_restart(self):
        proc = Mock()
        proc.poll.return_value = None
        with patch.object(launcher, 'is_server_running', return_value=False), \
             patch.object(launcher.HostsManager, 'apply_ip'), \
             patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)), \
             patch.object(launcher.subprocess, 'Popen', return_value=proc) as spawn:
            server = launcher.ServerManager('.')
            self.assertTrue(server.start()[0])
            self.assertIn('--server', spawn.call_args.args[0])
            self.assertEqual(spawn.call_args.kwargs['creationflags'], 0x08000000)
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertFalse(server.start()[0])
            self.assertTrue(server.stop()[0])
            proc.wait.assert_called_once_with(timeout=3)
            self.assertFalse(server.running)

    def test_existing_server_not_replaced(self):
        with patch.object(launcher, 'is_server_running', return_value=True), patch.object(launcher.subprocess, 'Popen') as spawn:
            self.assertFalse(launcher.ServerManager('.').start()[0])
            spawn.assert_not_called()

    def test_saved_ip_skips_dialog(self):
        app = Mock()
        app.saved_ip_var.get.return_value = '26.1.2.3'
        app.cfg = {'last_server_ip': '26.1.2.3'}
        app._save_server_ip.return_value = True
        with patch.object(launcher, 'fix_radmin_priority', return_value=(True, '')), patch.object(launcher, 'is_server_running', return_value=False):
            launcher.App._on_multi_play(app)
        app._ask_server_ip_and_launch.assert_not_called()
        app._set_host_and_launch.assert_called_once_with('26.1.2.3', multiplayer=True)

    @unittest.skipUnless(os.environ.get('RHAKMU_TEST_EXE'), 'requires built executable')
    def test_real_frozen_server_start_stop_restart(self):
        self.assertFalse(launcher.is_server_running(), 'Do not test against an existing server')
        with tempfile.TemporaryDirectory() as root:
            exe = str(Path(root, 'launcher.exe'))
            shutil.copyfile(os.environ['RHAKMU_TEST_EXE'], exe)
            # Integrated releases must ignore a stale external server override.
            Path(root, 'server.py').write_text("raise RuntimeError('STALE_EXTERNAL_SERVER')\n", encoding='utf-8')
            server = launcher.ServerManager(root)
            with patch.object(launcher.sys, 'frozen', True, create=True), patch.object(launcher.sys, 'executable', exe), patch.object(launcher.HostsManager, 'apply_ip'):
                try:
                    for _ in range(2):
                        self.assertTrue(server.start()[0])
                        deadline = time.monotonic() + 15
                        while not launcher.is_server_running(timeout=0.1) and time.monotonic() < deadline:
                            time.sleep(0.1)
                        self.assertTrue(launcher.is_server_running())
                        self.assertTrue(Path(root, 'server-console.log').exists())
                        self.assertTrue(server.stop()[0])
                        self.assertFalse(launcher.is_server_running())
                finally:
                    if server.running:
                        server.stop()


if __name__ == '__main__':
    unittest.main()
