"""단축키 확장 패치: 왕복/검증, 다른 패치와 공존, 실제 키 처리 함수(0x42EF90) 에뮬레이션."""
import struct
import unittest
from pathlib import Path

import hotkey_patch as h
import minimap_patch
import smart_cast_patch


def build(*args, **kwargs):
    """실행용 파일에서 맨 뒤 섹션(.scast, 마법 순차 시전)을 걷어낸 것 — 이 시험이 보는 섹션이 맨 뒤에 오게."""
    return smart_cast_patch.strip(minimap_patch.build(*args, **kwargs))


HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'

UNIT, STRIDE = 0x775A38, 0x138
LOCAL = 0xB412CC
SEL_N, SEL = 0x80083C, 0x80083E
FLAGS, LEADER, CUR_GROUP = 0xB412E4, 0xB412D0, 0xB412CE
GROUPS = 0x106A6C0
TYPEPTR = 0x4FCD88
WORKER, SOLDIER, ARCHER, BUILDING_T = 5, 7, 8, 9
STUB = 0x3000000
RET_ADDR = STUB + 0x100


class HotkeyPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        original = EXE.read_bytes()
        cls.base = build(original, False, True, hotkeys=False)
        cls.patched = build(original, False, True, hotkeys=True)

    def test_roundtrip_and_validation(self):
        self.assertFalse(h.state(self.base))
        self.assertTrue(h.state(self.patched))
        self.assertEqual(h.apply(self.patched), self.patched)
        self.assertEqual(h.strip(self.patched), self.base)
        self.assertEqual(h.apply(self.patched, False), self.base)
        self.assertEqual(len(self.patched), len(self.base) + h.SECTION_SIZE)
        for at in (h.SITE + 2, len(self.base) + 5, len(self.base) + len(h.CODE) + 1):
            bad = bytearray(self.patched); bad[at] ^= 1
            with self.assertRaises(ValueError):
                h.state(bytes(bad))

    def test_other_patch_checks_still_see_the_same_file(self):
        self.assertEqual(self.patched, h.apply(self.base))
        self.assertEqual(minimap_patch.underlying(self.patched), minimap_patch.underlying(self.base))
        # 이미 패치된 파일에서 다시 만들어도 같은 결과 (설정 끄기/켜기 왕복)
        self.assertEqual(build(self.patched, False, True, hotkeys=False), self.base)
        self.assertEqual(build(self.base, False, True, hotkeys=True), self.patched)
        for high in (False, True):
            p = build(self.patched, high, True, hotkeys=True)
            self.assertTrue(h.state(p))
            self.assertEqual(h.strip(p), build(self.base, high, True, hotkeys=False))
        # 런처의 명령 지연 패치 시그니처(66 C7 40 48 ?? 00 E8)가 새 코드에 생기면 안 됨
        def sites(d):
            return [i for i in range(len(d) - 7) if d[i] == 0x66 and d[i + 1] == 0xC7 and d[i + 2] == 0x40
                    and d[i + 3] == 0x48 and d[i + 5] == 0 and d[i + 6] == 0xE8]
        self.assertEqual(len(sites(self.patched)), 3)

    def test_code_is_position_independent_build(self):
        try:
            import build_hotkey_code
        except ImportError as e:
            self.skipTest(str(e))
        self.assertEqual(build_hotkey_code.assemble(), h.CODE)

    # ── 에뮬레이션 ──────────────────────────────────────────
    def _emu(self):
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX
        except ImportError as e:
            self.skipTest(str(e))
        img = pefile.PE(data=self.patched).get_memory_mapped_image()
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, (len(img) + 0xfff) & ~0xfff)
        mu.mem_write(0x400000, img)
        mu.mem_map(0x2000000, 0x200000)
        mu.mem_map(STUB, 0x1000)
        env = {'keys': set(), 'ime': 0, 'calls': []}
        # 외부 함수 대체: GetKeyState / classIME::IsActive
        mu.mem_write(STUB, b'\xc2\x04\x00')          # GetKeyState: ret 4
        mu.mem_write(STUB + 0x10, b'\xc3')           # IsActive: ret
        mu.mem_write(RET_ADDR, b'\xf4')
        mu.mem_write(0x4EC350, struct.pack('<I', STUB))
        mu.mem_write(0x4EC520, struct.pack('<I', STUB + 0x10))
        # 게임 내부 함수 대체 (네트워크 전송·정보창·기존 단축키·부대 저장)
        stubs = {0x447BD0: b'\xc3', 0x4659E0: b'\xc2\x08\x00', 0x465FC0: b'\xc2\x04\x00', 0x4DC7F0: b'\xc3'}
        for a, code in stubs.items():
            mu.mem_write(a, code)

        def hook(uc, addr, size, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            arg = lambda k: struct.unpack('<I', uc.mem_read(esp + 4 * k, 4))[0]
            if addr == STUB:
                uc.reg_write(UC_X86_REG_EAX, 0xFF80 if arg(1) in env['keys'] else 0)
            elif addr == STUB + 0x10:
                uc.reg_write(UC_X86_REG_EAX, env['ime'])
            elif addr in stubs:
                env['calls'].append((addr, arg(1), arg(2)))
        for a in [STUB, STUB + 0x10, *stubs]:
            mu.hook_add(UC_HOOK_CODE, hook, begin=a, end=a)

        # 게임 상태
        mu.mem_write(LOCAL, b'\x01')
        info = 0x2100000
        for t, cls_ in ((WORKER, 1), (SOLDIER, 0), (ARCHER, 0), (BUILDING_T, 0)):
            mu.mem_write(info + t * 0x100 + 0x40, struct.pack('<h', cls_))
            mu.mem_write(TYPEPTR + t * 0x1C, struct.pack('<I', info + t * 0x100))

        def unit(uid, t, owner=1, order=2, hp=50, building=0, hidden=0):
            b = UNIT + uid * STRIDE
            mu.mem_write(b + 2, struct.pack('<H', building))   # +2: 건물 분류 (0 = 일반 유닛)
            mu.mem_write(b + 6, struct.pack('<H', order))
            mu.mem_write(b + 8, struct.pack('<h', hp))
            mu.mem_write(b + 0xE, struct.pack('<h', t))
            mu.mem_write(b + 0x10, bytes([owner]))
            mu.mem_write(b + 0x28, struct.pack('<I', hidden << 24))

        def press(key, *held):
            env['keys'] = set(held)
            env['calls'].clear()
            esp = 0x2080000
            for v in (0, key, RET_ADDR):              # lParam, wParam, 복귀 주소
                esp -= 4; mu.mem_write(esp, struct.pack('<I', v))
            mu.reg_write(UC_X86_REG_ESP, esp)
            mu.emu_start(0x42EF90, RET_ADDR, count=500000)
            self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
            return list(env['calls'])

        def selection():
            n = struct.unpack('<h', mu.mem_read(SEL_N, 2))[0]
            ids = list(struct.unpack('<12H', mu.mem_read(SEL, 24)))
            return n, ids

        def set_selection(ids):
            mu.mem_write(SEL_N, struct.pack('<h', len(ids)))
            mu.mem_write(SEL, struct.pack('<12H', *(ids + [0] * (12 - len(ids)))))

        def group(n):
            g = GROUPS + 1 * 0xD0 + n * 0x1A
            return mu.mem_read(g, 1)[0], list(struct.unpack('<12H', mu.mem_read(g + 2, 24)))

        return mu, env, unit, press, selection, set_selection, group

    def test_period_selects_idle_workers_only(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        unit(10, WORKER)                    # 쉬는 일꾼
        unit(11, WORKER, order=0x2006)      # 채취 중
        unit(12, WORKER, owner=2)           # 상대 일꾼
        unit(13, SOLDIER)                   # 군사
        unit(14, WORKER, hp=0)              # 죽음
        unit(15, WORKER, hidden=1)          # 금광 안
        unit(16, WORKER, building=1)        # 건물 분류
        unit(17, WORKER, order=0x1002)      # 사망 처리 중
        unit(20, WORKER)                    # 쉬는 일꾼
        set_selection([13])
        calls = press(0xBE)
        self.assertEqual(selection(), (2, [10, 20] + [0] * 10))
        flags = mu.mem_read(FLAGS, 0x6A6)
        self.assertEqual([i for i, f in enumerate(flags) if f], [10, 20])
        self.assertEqual(struct.unpack('<h', mu.mem_read(LEADER, 2))[0], 10)
        self.assertEqual(mu.mem_read(CUR_GROUP, 1)[0], 0xFF)
        self.assertEqual([c[0] for c in calls], [0x447BD0, 0x4659E0])
        self.assertEqual(calls[1][1:], (UNIT + 10 * STRIDE, 1))

    def test_period_caps_at_twelve_and_keeps_selection_when_none(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        set_selection([13])
        unit(13, SOLDIER)
        self.assertEqual(press(0xBE), [])
        self.assertEqual(selection()[0], 1)
        for i in range(30, 45):
            unit(i, WORKER)
        press(0xBE)
        self.assertEqual(selection(), (12, list(range(30, 42))))

    def test_f2_selects_military_and_ctrl_f2_is_original(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        unit(10, WORKER)
        unit(11, SOLDIER, order=0x2003)
        unit(12, ARCHER)
        unit(13, SOLDIER, owner=3)
        unit(14, BUILDING_T, building=1)
        calls = press(0x71)
        self.assertEqual(selection(), (2, [11, 12] + [0] * 10))
        self.assertEqual(struct.unpack('<h', mu.mem_read(LEADER, 2))[0], 0)   # 종류가 섞이면 0
        self.assertEqual(calls[-1][1:], (UNIT, 1))
        set_selection([10])
        calls = press(0x71, 0x11)                                              # Ctrl+F2
        self.assertEqual(selection()[0], 1)
        self.assertNotIn(0x447BD0, [c[0] for c in calls])

    def test_shift_number_adds_to_group(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        for i, t in ((40, SOLDIER), (41, SOLDIER), (50, ARCHER)):
            unit(i, t)
        unit(51, SOLDIER, hp=0)
        g3 = GROUPS + 0xD0 + 3 * 0x1A
        mu.mem_write(g3, bytes([2, 0]) + struct.pack('<12H', 50, 51, *[0] * 10))
        set_selection([40, 41, 50])
        press(0x33, 0x10)                                                      # Shift+3
        self.assertEqual(group(3), (3, [50, 40, 41] + [0] * 9))
        press(0x34, 0x10)                                                      # Shift+4 (빈 부대)
        self.assertEqual(group(4), (3, [40, 41, 50] + [0] * 9))
        self.assertEqual(selection()[0], 3)                                    # 선택은 그대로
        calls = press(0x35)                                                    # Shift 없이: 원래 경로
        self.assertEqual(group(5)[0], 0)
        self.assertEqual([c[0] for c in calls], [0x465FC0])
        calls = press(0x36, 0x10, 0x11)                                        # Ctrl+Shift: 원래 부대 저장
        self.assertEqual(group(6)[0], 0)
        self.assertEqual(calls[0][:2], (0x4DC7F0, 6))

    def test_group_never_exceeds_twelve(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        for i in range(60, 80):
            unit(i, SOLDIER)
        g2 = GROUPS + 0xD0 + 2 * 0x1A
        mu.mem_write(g2, bytes([10, 0]) + struct.pack('<12H', *range(60, 70), 0, 0))
        set_selection(list(range(65, 77)))
        press(0x32, 0x10)
        self.assertEqual(group(2), (12, list(range(60, 72))))

    def test_blocked_while_chatting_paused_or_menu(self):
        mu, env, unit, press, selection, set_selection, group = self._emu()
        unit(10, WORKER)
        set_selection([])
        env['ime'] = 1
        self.assertEqual([c[0] for c in press(0xBE)], [0x465FC0])
        self.assertEqual(selection()[0], 0)
        env['ime'] = 0
        mu.mem_write(0xB40749, b'\x01')
        press(0xBE); self.assertEqual(selection()[0], 0)
        mu.mem_write(0xB40749, b'\x00')
        mu.mem_write(0x801EAC, struct.pack('<I', 1))
        press(0xBE); self.assertEqual(selection()[0], 0)
        mu.mem_write(0x801EAC, struct.pack('<I', 0))
        press(0xBE); self.assertEqual(selection()[0], 1)


if __name__ == '__main__':
    unittest.main()
