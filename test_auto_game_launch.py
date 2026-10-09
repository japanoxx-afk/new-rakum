import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch
import launcher
import peer_address_patch

class AutoLaunchTests(unittest.TestCase):
    def test_path_saved_and_patch_applied_without_radmin_mode(self):
        source = pathlib.Path(launcher.DEFAULT_GAME_DIR, launcher.PATCH_EXE).read_bytes()
        with tempfile.TemporaryDirectory() as root:
            folder = pathlib.Path(root)
            (folder / launcher.GAME_EXE).touch()
            game = folder / launcher.PATCH_EXE
            game.write_bytes(peer_address_patch.transform(source, False))
            for name in ('iCARUS.dll','GameCtrl.dll','ddraw.dll'):
                (folder/name).write_bytes(pathlib.Path(launcher.DEFAULT_GAME_DIR,name).read_bytes())
            app = Mock()
            app.gamedir_var.get.return_value = str(folder / launcher.GAME_EXE)
            app.cfg = {}
            app.base_dir = root
            app.radmin_only.get.return_value = False
            with patch.object(launcher, '_run_ps', return_value=(0, '')), patch.object(launcher, 'save_config') as save:
                launcher.App._prepare_game_launch(app)
                save.assert_called_once()
            self.assertEqual(app.cfg['game_dir'], str(folder))
            self.assertTrue(peer_address_patch.state(game.read_bytes()))
            self.assertEqual(game.read_bytes()[0xeb420:0xeb420+len(peer_address_patch.CODE)], peer_address_patch.CODE)

    def test_preflight_failure_never_launches(self):
        app = Mock()
        app._prepare_game_launch.side_effect = ValueError('invalid image')
        with patch.object(launcher.messagebox, 'showerror'), patch.object(launcher.subprocess, 'Popen') as spawn, patch.object(launcher.HostsManager, 'set_game_host') as hosts:
            launcher.App._set_host_and_launch(app, '127.0.0.1')
            spawn.assert_not_called()
            hosts.assert_not_called()

if __name__ == '__main__':
    unittest.main()
