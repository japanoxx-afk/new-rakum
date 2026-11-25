"""패키지 모드 실행 준비 (scenario_mode): 레지스트리 Pack 값과 시나리오 맵 자리."""
import tempfile
import struct
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


class SingleModePatchTests(unittest.TestCase):
    """싱글(패키지) 실행용 수정: CD 키 확인 건너뛰기·경기 시간 표시·경기 끝에 종료. 싱글 실행 때만 들어가고 보통 실행에서는 빠진다."""

    @classmethod
    def setUpClass(cls):
        exe = Path(__file__).resolve().parent / "game_backup" / "Rhakmu.exe"
        if not exe.is_file():
            raise unittest.SkipTest("game_backup/Rhakmu.exe 없음")
        cls.original = exe.read_bytes()

    def test_patch_only_for_the_single_launch(self):
        import minimap_patch
        import package_mode_patch as pm
        original = self.original
        for site, before, after in pm.SITES + pm.RETIRED:
            self.assertEqual(original[site:site + len(before)], before)
            self.assertEqual(len(before), len(after))
        self.assertEqual(original[pm.SITE - 12:pm.SITE - 7], bytes.fromhex("e834c7f4ff"))      # call 0x425E90 (CD 키 확인)
        self.assertEqual(pm.SITE + 0x400000 + 6 + 0xB5, 0x4D981E)                               # 두 점프 모두 같은 곳으로
        normal = minimap_patch.build(original, False)
        single = minimap_patch.build(original, False, package=True)
        self.assertFalse(pm.state(minimap_patch.underlying(normal)))
        self.assertTrue(pm.current(minimap_patch.underlying(single)))
        changed = {i for i in range(len(normal)) if normal[i] != single[i]}
        allowed = {i for site, before, _ in pm.SITES for i in range(site, site + len(before))}
        self.assertTrue(changed and changed <= allowed)
        self.assertEqual(minimap_patch.build(single, False), normal)                            # 다음 보통 실행에서 되돌아감
        self.assertEqual(minimap_patch.build(normal, False, package=True), single)
        self.assertEqual(minimap_patch.build(original, True, package=True),
                         minimap_patch.build(minimap_patch.build(original, True), True, package=True))
        bad = bytearray(original)
        bad[pm.SITE] ^= 1
        with self.assertRaises(ValueError):
            pm.state(bad)
        mixed = bytearray(original)                                                             # 알 수 없는 묶음
        mixed[pm.TIMER_SHOW[0]] = pm.TIMER_SHOW[2][0]
        with self.assertRaises(ValueError):
            pm.state(mixed)

    def test_upgrades_from_earlier_test_builds(self):
        """v0.9099 시험판(CD 키만)·v0.9100 시험판(경기 끝에서 바로 종료)을 알아보고 지금 판으로 맞추거나 걷어낸다."""
        import minimap_patch
        import package_mode_patch as pm
        every = pm.SITES + pm.RETIRED
        self.assertEqual(len(pm.LEGACY), 2)
        for used in pm.LEGACY:
            old = bytearray(minimap_patch.build(self.original, False))
            for k in used:
                site, before, after = every[k]
                old[site:site + len(after)] = after
            self.assertTrue(pm.state(minimap_patch.underlying(bytes(old))))
            self.assertFalse(pm.current(minimap_patch.underlying(bytes(old))))
            self.assertEqual(minimap_patch.build(bytes(old), False), minimap_patch.build(self.original, False))
            self.assertEqual(minimap_patch.build(bytes(old), False, package=True),
                             minimap_patch.build(self.original, False, package=True))

    def test_timer_code_matches_source(self):
        import package_mode_patch as pm
        try:
            from keystone import Ks, KS_ARCH_X86, KS_MODE_32
        except ImportError as e:
            self.skipTest(str(e))
        site, before, after = pm.TIMER_VALUE
        code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(pm.TIMER_SOURCE, addr=0x400000 + site)[0])
        self.assertEqual(code.ljust(len(before), b"\x90"), after)
        self.assertEqual(0x400000 + site + len(before), 0x4653AC)

    def _clock(self, image, countdown, multiplayer, seconds):
        """시계의 분·초 계산 구간(0x465344..0x4653AC)을 실행해 (분, 초) 를 돌려준다."""
        from test_production_split_patch import _emulator, SCRATCH
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP
        mu = _emulator(image)
        ebp = SCRATCH + 0x8000
        mu.reg_write(UC_X86_REG_EBP, ebp)
        mu.reg_write(UC_X86_REG_ESP, ebp - 0x100)
        mu.mem_write(ebp - 8, struct.pack("<i", countdown))
        mu.mem_write(0xB412CB, bytes([multiplayer]))
        mu.mem_write(0xB4074C, struct.pack("<I", seconds))
        mu.emu_start(0x465344, 0x4653AC, count=1000)
        return struct.unpack("<ii", mu.mem_read(ebp - 0x18, 8))[::-1]

    def test_clock_shows_game_time_in_single_games(self):
        import minimap_patch
        import package_mode_patch as pm
        normal = minimap_patch.build(self.original, False)
        single = minimap_patch.build(self.original, False, package=True)
        self.assertEqual(single[pm.TIMER_SHOW[0]], 0xEB)                  # 멀티가 아니어도 시계를 그림
        for image in (normal, single):                                     # 멀티플레이: 원래와 같음 (늘 경기 시간)
            self.assertEqual(self._clock(image, 100, 1, 754), (12, 34))
            self.assertEqual(self._clock(image, 45, 1, 754), (12, 34))
        self.assertEqual(self._clock(normal, 100, 0, 754), (1, 40))        # 원래: 싱글에서는 카운트다운 값(없으면 100)
        self.assertEqual(self._clock(single, 100, 0, 754), (12, 34))       # 싱글: 카운트다운이 없으면 경기 시간
        self.assertEqual(self._clock(single, 100, 0, 3600 * 3 + 5), (180, 5))
        self.assertEqual(self._clock(single, 75, 0, 754), (1, 15))         # 트리거 카운트다운이 돌면 그 값
        self.assertEqual(self._clock(single, 0, 0, 754), (0, 0))

    def test_leaving_the_score_screen_exits_with_the_relaunch_code(self):
        """경기 끝의 메뉴 다시 만들기(점수 화면)는 그대로, 점수 화면에서 메인 메뉴로 갈 때 ExitProcess(EXIT_CODE)."""
        import minimap_patch
        import package_mode_patch as pm
        from test_production_split_patch import _emulator, SCRATCH
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP
        single = minimap_patch.build(self.original, False, package=True)
        self.assertEqual(single[0xD5813:0xD5824], self.original[0xD5813:0xD5824])     # 경기 끝 -> 0x423850 (점수 화면) 그대로
        self.assertEqual(self.original[0x11EAD:0x11EAF], bytes.fromhex("7411"))       # 커스텀([0x6E167E] == 0)이면 0x411EC0 으로
        mu = _emulator(single)
        stub = SCRATCH + 0x4000
        mu.mem_write(0x4EC26C, struct.pack("<I", stub))                               # ExitProcess 수입 자리
        seen = []

        def hook(uc, address, size, user):
            esp = uc.reg_read(UC_X86_REG_ESP)
            seen.append(struct.unpack("<II", uc.mem_read(esp, 8)))
            uc.emu_stop()
        mu.hook_add(UC_HOOK_CODE, hook, begin=stub, end=stub)
        from unicorn.x86_const import UC_X86_REG_EBP
        mu.reg_write(UC_X86_REG_ESP, SCRATCH + 0x8000)
        mu.reg_write(UC_X86_REG_EBP, SCRATCH + 0x9000)
        mu.mem_write(0x6E167E, bytes([0]))
        mu.emu_start(0x411EA1, 0x411F59, count=100)
        self.assertEqual(seen, [(0x411EC0 + 11, pm.EXIT_CODE)])
