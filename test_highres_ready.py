"""1280×720 준비: ddraw.dll 자동 설치, 권한 없음/지원 안 하는 DLL 일 때 원본 해상도로 계속."""
import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME_SRC = Path(os.environ.get('RHAKMU_DLLS', '/mnt/user-data/uploads/RhakMu'))


def _ready(path):
    try:
        import launcher
    except Exception as e:  # tkinter 없는 환경
        raise unittest.SkipTest(str(e))
    fake = types.SimpleNamespace(winmode=None)
    return launcher.App._highres_ready(fake, Path(path))


class HighresReadyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name)
        import viewport_patch
        names = list(viewport_patch.manifest()['dll_hashes'])
        if not all((GAME_SRC / n).is_file() for n in names):
            self.skipTest('원본 게임 DLL 없음')
        for n in names:
            shutil.copy2(GAME_SRC / n, self.game / n)

    def tearDown(self):
        os.chmod(self.game, stat.S_IRWXU)
        self.tmp.cleanup()

    def test_installs_cnc_ddraw_when_missing(self):
        ok, why = _ready(self.game)
        self.assertTrue(ok, why)
        self.assertEqual((self.game / 'ddraw.dll').read_bytes(), (HERE / 'cnc_ddraw' / 'ddraw.dll').read_bytes())
        self.assertTrue((self.game / 'ddraw.ini').is_file())

    def test_keeps_existing_ini(self):
        (self.game / 'ddraw.ini').write_text('[ddraw]\nwidth=1920\n')
        ok, _ = _ready(self.game)
        self.assertTrue(ok)
        self.assertIn('1920', (self.game / 'ddraw.ini').read_text())

    def test_falls_back_without_permission(self):
        from unittest import mock
        with mock.patch('launcher.shutil.copy2', side_effect=PermissionError):
            ok, why = _ready(self.game)
        self.assertFalse(ok)
        self.assertIn('권한', why)

    def test_falls_back_on_unsupported_dll(self):
        (self.game / 'GameCtrl.dll').write_bytes(b'other version')
        ok, why = _ready(self.game)
        self.assertFalse(ok)
        self.assertIn('GameCtrl.dll', why)


if __name__ == '__main__':
    unittest.main()
