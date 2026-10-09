import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import command_cadence_installer as installer
import command_cadence_trial as trial

SOURCE = Path(__file__).parent / 'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'


@unittest.skipUnless(SOURCE.exists(), 'Known reference game not available')
class InstallerTests(unittest.TestCase):
    def test_apply_restore_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Rhakmu.exe'
            original = SOURCE.read_bytes()
            target.write_bytes(original)
            with patch.object(installer.viewport_patch, 'ensure_closed') as closed:
                installer.apply(target, True)
                self.assertEqual(target.read_bytes(), trial.transform(original))
                self.assertEqual(next(Path(directory).glob('*.bak_cadence_*')).read_bytes(), original)
                self.assertIn('이미', installer.apply(target, True))
                installer.apply(target, False)
                self.assertEqual(target.read_bytes(), original)
                self.assertGreaterEqual(closed.call_count, 5)

    def test_running_game_blocks_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Rhakmu.exe'
            original = SOURCE.read_bytes()
            target.write_bytes(original)
            with patch.object(installer.viewport_patch, 'ensure_closed', side_effect=RuntimeError('running')):
                with self.assertRaises(RuntimeError):
                    installer.apply(target, True)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
