"""마법 순차 시전 (smart_cast_patch) — 게임 코드 그대로 Unicorn 으로 실행.

0x447D60(명령, 대상, 층, 지점) 을 부르고 명령 보내기(0x4494C0)에 넘어간 패킷을 차례로 본다.
"""
import itertools
import struct
import unittest
from pathlib import Path

import hotkey_patch
import minimap_patch
import smart_cast_patch as sc
from test_production_split_patch import _emulator, EXE, UNITS, UNIT_SIZE, SHOWN, SEL_COUNT, NET, SEND, SCRATCH

SENTINEL = SCRATCH + 0x9000
BUF = SCRATCH + 0x200
MAGE, OTHER = 0x31, 0x32
SPELL, INSTANT = 0x2025, 0x2021          # 명령 표: 0x25 는 대상 고르기 함수가 있고 0x21 은 없다
SLOT, COST = 2, 50
POINT = (100 * 32) | ((80 * 32) << 16)    # 찍은 지점 (칸 100, 80 의 픽셀)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise unittest.SkipTest('game_backup/Rhakmu.exe 없음')
        cls.original = EXE.read_bytes()


class PatchTests(Base):
    def test_code_matches_source(self):
        try:
            self.assertEqual(sc.assemble(), sc.CODE)
        except ImportError as e:
            self.skipTest(str(e))

    def test_every_build_has_it_last_and_is_idempotent(self):
        for hr, keys, sel, rec, play in itertools.product((False, True), repeat=5):
            args = (hr, True, keys, sel, rec, rec, play, False)
            built = minimap_patch.build(self.original, *args)
            self.assertTrue(sc.state(built))
            under = sc.strip(built)
            self.assertFalse(sc.state(under))
            self.assertEqual(under[sc.SITE:sc.SITE + 6], sc.SITE_ORIGINAL)
            self.assertEqual(hotkey_patch.state(under), keys)                 # 그 아래 섹션들은 그대로
            self.assertEqual(sc.apply(under, True), built)
            self.assertEqual(sc.apply(built, False), under)
            self.assertEqual(minimap_patch.build(built, *args), built)
            self.assertEqual(minimap_patch.underlying(built), minimap_patch.underlying(under))

    def test_unknown_state_is_rejected(self):
        built = bytearray(minimap_patch.build(self.original, False))
        built[-sc.SECTION_SIZE + 3] ^= 1
        with self.assertRaises(ValueError):
            sc.state(built)
        bad = bytearray(self.original)
        bad[sc.SITE] ^= 1
        with self.assertRaises(ValueError):
            sc.state(bad)


