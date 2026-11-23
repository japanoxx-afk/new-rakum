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



class FakeRegistry:
    """winreg 흉내 (HKLM\\SOFTWARE\\TriggerSoft\\RhakMu 한 키)."""
    HKEY_LOCAL_MACHINE, KEY_READ, KEY_WRITE, KEY_WOW64_32KEY, REG_SZ, REG_DWORD, REG_BINARY = 1, 2, 4, 0x200, 1, 4, 3

    def __init__(self, values=None, exists=True):
        self.values, self.exists, self.opened = dict(values or {}), exists, []

    def OpenKey(self, root, name, reserved, access):
        self.opened.append((root, name, access))
        if not self.exists:
            raise FileNotFoundError(name)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)


class OfficialPatchTests(unittest.TestCase):
    """Patch1003.exe 를 깔지 않아도 런처가 같은 상태로 맞춘다."""

    def test_registry_version_keeps_the_value_kind(self):
        R = FakeRegistry
        for before, after, changed in (((1000, R.REG_DWORD), (1003, R.REG_DWORD), True),
                                       (("1000", R.REG_SZ), ("1003", R.REG_SZ), True),
                                       ((1003, R.REG_DWORD), (1003, R.REG_DWORD), False),
                                       (("1003", R.REG_SZ), ("1003", R.REG_SZ), False),
                                       ((b"x", R.REG_BINARY), (b"x", R.REG_BINARY), False)):
            reg = R({"GameVer": before, "GamePath": ("C:\\x", R.REG_SZ)})
            self.assertEqual(gv.ensure_registry(reg), changed, before)
            self.assertEqual(reg.values["GameVer"], after)
            self.assertEqual(reg.values["GamePath"], ("C:\\x", R.REG_SZ))
            self.assertEqual(reg.opened, [(R.HKEY_LOCAL_MACHINE, r"SOFTWARE\TriggerSoft\RhakMu",
                                           R.KEY_READ | R.KEY_WRITE | R.KEY_WOW64_32KEY)])

    def test_registry_is_not_created_when_missing(self):
        reg = FakeRegistry(exists=False)
        self.assertFalse(gv.ensure_registry(reg))
        reg = FakeRegistry({"GamePath": ("C:\\x", 1)})
        self.assertFalse(gv.ensure_registry(reg))
        self.assertNotIn("GameVer", reg.values)

    def test_fresh_install_gets_exe_and_registry(self):
        try:
            original = gv.bundled()
        except FileNotFoundError as e:
            self.skipTest(str(e))
        older = bytearray(original)
        older[VERSION_SITE + 7] = 0xE8                                        # 버전 1000 을 보내는 판
        with tempfile.TemporaryDirectory() as root:
            reg = FakeRegistry({"GameVer": (1000, FakeRegistry.REG_DWORD)})
            self.assertEqual(gv.apply_official_patch(root, reg), "")          # Rhakmu.exe 없음: 아무것도 안 함
            self.assertEqual(reg.values["GameVer"][0], 1000)
            exe = Path(root, "Rhakmu.exe")
            exe.write_bytes(older)
            note = gv.apply_official_patch(root, reg)
            self.assertIn("Patch1003", note)
            self.assertEqual(exe.read_bytes(), original)
            self.assertEqual(reg.values["GameVer"], (1003, FakeRegistry.REG_DWORD))
            self.assertEqual(gv.apply_official_patch(root, reg), "")          # 두 번째는 할 일 없음
            self.assertEqual(len(list(Path(root).glob("Rhakmu.exe.bak_not1000d_*"))), 1)


if __name__ == "__main__":
    unittest.main()
