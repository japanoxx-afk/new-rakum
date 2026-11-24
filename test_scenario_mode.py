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


if __name__ == "__main__":
    unittest.main()