class CastTests(Base):
    def machine(self, select24=False):
        from unicorn import UC_HOOK_CODE
        built = minimap_patch.build(self.original, False, True, True, select24, False)
        mu = _emulator(built)
        mu.mem_write(NET, struct.pack('<I', SCRATCH + 0x100))
        mu.mem_write(SCRATCH + 0x100 + 0x44, struct.pack('<I', BUF))
        mu.mem_write(SEND, b'\xc3')
        self.list_at = struct.unpack('<I', bytes(mu.mem_read(sc.SEL_LIST_PTR, 4)))[0]
        record = SCRATCH + 0x400                                             # 마법 자료: +8 드는 마나, +0x42 마나 칸
        mu.mem_write(record + 8, struct.pack('<h', COST))
        mu.mem_write(record + 0x42, struct.pack('<h', SLOT))
        for order in (SPELL, INSTANT):
            mu.mem_write(sc.MAGIC_TABLE + (order - 0x2020) * 0x14, struct.pack('<I', record))
        self.assertNotEqual(struct.unpack('<I', bytes(mu.mem_read(sc.ORDER_TABLE + (SPELL & 0xFF) * 0x14, 4)))[0], 0)
        self.assertEqual(struct.unpack('<I', bytes(mu.mem_read(sc.ORDER_TABLE + (INSTANT & 0xFF) * 0x14, 4)))[0], 0)
        self.sent = []
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, s, _: self.sent.append(self.packet(uc)), begin=SEND, end=SEND)
        return mu

    @staticmethod
    def packet(uc):
        kind, size = struct.unpack('<HH', bytes(uc.mem_read(BUF, 4)))
        body = bytes(uc.mem_read(BUF, size))
        if kind == 0x4002:
            return ('select', list(struct.unpack(f'<{body[4]}H', body[5:5 + 2 * body[4]])))
        if kind == 0x4009:
            return ('order',) + struct.unpack('<HhBI', body[4:13])
        return (hex(kind), body)

    def unit(self, mu, n, kind=MAGE, mana=100, cell=(0, 0), order=2, hp=100, building=0):
        base = UNITS + n * UNIT_SIZE
        mu.mem_write(base + 2, struct.pack('<H', building))
        mu.mem_write(base + 6, struct.pack('<H', order))
        mu.mem_write(base + 8, struct.pack('<h', hp))
        mu.mem_write(base + 0xE, struct.pack('<H', kind))
        mu.mem_write(base + 0x18, struct.pack('<hh', *cell))
        mu.mem_write(base + 0xFE + SLOT * 4, struct.pack('<h', mana))

    def select(self, mu, ids, shown=None):
        mu.mem_write(SEL_COUNT, struct.pack('<H', len(ids)))
        mu.mem_write(self.list_at, struct.pack(f'<{len(ids)}H', *ids) + bytes(4))
        mu.mem_write(SHOWN, struct.pack('<h', ids[0] if shown is None else shown))

    def cast(self, mu, order=SPELL, target=0, layer=1, point=POINT):
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP
        self.sent.clear()
        esp = SCRATCH + 0x8000
        mu.mem_write(esp, struct.pack('<IIIII', SENTINEL, order, target & 0xFFFF, layer, point))
        saved = {r: 0x1000 + r for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)}
        for r, v in saved.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(sc.SITE_VA, SENTINEL, count=100000)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        for r, v in saved.items():                                           # 게임이 지키는 레지스터는 그대로
            self.assertEqual(mu.reg_read(r), v)
        return list(self.sent)

    def order_packet(self, order=SPELL, target=0, layer=1, point=POINT):
        return ('order', order, target, layer, point)

    def test_one_caster_per_use_nearest_first_then_the_next(self):
        for sel24 in (False, True):
            mu = self.machine(sel24)
            self.unit(mu, 10, cell=(10, 80))
            self.unit(mu, 11, cell=(98, 80))                                 # 지점에 가장 가까움
            self.unit(mu, 12, cell=(60, 80))
            self.select(mu, [10, 11, 12])
            self.assertEqual(self.cast(mu), [('select', [11]), self.order_packet(), ('select', [10, 11, 12])])
            # 게임이 명령을 실행하면 11 번은 마법 명령 상태가 된다 -> 다음에는 그다음 가까운 유닛
            self.unit(mu, 11, cell=(98, 80), order=SPELL)
            self.assertEqual(self.cast(mu)[0], ('select', [12]))
            self.unit(mu, 12, cell=(60, 80), order=SPELL)
            self.assertEqual(self.cast(mu)[0], ('select', [10]))
            self.unit(mu, 10, cell=(10, 80), order=SPELL)                    # 모두 쓰는 중이면 그중 가까운 유닛
            self.assertEqual(self.cast(mu)[0], ('select', [11]))

    def test_skips_no_mana_dead_and_other_kinds(self):
        mu = self.machine()
        self.unit(mu, 20, cell=(100, 80), mana=COST - 1)                     # 마나 부족
        self.unit(mu, 21, cell=(100, 81), hp=0)                              # 죽음
        self.unit(mu, 22, cell=(100, 82), kind=OTHER)                        # 다른 종류
        self.unit(mu, 23, cell=(20, 20), mana=COST)                          # 멀지만 쓸 수 있음
        self.select(mu, [20, 21, 22, 23])
        self.assertEqual(self.cast(mu, target=77), [('select', [23]), self.order_packet(target=77), ('select', [20, 21, 22, 23])])
        self.unit(mu, 23, cell=(20, 20), mana=0)                             # 쓸 유닛이 없으면 원래대로 (모두에게)
        self.assertEqual(self.cast(mu), [self.order_packet()])

    def test_everything_else_is_sent_as_before(self):
        mu = self.machine()
        for n in (30, 31, 32):
            self.unit(mu, n, cell=(n, n))
        self.select(mu, [30, 31, 32])
        self.assertEqual(self.cast(mu, order=INSTANT), [self.order_packet(order=INSTANT)])     # 누르자마자 쓰는 마법
        for order in (0x2001, 0x2003, 0x2007, 0x2011, 0x2061, 0x206B):                         # 공격·이동 등, 건물 마법
            self.assertEqual(self.cast(mu, order=order), [self.order_packet(order=order)], hex(order))
        self.select(mu, [30])                                                                  # 하나만 골랐을 때
        self.assertEqual(self.cast(mu), [self.order_packet()])
        self.select(mu, [30, 31, 32], shown=0)                                                 # 보이는 유닛 없음
        self.assertEqual(self.cast(mu), [self.order_packet()])
        self.unit(mu, 30, building=3)                                                          # 보이는 것이 건물
        self.select(mu, [30, 31, 32])
        self.assertEqual(self.cast(mu), [self.order_packet()])
        mu.mem_write(sc.MAGIC_TABLE + (SPELL - 0x2020) * 0x14, bytes(4))                       # 마법 자료 없음
        self.unit(mu, 30)
        self.assertEqual(self.cast(mu), [self.order_packet()])

    def test_unpatched_game_sends_one_order(self):
        """원본 0x447D60 은 명령 하나만 보낸다 (비교 기준)."""
        from unicorn import UC_HOOK_CODE
        mu = _emulator(self.original)
        mu.mem_write(NET, struct.pack('<I', SCRATCH + 0x100))
        mu.mem_write(SCRATCH + 0x100 + 0x44, struct.pack('<I', BUF))
        mu.mem_write(SEND, b'\xc3')
        self.list_at = 0x80083E
        self.sent = []
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, s, _: self.sent.append(self.packet(uc)), begin=SEND, end=SEND)
        for n in (40, 41):
            self.unit(mu, n)
        self.select(mu, [40, 41])
        self.assertEqual(self.cast(mu), [self.order_packet()])


if __name__ == '__main__':
    unittest.main()
