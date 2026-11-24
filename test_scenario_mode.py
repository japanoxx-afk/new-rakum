"""패키지 모드 실행 준비 (scenario_mode): 레지스트리 Pack 값과 시나리오 맵 자리."""
import tempfile
import unittest
from pathlib import Path

import scenario_mode as sm
from test_game_version import FakeRegistry


class Registry(FakeRegistry):
    def CreateKeyEx(self, root, name, reserved, access):
        self.opened.append((root, name, access))
        self.exists = True
        return self

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class PackTests(unittest.TestCase):
    def test_enable_and_restore_every_previous_state(self):
        R = Registry
        for values, exists, before in (({"Pack": (0, R.REG_DWORD)}, True, 0), ({}, True, None), ({}, False, None),
                                       ({"Pack": (1, R.REG_DWORD)}, True, 1), ({"Pack": ("1", R.REG_SZ)}, True, None)):
            reg = R(dict(values, GamePath=("C:\\x", R.REG_SZ)), exists)
            self.assertEqual(sm.get_pack(reg), before)
            self.assertEqual(sm.enable(reg), before)
            self.assertEqual(reg.values["Pack"], (1, R.REG_DWORD))
            self.assertEqual(reg.values["GamePath"], ("C:\\x", R.REG_SZ))           # 다른 값은 그대로
            sm.restore(before, reg)
            self.assertEqual(sm.get_pack(reg), before)
            if before is None:
                self.assertNotIn("Pack", reg.values)
            for root, name, access in reg.opened:
                self.assertEqual((root, name), (R.HKEY_LOCAL_MACHINE, r"SOFTWARE\TriggerSoft\RhakMu"))
                self.assertTrue(access & R.KEY_WOW64_32KEY)


class MapTests(unittest.TestCase):
    def test_install_keeps_foreign_files_and_remove_deletes_only_ours(self):
        with tempfile.TemporaryDirectory() as root:
            game = Path(root)
            first, second = game / "a.rkm", game / "b.rkm"
            first.write_bytes(b"map one")
            second.write_bytes(b"map two")
            folder = sm.scenario_dir(game)
            self.assertEqual(folder, game / "Data" / "Scenario")
            folder.mkdir(parents=True)
            (folder / "Scenario-1-0.rkm").write_bytes(b"real mission")              # 원래 있던 미션은 건드리지 않음
            written = sm.install_maps(game, first)
            self.assertEqual(len(written), len(sm.STAGES) * len(sm.SIDES) - 1)
            self.assertNotIn("Scenario-1-0.rkm", written)
            self.assertEqual((folder / "Scenario-1-0.rkm").read_bytes(), b"real mission")
            self.assertEqual((folder / "Scenario-0-0.rkm").read_bytes(), b"map one")
            self.assertEqual(sorted(sm.install_maps(game, second)), sorted(written))    # 다시 넣으면 우리 것만 바뀜
            self.assertEqual((folder / "Scenario-0-1.rkm").read_bytes(), b"map two")
            self.assertEqual((folder / "Scenario-1-0.rkm").read_bytes(), b"real mission")
            self.assertEqual(sorted(sm.remove_maps(game)), sorted(written))
            self.assertEqual([p.name for p in folder.iterdir()], ["Scenario-1-0.rkm"])
            self.assertEqual(sm.remove_maps(game), [])
            with self.assertRaises(FileNotFoundError):
                sm.install_maps(game, game / "none.rkm")

    def test_remove_cleans_up_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as root:
            game = Path(root)
            src = game / "a.rkm"
            src.write_bytes(b"m")
            sm.install_maps(game, src)
            sm.remove_maps(game)
            self.assertFalse(sm.scenario_dir(game).exists())


class CdKeyTests(unittest.TestCase):
    """패키지 모드의 CD 키 확인 건너뛰기: 싱글 메뉴 실험 실행 때만 들어가고, 보통 실행으로 빌드하면 빠진다."""

    def test_patch_only_for_the_experimental_launch(self):
        import minimap_patch
        import package_mode_patch as pm
        exe = Path(__file__).resolve().parent / "game_backup" / "Rhakmu.exe"
        if not exe.is_file():
            self.skipTest("game_backup/Rhakmu.exe 없음")
        original = exe.read_bytes()
        self.assertEqual(original[pm.SITE:pm.SITE + 6], pm.ORIGINAL)
        self.assertEqual(original[pm.SITE - 12:pm.SITE - 7], bytes.fromhex("e834c7f4ff"))      # call 0x425E90 (CD 키 확인)
        self.assertEqual(pm.SITE + 0x400000 + 6 + 0xB5, 0x4D981E)                               # 두 점프 모두 같은 곳으로
        normal = minimap_patch.build(original, False)
        single = minimap_patch.build(original, False, package=True)
        self.assertFalse(pm.state(minimap_patch.underlying(normal)))
        self.assertTrue(pm.state(minimap_patch.underlying(single)))
        self.assertEqual([i for i in range(len(normal)) if normal[i] != single[i]], [pm.SITE, pm.SITE + 1])
        self.assertEqual(minimap_patch.build(single, False), normal)                            # 다음 보통 실행에서 되돌아감
        self.assertEqual(minimap_patch.build(normal, False, package=True), single)
        self.assertEqual(minimap_patch.build(original, True, package=True),
                         minimap_patch.build(minimap_patch.build(original, True), True, package=True))
        bad = bytearray(original)
        bad[pm.SITE] ^= 1
        with self.assertRaises(ValueError):
            pm.state(bad)


if __name__ == "__main__":
    unittest.main()
