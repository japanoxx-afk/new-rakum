"""같은 생산 건물 여러 개에 생산·연구를 나눠 맡기기 (Rhakmu.exe 1.000d) — 게임 코드 그대로 Unicorn 으로 실행.

  production_split_patch: 명령 0x4008 (0x447CF0) 의 건물 번호를 선택 중 가장 한가한 같은 종류 건물로 바꾸고,
  더블클릭(0x4335F0)으로 같은 종류의 내 건물을 함께 고를 수 있게 한다.
"""
import itertools
import struct
import unittest
from pathlib import Path

import minimap_patch
import production_split_patch as ps

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'
UNITS, UNIT_SIZE = 0x775A38, 0x138
SHOWN, ME, SEL_COUNT = 0xB412D0, 0xB412CC, 0x80083C
NET = 0xB411A4                    # 네트워크 객체 포인터, +0x44 = 보낼 명령 버퍼
SEND = 0x4494C0                   # 명령 보내기 (thiscall) — 시험에서는 바로 돌아옴
SCRATCH = 0x2000000
SENTINEL = 0x2FF0000
BARRACKS, FORGE = 40, 41


def _emulator(image):
    try:
        import pefile
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    except ImportError as e:
        raise unittest.SkipTest(str(e))
    img = pefile.PE(data=image).get_memory_mapped_image()
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    size = max(len(img), 0x1100000 - 0x400000)
    mu.mem_map(0x400000, (size + 0xFFF) & ~0xFFF)
    mu.mem_write(0x400000, img)
    mu.mem_map(SCRATCH, 0x1000000)
    return mu


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()


class PatchFileTests(Base):
    def test_state_roundtrip_and_code(self):
        self.assertFalse(ps.state(self.original))
        on = ps.transform(self.original, True)
        self.assertTrue(ps.state(on))
        self.assertEqual(ps.transform(on, False), self.original)
        try:
            self.assertEqual(ps.assemble(), ps.CODE)
        except ImportError as e:
            self.skipTest(str(e))

    def test_upgrades_from_v0_9086_installs(self):
        """v0.9086 (시험판·배포판)이 설치해 둔 게임 파일을 걷어내고 지금 판으로 바꾼다.
        (v0.9087 은 이 상태를 몰라 '코드 충돌' 로 게임 실행이 막혔다.)"""
        fresh = ps.transform(self.original, True)
        self.assertEqual(len(ps.LEGACY_SITES), 3)                 # v0.9086 시험판, v0.9086, v0.9087~v0.9093
        for sites in ps.LEGACY_SITES:
            old = bytearray(self.original)
            for offset, original, patched in sites:
                self.assertEqual(bytes(old[offset:offset + len(original)]), original)
                old[offset:offset + len(patched)] = patched
            self.assertTrue(ps.state(old))
            self.assertEqual(ps.transform(old, False), self.original)
            self.assertEqual(ps.transform(old, True), fresh)
            self.assertEqual(minimap_patch.build(bytes(old), False), minimap_patch.build(self.original, False))
        bad = bytearray(fresh)
        bad[ps.SCAN_SITE + 2] ^= 1
        with self.assertRaises(ValueError):
            ps.state(bad)

    def test_rally_flag_is_drawn_for_several_selected_buildings(self):
        """집결지 깃발 그리기(0x4D34D0) 머리: 원래는 고른 것이 하나일 때만 다음 검사로 넘어간다.
        패치하면 여러 개여도 넘어간다 (0 개는 여전히 끝으로). 게임 코드 그대로 실행."""
        try:
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
            from unicorn.x86_const import UC_X86_REG_EIP
        except ImportError:
            self.skipTest("unicorn 없음")
        patched = ps.transform(self.original, True)
        self.assertEqual(patched[ps.FLAG_SITE:ps.FLAG_SITE + 6], ps.FLAG_PATCHED)
        NEXT, END = 0x4D34E9, 0x4D377E
        for image, expect in ((self.original, {0: END, 1: NEXT, 2: END, 12: END}),
                              (patched, {0: END, 1: NEXT, 2: NEXT, 12: NEXT, 24: NEXT})):
            for count, want in expect.items():
                mu = Uc(UC_ARCH_X86, UC_MODE_32)
                mu.mem_map(0x400000, 0x200000)
                mu.mem_write(0x400000, bytes(image[:0x200000]))
                mu.mem_map(0x800000, 0x1000)
                mu.mem_write(SEL_COUNT, struct.pack("<H", count))
                mu.emu_start(0x4D34D9, 0, count=3)              # movsx eax,[count]; cmp eax,1; jcc
                self.assertEqual(mu.reg_read(UC_X86_REG_EIP), want, (image is patched, count))

    def test_caves_are_free_in_original(self):
        caves = [(va - 0x400000, size) for va, size in ps.CHUNKS.values()] + [(ps.VOICE_CAVE - 0x400000, len(ps.VOICE_CODE))]
        for offset, size in caves:
            self.assertEqual(self.original[offset:offset + size], bytes(size))

    def test_every_build_has_it_and_is_idempotent(self):
        """모든 패치 조합에서 다른 패치와 겹치지 않고 늘 들어간다. 다시 빌드해도 같은 결과."""
        for hr, gold, keys, sel, rec, play, spawn in itertools.product((False, True), repeat=7):
            args = (hr, gold, keys, sel, rec, rec, play, spawn)
            built = minimap_patch.build(self.original, *args)
            self.assertTrue(ps.state(minimap_patch.underlying(built)))
            self.assertEqual(minimap_patch.build(built, *args), built)


