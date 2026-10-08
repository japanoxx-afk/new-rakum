from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from display_settings import WindowModeManager, read_section, update_section


class DisplayTests(unittest.TestCase):
    def test_section_isolation_and_insertion(self):
        original = '; comment\r\n[ddraw]\r\nwidth=800\r\n[other]\r\nwidth=42\r\n'
        updated = update_section(original, {'width': 1280, 'height': 720})
        self.assertEqual(read_section(updated), {'width': '1280', 'height': '720'})
        self.assertTrue(updated.endswith('[other]\r\nwidth=42\r\n'))
        self.assertTrue(updated.startswith('; comment\r\n'))

    def test_missing_section_and_duplicate_keys(self):
        self.assertEqual(read_section(update_section('[other]\nwidth=1', {'width': 0})), {'width': '0'})
        self.assertEqual(update_section('[ddraw]\nwidth=1\nwidth=2', {'width': 0}).count('width='), 1)
        with self.assertRaises(ValueError):
            update_section('[ddraw]\n[ddraw]\n', {'width': 0})

    def test_atomic_backup_filters_and_speed_preservation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, 'ddraw.ini')
            Path(root, 'ddraw.dll').touch()
            original = b'[ddraw]\nrenderer=direct3d9\nshader=Lanczos\nd3d9_filter=2\nmaxgameticks=0\nmaxfps=-1\n'
            path.write_bytes(original)
            manager = WindowModeManager(root)
            self.assertEqual(manager.read_settings()['shader'], 'Bicubic')
            ok, message = manager.apply_settings(True, 1280, 720, shader='Lanczos', renderer='direct3d9')
            self.assertTrue(ok, message)
            self.assertEqual(next(Path(root).glob('*.bak_*')).read_bytes(), original)
            values = read_section(path.read_text())
            self.assertEqual(values['d3d9_filter'], '3')
            self.assertEqual(values['maxgameticks'], '0')
            self.assertEqual(values['maxfps'], '-1')
            self.assertEqual(values['devmode'], 'false')
            self.assertEqual(manager.read_settings()['shader'], 'Lanczos')
            before = path.read_bytes()
            with patch('display_settings.os.replace', side_effect=OSError('locked')):
                self.assertFalse(manager.apply_settings(True, 0, 0, shader='Bicubic')[0])
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(Path(root).glob('*.tmp')))

    def test_invalid_settings_do_not_write(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, 'ddraw.ini')
            Path(root, 'ddraw.dll').touch()
            original = b'[ddraw]\nwidth=800\n[rhakmu]\nwidth=640\n'
            path.write_bytes(original)
            manager = WindowModeManager(root)
            for width, height in ((-1, 720), (0, 720), (9000, 9000), (1280, 720)):
                self.assertFalse(manager.apply_settings(True, width, height, shader='Bicubic')[0])
                self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(Path(root).glob('*.bak_*')))

    def test_running_game_blocks_ui_apply(self):
        from unittest.mock import Mock
        import launcher
        app = Mock()
        with patch.object(launcher, '_run_ps', return_value=(0, 'RUNNING')), patch.object(launcher.messagebox, 'showwarning'):
            launcher.App._on_apply_winmode(app)
        app.winmode.apply_settings.assert_not_called()


if __name__ == '__main__':
    unittest.main()
