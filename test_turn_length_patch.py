"""멀티 턴 길이 (turn_length_patch) — 게임 코드 그대로 Unicorn 으로 실행."""
import itertools
import struct
import unittest

import minimap_patch
import turn_length_patch as tl
from test_production_split_patch import _emulator, EXE, SCRATCH

NET = SCRATCH + 0x1000
PERIOD, MIN_DEPTH = 0xB412B8, 0x7F77A4


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()


class FileTests(Base):
    def test_sites_and_roundtrip(self):
        o = self.original
        self.assertEqual(o[0xD7B96:0xD7B9D], bytes.fromhex("b905000000f7f1"))      # mov ecx,5; div ecx (프레임 % 5)
        self.assertEqual(o[0x4A98B:0x4A990], bytes.fromhex("83fa037c16"))          # cmp edx,3; jl (속도 되돌림 기준)
        self.assertEqual(tl.state(o), 5)
        self.assertTrue(tl.current(o, 5))
        for frames in tl.CHOICES:
            on = tl.transform(o, frames)
            self.assertEqual(tl.state(on), frames)
            self.assertTrue(tl.current(on, frames))
            self.assertEqual(on[tl.RECOVER_SITE], 3 if frames == 5 else 2)
            self.assertEqual(tl.transform(on, 5), o)
            self.assertEqual([i for i in range(len(o)) if o[i] != on[i]],
                             [] if frames == 5 else [tl.RECOVER_SITE, tl.FRAMES_SITE])
        with self.assertRaises(ValueError):
            tl.transform(o, 4)
        bad = bytearray(o)
        bad[tl.FRAMES_SITE] = 7
        with self.assertRaises(ValueError):
            tl.state(bad)
        old = bytearray(o)                               # 예전 99ms 실험판: 턴만 3, 기준은 그대로
        old[tl.FRAMES_SITE] = 3
        self.assertEqual(tl.state(old), 3)
        self.assertFalse(tl.current(old, 3))
        self.assertEqual(tl.transform(bytes(old), 5), o)

    def test_every_build_carries_the_chosen_length(self):
        for hr, sel, rec, package in itertools.product((False, True), repeat=4):
            base = minimap_patch.build(self.original, hr, True, True, sel, rec, rec, False, True, True, package)
            self.assertEqual(tl.state(minimap_patch.underlying(base)), 5)          # 인자를 안 주면 원래 값
            for frames in (3, 2):
                built = minimap_patch.build(self.original, hr, True, True, sel, rec, rec, False, True, True, package, frames)
                self.assertTrue(tl.current(minimap_patch.underlying(built), frames))
                self.assertEqual([i for i in range(len(base)) if base[i] != built[i]], [tl.RECOVER_SITE, tl.FRAMES_SITE])
                self.assertEqual(minimap_patch.build(built, hr, True, True, sel, rec, rec, False, True, True, package), base)
                self.assertEqual(minimap_patch.build(base, hr, True, True, sel, rec, rec, False, True, True, package, frames), built)

    def test_replay_playback_gets_the_recorded_length(self):
        import hotkey_patch
        import replay_record_patch as rrp
        import smart_cast_patch
        for turn in (5, 3, 2, 1):                        # 1 = 싱글(커스텀) 경기 리플레이: Game_Multi 쪽은 원래 값으로
            built = minimap_patch.build(self.original, False, True, True, False, True, False, True, True, True, False, turn)
            under = hotkey_patch.strip(smart_cast_patch.strip(built))
            self.assertTrue(rrp.plays(under))
            self.assertEqual(rrp.play_turn(under), turn)
            self.assertEqual(tl.state(minimap_patch.underlying(built)), turn if turn in tl.CHOICES else 5)
            live = minimap_patch.build(built, False, True, True, False, True, False, False, True, True, False, 3)
            self.assertEqual(rrp.play_turn(hotkey_patch.strip(smart_cast_patch.strip(live))), 5)   # 기록 설치는 늘 같은 내용
            self.assertEqual(live, minimap_patch.build(self.original, False, True, True, False, True, False, False, True, True, False, 3))


class LoopTests(Base):
    def _turn_frames(self, image, upto=13):
        """Game_Multi 의 '이 프레임에 턴을 보내는가' (0x4D7B8F..) 를 프레임마다 실행."""
        mu = _emulator(image)
        out = []
        for frame in range(upto):
            mu.mem_write(0xB412B4, struct.pack("<I", frame))
            mu.emu_start(0x4D7B8F, 0x4D7B9F, count=20)
            from unicorn.x86_const import UC_X86_REG_EDX
            if mu.reg_read(UC_X86_REG_EDX) == 0:
                out.append(frame)
        return out

    def test_turn_is_sent_every_n_frames(self):
        self.assertEqual(self._turn_frames(minimap_patch.build(self.original, False)), [0, 5, 10])
        self.assertEqual(self._turn_frames(minimap_patch.build(self.original, False, turn_frames=3)), [0, 3, 6, 9, 12])
        self.assertEqual(self._turn_frames(minimap_patch.build(self.original, False, turn_frames=2)), [0, 2, 4, 6, 8, 10, 12])

    def _period(self, image, depth, period, ready=True):
        """턴 처리의 속도 조절(0x44A950..0x44A9A6): 모두 준비됐고 가장 적게 쌓인 대기 턴 수가 depth 일 때 프레임 시간."""
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_ESP
        mu = _emulator(image)
        mu.reg_write(UC_X86_REG_EBP, SCRATCH + 0x8000)
        mu.reg_write(UC_X86_REG_ESP, SCRATCH + 0x7000)
        mu.mem_write(SCRATCH + 0x8000 - 4, struct.pack("<I", NET))
        mu.mem_write(NET + 0x4A, struct.pack("<HH", 3, 3))
        mu.mem_write(MIN_DEPTH, struct.pack("<H", depth))
        mu.mem_write(PERIOD, struct.pack("<I", period))
        mu.emu_start(0x44A950, 0x44A9A6, count=50)
        return struct.unpack("<I", mu.mem_read(PERIOD, 4))[0]

    def test_speed_recovers_with_two_queued_turns_when_turns_are_short(self):
        normal = minimap_patch.build(self.original, False)
        short = minimap_patch.build(self.original, False, turn_frames=3)
        self.assertEqual(self._period(normal, 3, 40), 39)        # 원래: 3턴 이상 쌓였을 때만 빨라짐
        self.assertEqual(self._period(normal, 2, 40), 40)
        self.assertEqual(self._period(short, 3, 40), 39)
        self.assertEqual(self._period(short, 2, 40), 39)         # 턴이 짧으면 2턴 여유로도 되돌림 (느려진 채 머물지 않게)
        self.assertEqual(self._period(short, 1, 40), 40)
        self.assertEqual(self._period(short, 2, 33), 33)         # 33ms 아래로는 안 내려감


if __name__ == '__main__':
    unittest.main()