class SendTests(Base):
    """0x447CF0(0x4008, 건물, 세부, 값) 을 실행해 버퍼에 쓰인 건물 번호를 본다."""

    def machine(self, select24=False):
        built = minimap_patch.build(self.original, False, True, True, select24, False)
        mu = _emulator(built)
        mu.mem_write(NET, struct.pack('<I', SCRATCH + 0x100))
        mu.mem_write(SCRATCH + 0x100 + 0x44, struct.pack('<I', SCRATCH + 0x200))
        mu.mem_write(SEND, b'\xc3')
        mu.mem_write(ME, b'\x01')
        self.list_at = struct.unpack('<I', bytes(mu.mem_read(ps.SEL_LIST_REF, 4)))[0]
        return mu

    def unit(self, mu, n, kind=BARRACKS, owner=1, hp=100, order=0x2000, queue=0):
        base = UNITS + n * UNIT_SIZE
        mu.mem_write(base + 6, struct.pack('<H', order))
        mu.mem_write(base + 8, struct.pack('<h', hp))
        mu.mem_write(base + 0xE, struct.pack('<h', kind))
        mu.mem_write(base + 0x10, bytes([owner]))
        mu.mem_write(base + 0x52, bytes([queue]))

    def select(self, mu, units, shown=None):
        mu.mem_write(SEL_COUNT, struct.pack('<h', len(units)))
        mu.mem_write(self.list_at, b''.join(struct.pack('<h', u) for u in units))
        mu.mem_write(SHOWN, struct.pack('<h', units[0] if shown is None else shown))

    def send(self, mu, kind, unit, sub, value=7):
        from unicorn.x86_const import UC_X86_REG_ESP
        esp = SCRATCH + 0x8000
        mu.mem_write(esp, struct.pack('<IIIII', SENTINEL, kind, unit, sub, value))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(0x447CF0, SENTINEL, count=20000)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        pkt = bytes(mu.mem_read(SCRATCH + 0x200, 9))
        t, size, u, s, v = struct.unpack('<HHhBH', pkt)
        self.assertEqual((t, size, s, v), (kind, 9, sub, value))
        return u

    def test_production_goes_to_the_least_busy_building(self):
        for sel24 in (False, True):
            mu = self.machine(sel24)
            self.unit(mu, 10, order=0x1005, queue=2)      # 생산 중 + 예약 2 = 3
            self.unit(mu, 11, order=0x1005, queue=0)      # 1
            self.unit(mu, 12, order=0x1005, queue=1)      # 2
            self.select(mu, [10, 11, 12])
            self.assertEqual(self.send(mu, 0x4008, 10, 5), 11)
            self.unit(mu, 12)                              # 쉬는 건물이 가장 먼저
            self.assertEqual(self.send(mu, 0x4008, 10, 5), 12)

    def test_order_follows_starcraft2(self):
        """모두 쉬면 정보 창 건물부터, 그다음 선택 순서대로 하나씩: 예약이 쌓이는 순서를 흉내 낸다."""
        mu = self.machine()
        for n in (20, 21, 22):
            self.unit(mu, n)
        self.select(mu, [20, 21, 22])
        got = []
        for _ in range(6):
            u = self.send(mu, 0x4008, 20, 5)
            got.append(u)
            base = UNITS + u * UNIT_SIZE                    # 게임이 실행한 것처럼: 시작 또는 예약
            order = struct.unpack('<H', bytes(mu.mem_read(base + 6, 2)))[0]
            if order & 0x1000:
                q = bytes(mu.mem_read(base + 0x52, 1))[0]
                mu.mem_write(base + 0x52, bytes([q + 1]))
            else:
                mu.mem_write(base + 6, struct.pack('<H', 0x1005))
        self.assertEqual(got, [20, 21, 22, 20, 21, 22])

    def test_skips_other_types_enemies_dead_full_and_busy(self):
        mu = self.machine()
        self.unit(mu, 30, order=0x1005, queue=3)          # 정보 창 건물: 4
        self.unit(mu, 31, kind=FORGE)                      # 다른 종류
        self.unit(mu, 32, owner=2)                         # 남의 것
        self.unit(mu, 33, hp=0)                            # 죽음
        self.unit(mu, 34, order=0x1005, queue=4)          # 예약 가득
        self.unit(mu, 35, order=0x1006)                   # 연구 중 (생산 못 받음)
        self.unit(mu, 36, order=0x1004)                   # 건설 중
        self.select(mu, [30, 31, 32, 33, 34, 35, 36])
        self.assertEqual(self.send(mu, 0x4008, 30, 5), 30)
        self.unit(mu, 30, order=0x1005, queue=4)          # 모두 받을 수 없으면 원래대로
        self.assertEqual(self.send(mu, 0x4008, 30, 5), 30)

    def test_upgrade_goes_to_an_idle_building(self):
        for sub in (6, 10):
            mu = self.machine()
            self.unit(mu, 40, kind=FORGE, order=0x1006)   # 정보 창 건물은 연구 중
            self.unit(mu, 41, kind=FORGE, order=0x1005)   # 업그레이드는 생산 중이면 못 받음
            self.unit(mu, 42, kind=FORGE)
            self.select(mu, [40, 41, 42])
            self.assertEqual(self.send(mu, 0x4008, 40, sub), 42)
            self.unit(mu, 40, kind=FORGE)                  # 정보 창 건물이 쉬면 그대로
            self.assertEqual(self.send(mu, 0x4008, 40, sub), 40)

    def test_other_commands_unchanged(self):
        mu = self.machine()
        self.unit(mu, 50, order=0x1005, queue=3)
        self.unit(mu, 51)
        self.select(mu, [50, 51])
        for sub in (7, 8, 9, 11):                          # 변신 등은 정보 창 건물 그대로
            self.assertEqual(self.send(mu, 0x4008, 50, sub), 50)
        from unicorn.x86_const import UC_X86_REG_ESP
        esp = SCRATCH + 0x8000                             # 다른 명령 (0x4011) 도 그대로
        mu.mem_write(esp, struct.pack('<IIIII', SENTINEL, 0x4011, 50, 4, 9))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(0x447CF0, SENTINEL, count=20000)
        self.assertEqual(struct.unpack('<HHh', bytes(mu.mem_read(SCRATCH + 0x200, 6))), (0x4011, 9, 50))
        mu.mem_write(SHOWN, struct.pack('<h', 0))         # 정보 창 유닛 없음: 그대로
        self.assertEqual(self.send(mu, 0x4008, 50, 5), 50)


