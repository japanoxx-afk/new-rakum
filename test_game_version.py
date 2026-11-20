"""게임판 맞춤: 1.000d (원본/런처 패치본) 인정, 다른 판은 백업 후 1.000d 로 교체."""
import tempfile
import unittest
from pathlib import Path

import game_version as gv
import minimap_patch

VERSION_SITE = 0x233A9          # mov word ptr [ecx+0x9A0], 0x3EB  (66 C7 81 A0 09 00 00 EB 03)


class GameVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.original = gv.bundled()
        except FileNotFoundError as e:
            raise unittest.SkipTest(str(e))

    def older(self):
        """1.000 처럼 버전 1000 을 보내는 실행 파일 (크기·다른 바이트는 같음)."""
        d = bytearray(self.original)
        self.assertEqual(bytes(d[VERSION_SITE:VERSION_SITE + 9]), bytes.fromhex('66c781a0090000eb03'))
        d[VERSION_SITE + 7] = 0xE8
        return bytes(d)

    def test_original_and_every_patched_variant_are_1000d(self):
        self.assertTrue(gv.is_1000d(self.original))
        for high in (False, True):
            for rally in (False, True):
                for hot in (False, True):
                    for wide in (False, True):
                        built = minimap_patch.build(self.original, high, rally, hot, wide)
                        self.assertTrue(gv.is_1000d(built), (high, rally, hot, wide))

    def test_other_versions_and_broken_files_are_not(self):
        self.assertFalse(gv.is_1000d(self.older()))
        self.assertFalse(gv.is_1000d(self.original[:-100]))
        self.assertFalse(gv.is_1000d(b'MZ' + bytes(1000)))
        with self.assertRaises(ValueError):                                   # 기존 패치 과정도 거부
            minimap_patch.build(self.older(), False, True, True, True)

    def test_ensure_replaces_with_backup_and_keeps_1000d(self):
        with tempfile.TemporaryDirectory() as root:
            exe = Path(root, 'Rhakmu.exe')
            old = self.older()
            exe.write_bytes(old)
            note = gv.ensure(exe)
            self.assertIn('1.000d', note)
            self.assertEqual(exe.read_bytes(), self.original)
            backups = list(Path(root).glob('Rhakmu.exe.bak_not1000d_*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), old)
            self.assertEqual(gv.ensure(exe), '')                              # 이미 1.000d
            patched = minimap_patch.build(self.original, False, True, True, True)
            exe.write_bytes(patched)
            self.assertEqual(gv.ensure(exe), '')
            self.assertEqual(exe.read_bytes(), patched)                       # 패치본은 그대로


if __name__ == '__main__':
    unittest.main()
