"""선택 한도 24 패치: 왕복/검증, 다른 패치와 공존, 실제 게임 함수 에뮬레이션."""
import struct
import unittest
from pathlib import Path

import hotkey_patch
import minimap_patch
import selection_patch as sp

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'

UNIT, STRIDE = 0x775A38, 0x138
LOCAL = 0xB412CC
SEL_N, OLD_SEL = 0x80083C, 0x80083E
TMP_N = 0x766910
PSEL_N = 0x7F793C
FLAGS, LEADER, CUR_GROUP = 0xB412E4, 0xB412D0, 0xB412CE
TYPEPTR = 0x4FCD88
CMD_OBJ, CMD_BUF = 0x2200000, 0x2201000
STUB = 0x3000000
RET = STUB + 0xF00


class SelectionPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()
        cls.base = minimap_patch.build(cls.original, False, True, hotkeys=True)
        cls.wide = minimap_patch.build(cls.original, False, True, hotkeys=True, select24=True)

    # ── 파일 ────────────────────────────────────────────────
    def test_roundtrip_and_validation(self):
        under = hotkey_patch.strip(self.wide)
        self.assertTrue(sp.state(under))
        self.assertFalse(sp.state(hotkey_patch.strip(self.base)))
        self.assertEqual(sp.strip(under), hotkey_patch.strip(self.base))
        self.assertEqual(sp.apply(under), under)
        self.assertEqual(minimap_patch.underlying(self.wide), minimap_patch.underlying(self.base))
        self.assertEqual(minimap_patch.build(self.wide, False, True, True, False), self.base)
        self.assertEqual(minimap_patch.build(self.base, False, True, True, True), self.wide)
        self.assertTrue(hotkey_patch.state(self.wide))
        self.assertEqual(hotkey_patch._code_for(self.wide), hotkey_patch.CODE24)
        self.assertEqual(hotkey_patch._code_for(self.base), hotkey_patch.CODE)
        for at in (sp.SITES[0][0], sp.SITES[-1][0], len(under) - sp.RAW_SIZE + 3):
            bad = bytearray(under); bad[at] ^= 1
            with self.assertRaises(ValueError):
                sp.state(bytes(bad))

    def test_sites_do_not_overlap_and_match_builder(self):
        spans = sorted((o, o + len(a)) for o, a, b in sp.SITES)
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0)
        try:
            import build_selection_patch as b
            import build_hotkey_code
        except ImportError as e:
            self.skipTest(str(e))
        self.assertEqual(tuple(b.build()), sp.SITES)
        self.assertEqual(build_hotkey_code.assemble(n=24), hotkey_patch.CODE24)

    # ── 에뮬레이션 ──────────────────────────────────────────
    def _emu(self, image):
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX
        except ImportError as e:
            self.skipTest(str(e))
        img = pefile.PE(data=image).get_memory_mapped_image()
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, (len(img) + 0xFFF) & ~0xFFF)
        mu.mem_write(0x400000, img)
        mu.mem_map(0x2000000, 0x400000)
        mu.mem_map(STUB, 0x1000)
        mu.mem_write(RET, b'\xf4')
        calls = []
        # 게임 내부 함수 대체: 주소 -> 돌아가는 코드
        stubs = {
            0x4494C0: b'\xc3',                       # 명령 큐에 넣기 (버퍼는 아래에서 직접 읽음)
            0x4659E0: b'\xc2\x08\x00',               # 아래 정보 창 갱신
            0x49E400: b'\xc3',                       # 유닛 소리
            0x401110: b'\xb8\x00\x10\x00\x00\xc3',   # 부대 두 번 누르기 타이머
            0x401180: b'\xc3',
            0x43BAB0: b'\xc2\x08\x00',               # 죽은 유닛 선택 해제
            0x465460: b'\xc2\x10\x00',
            0x465FC0: b'\xc2\x04\x00',
        }
        for a, code in stubs.items():
            mu.mem_write(a, code)

        def hook(uc, addr, size, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            calls.append((addr, struct.unpack('<I', uc.mem_read(esp + 4, 4))[0], uc.reg_read(UC_X86_REG_ECX)))
        for a in stubs:
            mu.hook_add(UC_HOOK_CODE, hook, begin=a, end=a)
        # 명령 버퍼 (0xB411A4 -> 객체, 객체+0x44 -> 버퍼)
        mu.mem_write(0xB411A4, struct.pack('<I', CMD_OBJ))
        mu.mem_write(CMD_OBJ + 0x44, struct.pack('<I', CMD_BUF))
        mu.mem_write(LOCAL, b'\x01')
        info = 0x2100000
        for t in range(1, 10):
            mu.mem_write(TYPEPTR + t * 0x1C, struct.pack('<I', info + t * 0x100))
            mu.mem_write(info + t * 0x100 + 0x58, struct.pack('<h', 0x80))
            mu.mem_write(info + t * 0x100 + 0x40, struct.pack('<h', 1 if t == 5 else 0))

        def call(fn, *args, ecx=0):
            esp = 0x2080000 - 4 * (len(args) + 1)        # [복귀 주소][인자...]
            mu.mem_write(esp, struct.pack('<I', RET))
            for k, v in enumerate(args):
                mu.mem_write(esp + 4 + 4 * k, struct.pack('<I', v & 0xFFFFFFFF))
            mu.reg_write(UC_X86_REG_ESP, esp)
            mu.reg_write(UC_X86_REG_ECX, ecx)
            calls.clear()
            mu.emu_start(fn, RET, count=2000000)
            return mu.reg_read(UC_X86_REG_ESP) - esp, mu.reg_read(UC_X86_REG_EAX)

        def unit(uid, t=7, owner=1, hp=50, x=0, y=0, mobile=0, order=2):
            b = UNIT + uid * STRIDE
            mu.mem_write(b + 2, struct.pack('<H', mobile))
            mu.mem_write(b + 6, struct.pack('<H', order))
            mu.mem_write(b + 8, struct.pack('<h', hp))
            mu.mem_write(b + 0xE, struct.pack('<h', t))
            mu.mem_write(b + 0x10, bytes([owner]))
            mu.mem_write(b + 0x12, struct.pack('<hh', x, y))

        rd16 = lambda a, n=1: list(struct.unpack(f'<{n}h', mu.mem_read(a, 2 * n)))
        return mu, call, unit, rd16, calls

    def _sel(self, mu, ids, at=sp.LSEL):
        mu.mem_write(SEL_N, struct.pack('<h', len(ids)))
        mu.mem_write(at, struct.pack(f'<{sp.N}H', *(ids + [0] * (sp.N - len(ids)))))

    def test_group_save_and_recall_twenty_units_and_send(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        ids = list(range(100, 120))
        for i in ids:
            unit(i)
        self._sel(mu, ids)
        mu.mem_write(OLD_SEL + 24, b'\x5a\x5a')                     # 원래 목록 뒤 변수는 그대로여야 함
        self.assertEqual(call(0x4DC7F0, 3)[0], 4)                    # Ctrl+3
        g = sp.GROUPS + 1 * sp.PLAYER_GROUPS + 3 * sp.GROUP_STRIDE
        self.assertEqual(mu.mem_read(g, 1)[0], 20)
        self.assertEqual(rd16(g + 2, sp.N), ids + [0] * 4)
        self._sel(mu, [100])
        mu.mem_write(CUR_GROUP, b'\xff')
        call(0x4DC940, 3)                                            # 3
        self.assertEqual(rd16(SEL_N), [20])
        self.assertEqual(rd16(sp.LSEL, sp.N), ids + [0] * 4)
        self.assertEqual(bytes(mu.mem_read(OLD_SEL + 24, 2)), b'\x5a\x5a')
        flags = mu.mem_read(FLAGS, 0x6A6)
        self.assertEqual([i for i, f in enumerate(flags) if f and i], ids)   # 빈 칸(0)도 표시하는 건 원래 동작
        # 선택 명령 0x4002: [id][길이][개수][번호 20개]
        pkt = bytes(mu.mem_read(CMD_BUF, 5 + 40))
        self.assertEqual(struct.unpack('<HHB', pkt[:5]), (0x4002, 45, 20))
        self.assertEqual(list(struct.unpack('<20H', pkt[5:])), ids)

    def test_receive_selection_command_for_player(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        ids = list(range(200, 222))
        for i in ids:
            unit(i, owner=2)
        pkt = 0x2300000
        mu.mem_write(pkt, struct.pack('<HHB', 0x4002, 5 + 2 * len(ids), len(ids)) + struct.pack(f'<{len(ids)}H', *ids))
        mu.mem_write(0x7F7958 + 2 * 0x11E0, b'\x77' * 8)           # 원래 12칸 뒤 데이터
        delta, _ = call(0x4407E0, 2, pkt, 5 + 2 * len(ids))   # 명령 묶음 전체 길이
        self.assertEqual(delta, 4)
        p = sp.PSEL + 2 * 0x11E0
        self.assertEqual(rd16(PSEL_N + 2 * 0x11E0), [22])
        self.assertEqual(rd16(p, sp.N), ids + [0, 0])
        self.assertEqual(bytes(mu.mem_read(0x7F7958 + 2 * 0x11E0, 8)), b'\x77' * 8)
        self.assertEqual(bytes(mu.mem_read(0x7F793E + 2 * 0x11E0, 24)), bytes(24))   # 옛 자리는 안 씀

    def test_original_game_overflows_without_patch(self):
        """패치 안 한 PC가 13기 이상 선택 명령을 받으면 다른 데이터를 덮어쓴다 (멀티 경고의 근거)."""
        mu, call, unit, rd16, calls = self._emu(self.base)
        ids = list(range(200, 216))
        for i in ids:
            unit(i, owner=2)
        pkt = 0x2300000
        mu.mem_write(pkt, struct.pack('<HHB', 0x4002, 5 + 2 * len(ids), len(ids)) + struct.pack(f'<{len(ids)}H', *ids))
        mu.mem_write(0x7F7958 + 2 * 0x11E0, b'\x77' * 8)
        call(0x4407E0, 2, pkt, 5 + 2 * len(ids))
        self.assertNotEqual(bytes(mu.mem_read(0x7F7958 + 2 * 0x11E0, 8)), b'\x77' * 8)

    def test_portrait_click_removes_and_compacts(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        ids = list(range(300, 324))
        for i in ids:
            unit(i)
        self._sel(mu, ids)
        call(0x433BF0, 5, 1, 0)                                      # Shift+클릭: 6번째 초상화 제외
        self.assertEqual(rd16(SEL_N), [23])
        self.assertEqual(rd16(sp.LSEL, sp.N), ids[:5] + ids[6:] + [0])

    def test_drag_commit_copies_twenty_four(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        ids = list(range(400, 424))
        for i in ids:
            unit(i, t=7)
        mu.mem_write(TMP_N, struct.pack('<h', 24))
        mu.mem_write(sp.TSEL, struct.pack('<24H', *ids))
        call(0x432F30)
        self.assertEqual(rd16(SEL_N), [24])
        self.assertEqual(rd16(sp.LSEL, sp.N), ids)
        flags = mu.mem_read(FLAGS, 0x6A6)
        self.assertEqual([i for i, f in enumerate(flags) if f], ids)
        self.assertEqual(rd16(LEADER), [400])                        # 모두 같은 종류 -> 대표 유닛

    def test_formation_spacing_for_twenty_units(self):
        """같이 이동할 때(0x47C550) 무리별 간격 유지: 스택 배열을 넓혀도 프레임이 깨지지 않음."""
        for image, count in ((self.base, 12), (self.wide, 20)):
            mu, call, unit, rd16, calls = self._emu(image)
            psel = (sp.PSEL if image is self.wide else 0x7F793E) + 1 * 0x11E0
            mu.mem_write(0x5038D8, struct.pack('<I', 0x2310000))
            mu.mem_write(0x2310000, struct.pack('<I', 0x2310100))      # 그림 크기 0
            ids = list(range(500, 500 + count))
            pos = {}
            for k, i in enumerate(ids):
                cx, cy = (1000, 1000) if k % 2 else (6000, 6000)       # 두 무리
                pos[i] = (cx + 10 * k, cy + 7 * k)
                unit(i, x=pos[i][0], y=pos[i][1])
            mu.mem_write(PSEL_N + 0x11E0, struct.pack('<h', count))
            mu.mem_write(psel, struct.pack(f'<{count}H', *ids))
            delta, _ = call(0x47C550, 1, 3000 | (4000 << 16))
            self.assertEqual(delta, 4)
            for group in (ids[0::2], ids[1::2]):
                mx = sum(pos[i][0] for i in group) // len(group)
                my = sum(pos[i][1] for i in group) // len(group)
                for i in group:
                    got = rd16(UNIT + i * STRIDE + 0xD0, 2)
                    self.assertEqual(got, [3000 + pos[i][0] - mx, 4000 + pos[i][1] - my], (count, i))

    def test_panel_count_is_capped_at_twelve(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        for n, want in ((20, 12), (12, 12), (5, 5), (0, 0)):
            mu.mem_write(SEL_N, struct.pack('<h', n))
            self.assertEqual(call(sp.IMAGE + sp.STUB_OFFSET['eax'])[1], want)
            call(sp.IMAGE + sp.STUB_OFFSET['ecx'])
            from unicorn.x86_const import UC_X86_REG_ECX
            self.assertEqual(mu.reg_read(UC_X86_REG_ECX), want)

    def test_hotkey_period_selects_up_to_twenty_four(self):
        mu, call, unit, rd16, calls = self._emu(self.wide)
        mu.mem_write(0x4EC350, struct.pack('<I', STUB))              # GetKeyState -> 0
        mu.mem_write(STUB, b'\x31\xc0\xc2\x04\x00')
        mu.mem_write(0x4EC520, struct.pack('<I', STUB + 0x10))       # IME 비활성
        mu.mem_write(STUB + 0x10, b'\x31\xc0\xc3')
        for i in range(30, 60):
            unit(i, t=5, mobile=1)                                   # 쉬는 일꾼 30
        self._sel(mu, [])
        call(0x42EF90, 0xBE, 0)
        self.assertEqual(rd16(SEL_N), [24])
        self.assertEqual(rd16(sp.LSEL, sp.N), list(range(30, 54)))


if __name__ == '__main__':
    unittest.main()