class RallyTests(SendTests):
    """0x447E60(3 = 집결지, 대상, 층, 지점): 같은 종류 내 건물을 여럿 골랐으면 건물마다 명령 0x400E 를 하나씩."""

    def rally(self, mu, sub=3, target=0, layer=1, point=0x00C80190):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP
        sent = []
        h = mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: sent.append(bytes(uc.mem_read(SCRATCH + 0x200, 0xF))),
                        begin=SEND, end=SEND)
        esp = SCRATCH + 0x8000
        mu.mem_write(esp, struct.pack('<IIIII', SENTINEL, sub, target, layer, point))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(0x447E60, SENTINEL, count=100000)
        mu.hook_del(h)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        out = []
        for pkt in sent:
            t, size, s_, unit, tgt, lay, pt = struct.unpack('<HHHhhBI', pkt)
            self.assertEqual((t, size, s_, tgt, lay, pt), (0x400E, 0xF, sub, target, layer, point))
            out.append(unit)
        return out

    def test_rally_goes_to_every_selected_building(self):
        for sel24 in (False, True):
            mu = self.machine(sel24)
            self.unit(mu, 60)                                  # 쉼
            self.unit(mu, 61, order=0x1005, queue=2)           # 생산 중
            self.unit(mu, 62, order=0x1006)                    # 연구 중
            self.unit(mu, 63, order=0x1004)                    # 건설 중 (집결지 가능, 건설 중 집결지 패치)
            self.unit(mu, 64, kind=FORGE)                      # 다른 종류
            self.unit(mu, 65, owner=2)                         # 남의 것
            self.unit(mu, 66, hp=0)                            # 죽음
            self.select(mu, [60, 61, 62, 63, 64, 65, 66])
            self.assertEqual(self.rally(mu), [60, 61, 62, 63])
            self.assertEqual(struct.unpack('<h', bytes(mu.mem_read(SHOWN, 2)))[0], 60)   # 정보 창 유닛 그대로

    def test_single_building_and_other_subcommands_unchanged(self):
        mu = self.machine()
        self.unit(mu, 70)
        self.unit(mu, 71)
        self.select(mu, [70])
        self.assertEqual(self.rally(mu), [70])
        self.select(mu, [70, 71], shown=70)
        self.assertEqual(self.rally(mu, sub=1, target=5), [70])        # 공격 대상 지정 등은 정보 창 건물만


class DoubleClickTests(Base):
    """0x4335F0 의 앞부분: 누른 유닛이 내 것이 아니면 그만 (전에는 건물이면 그만)."""

    def test_site_bytes(self):
        on = ps.transform(self.original, True)
        try:
            import capstone
        except ImportError as e:
            self.skipTest(str(e))
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        text = [f'{i.mnemonic} {i.op_str}' for i in md.disasm(on[ps.PICK_SITE:ps.PICK_SITE + 18], 0x433603)]
        self.assertEqual(text, ['mov cl, byte ptr [eax + 0x775a48]', 'cmp cl, byte ptr [0xb412cc]', 'jne 0x433bdd'])

    def test_pick_rejects_others_and_accepts_mine(self):
        mu = _emulator(minimap_patch.build(self.original, False))
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP
        for owner, want in ((2, 0x433BDD), (1, 0x433615)):
            mu.mem_write(ME, b'\x01')
            mu.mem_write(UNITS + 7 * UNIT_SIZE + 0x10, bytes([owner]))
            mu.reg_write(UC_X86_REG_EAX, 7 * UNIT_SIZE)
            mu.emu_start(0x433603, 0, count=3)
            self.assertEqual(mu.reg_read(UC_X86_REG_EIP), want, owner)


class PanelTests(Base):
    """0x46049F: 같은 건물을 둘 이상 골랐으면 연구 중이어도 버튼 목록(0x460508), 하나면 원래대로."""

    def test_branch(self):
        mu = _emulator(minimap_patch.build(self.original, False))
        from unicorn.x86_const import UC_X86_REG_EIP
        mu.mem_write(SHOWN, struct.pack('<h', 9))
        for count, order, want in ((2, 0x1006, 0x460508), (1, 0x1006, 0x4604BD), (1, 0x2000, 0x460508),
                                   (3, 0x2000, 0x460508), (1, 0x1005, 0x4604BD)):
            mu.mem_write(SEL_COUNT, struct.pack('<h', count))
            mu.mem_write(UNITS + 9 * UNIT_SIZE + 6, struct.pack('<H', order))
            mu.emu_start(0x46049F, 0, count=2)                  # cmp, ja
            if mu.reg_read(UC_X86_REG_EIP) != 0x460508:
                mu.emu_start(mu.reg_read(UC_X86_REG_EIP), 0, count=5)   # mov, cwde, imul, test, je
            self.assertEqual(mu.reg_read(UC_X86_REG_EIP), want, (count, hex(order)))


class ScanTests(Base):
    """더블클릭 화면 탐색의 후보 검사 (땅 0x433AC0, 공중 0x433896) 와 선택 음성 (0x49E400 대신)."""

    def setUp(self):
        from unicorn.x86_const import UC_X86_REG_EBP
        self.mu = _emulator(minimap_patch.build(self.original, False))
        self.mu.reg_write(UC_X86_REG_EBP, SCRATCH + 0x9000)
        self.mu.mem_write(SCRATCH + 0x9000 + 0xC, struct.pack('<h', 5))      # 누른 유닛 5

    def cand(self, n, cls, marked=False, hp=50, clicked_cls=None):
        mu = self.mu
        mu.mem_write(0x766912, struct.pack('<h', n))
        mu.mem_write(UNITS + n * UNIT_SIZE + 2, struct.pack('<h', cls))
        mu.mem_write(UNITS + n * UNIT_SIZE + 8, struct.pack('<h', hp))
        mu.mem_write(0xB412E4 + n, bytes([0x80 if marked else 0]))
        if clicked_cls is not None:
            mu.mem_write(UNITS + 5 * UNIT_SIZE + 2, struct.pack('<h', clicked_cls))

    def run_to(self, start, stops):
        from unicorn import UC_HOOK_CODE
        hit = []
        def f(uc, a, sz, _):
            if a in stops:
                hit.append(a)
                uc.emu_stop()
        h = self.mu.hook_add(UC_HOOK_CODE, f)
        self.mu.emu_start(start, 0, count=40)
        self.mu.hook_del(h)
        return hit[0]

    def test_ground_scan_keeps_units_and_buildings_apart(self):
        skip, go = 0x433AF2, 0x433AF7
        for clicked, cand, marked, want in ((3, 3, False, go), (3, 0, False, skip), (0, 3, False, skip),
                                            (0, 0, False, go), (0, 0, True, skip), (3, 3, True, skip)):
            self.cand(9, cand, marked, clicked_cls=clicked)
            self.assertEqual(self.run_to(0x433AC0, {skip, go}), want, (clicked, cand, marked))

    def test_air_scan_never_for_a_clicked_building(self):
        nxt, go = 0x433977, 0x4338D1
        for clicked, marked, hp, want in ((0, False, 50, go), (3, False, 50, nxt), (0, True, 50, nxt), (0, False, 0, nxt)):
            self.cand(9, 0, marked, hp, clicked_cls=clicked)
            self.assertEqual(self.run_to(0x433896, {nxt, go}), want, (clicked, marked, hp))

    def test_voice_only_for_units(self):
        from unicorn.x86_const import UC_X86_REG_ESP
        mu = self.mu
        for cls, want in ((0, ps.VOICE), (2, SENTINEL)):
            mu.mem_write(UNITS + 9 * UNIT_SIZE + 2, struct.pack('<h', cls))
            esp = SCRATCH + 0x8000
            mu.mem_write(esp, struct.pack('<II', SENTINEL, UNITS + 9 * UNIT_SIZE))
            mu.reg_write(UC_X86_REG_ESP, esp)
            from unicorn import UC_HOOK_CODE
            hit = []
            h = mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: (hit.append(a), uc.emu_stop()) if a in (ps.VOICE, SENTINEL) else None)
            mu.emu_start(ps.VOICE_CAVE, 0, count=20)
            mu.hook_del(h)
            self.assertEqual(hit[0], want, cls)
        built = minimap_patch.build(self.original, False)
        for at in ps.VOICE_SITES:
            rel = struct.unpack('<i', built[at + 1:at + 5])[0]
            self.assertEqual(0x400000 + at + 5 + rel, ps.VOICE_CAVE)


if __name__ == '__main__':
    unittest.main()
