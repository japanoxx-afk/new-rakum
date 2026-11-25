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
SPELL, INSTANT, TOGGLE = 0x2025, 0x2021, 0x2022     # 대상을 찍는 마법, 누르자마자 쓰는 마법, 마나가 들지 않는 것
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
            self.assertEqual(sc.assemble(), (sc.CODE, sc.CODE2, sc.CODE3, sc.CODE4))
            self.assertLessEqual(sc.CODE3_OFFSET + len(sc.CODE3), sc.CODE4_OFFSET)
            self.assertLessEqual(len(sc.CODE), sc.CODE2_OFFSET)
            self.assertLessEqual(sc.CODE2_OFFSET + len(sc.CODE2), sc.CODE3_OFFSET)
            self.assertLessEqual(sc.CODE4_OFFSET + len(sc.CODE4), sc.SECTION_SIZE)
        except ImportError as e:
            self.skipTest(str(e))

    def test_every_build_has_it_last_and_is_idempotent(self):
        for hr, keys, sel, rec, play in itertools.product((False, True), repeat=5):
            args = (hr, True, keys, sel, rec, rec, play, False)
            built = minimap_patch.build(self.original, *args)
            self.assertTrue(sc.state(built))
            under = sc.strip(built)
            self.assertTrue(sc.current(built))
            self.assertFalse(sc.state(under))
            for site, original, _ in sc.SITES:
                self.assertEqual(under[site:site + len(original)], original)
                self.assertEqual(self.original[site:site + len(original)], original)
            self.assertEqual(hotkey_patch.state(under), keys)                 # 그 아래 섹션들은 그대로
            self.assertEqual(sc.apply(under, True), built)
            self.assertEqual(sc.apply(built, False), under)
            self.assertEqual(minimap_patch.build(built, *args), built)
            self.assertEqual(minimap_patch.underlying(built), minimap_patch.underlying(under))

    def test_upgrades_from_older_builds(self):
        """v0.9096 시험판(자리 하나, 예전 코드)·v0.9097~v0.9099(미니맵 시야 없음)·v0.9100~v0.9103(A 키 처리 없음)이 설치해 둔 상태를 알아보고 지금 판으로 바꾼다."""
        import struct as st
        built = minimap_patch.build(self.original, False)
        under = sc.strip(built)
        self.assertEqual(len(sc.LEGACY), 3)
        for code, used in sc.LEGACY:
            old = bytearray(built)
            va = st.unpack_from('<I', built, sc._layout(built)[6][-1][5] + 12)[0]
            old[-sc.SECTION_SIZE:] = code.ljust(sc.SECTION_SIZE, bytes(1))
            for k, (site, original, offset) in enumerate(sc.SITES):
                old[site:site + len(original)] = sc._jump(site, va, offset) if k in used else original
            self.assertTrue(sc.state(old))
            self.assertFalse(sc.current(old))
            self.assertEqual(sc.strip(old), under)
            self.assertEqual(minimap_patch.build(bytes(old), False), built)

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
        free = SCRATCH + 0x500                                               # 마나가 들지 않는 것 (변신 등)
        mu.mem_write(free + 0x42, struct.pack('<h', SLOT))
        mu.mem_write(sc.MAGIC_TABLE + (TOGGLE - 0x2020) * 0x14, struct.pack('<I', free))
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
        if size == 5:
            return ('instant', kind, body[4])
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

    def press(self, mu, command=0x400D, number=INSTANT - 0x2020):
        """누르자마자 쓰는 마법 버튼: 0x447E10(명령, 마법 번호)."""
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP
        self.sent.clear()
        esp = SCRATCH + 0x8000
        mu.mem_write(esp, struct.pack('<III', SENTINEL, command, number))
        saved = {r: 0x2000 + r for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)}
        for r, v in saved.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(sc.SITE2_VA, SENTINEL, count=100000)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        for r, v in saved.items():
            self.assertEqual(mu.reg_read(r), v)
        return list(self.sent)

    def test_instant_spell_goes_to_the_caster_with_most_mana(self):
        k = INSTANT - 0x2020
        for sel24 in (False, True):
            mu = self.machine(sel24)
            self.unit(mu, 50, mana=120)
            self.unit(mu, 51, mana=200)
            self.unit(mu, 52, mana=160)
            self.unit(mu, 53, mana=999, kind=OTHER)                           # 다른 종류는 빼고
            self.unit(mu, 54, mana=999, hp=0)                                 # 죽은 유닛도
            ids = [50, 51, 52, 53, 54]
            self.select(mu, ids)
            self.assertEqual(self.press(mu), [('select', [51]), ('instant', 0x400D, k), ('select', ids)])
            self.unit(mu, 51, mana=200 - COST)                                # 쓰고 나면 마나가 줄어 다음 유닛 차례
            self.assertEqual(self.press(mu)[0], ('select', [52]))
            self.unit(mu, 52, mana=160 - COST)
            self.assertEqual(self.press(mu)[0], ('select', [51]))
            for n in (50, 51, 52):
                self.unit(mu, n, mana=COST - 1)                               # 쓸 유닛이 없으면 원래대로
            self.assertEqual(self.press(mu), [('instant', 0x400D, k)])

    def test_free_abilities_and_other_commands_go_to_everyone(self):
        mu = self.machine()
        for n in (60, 61, 62):
            self.unit(mu, n)
        self.select(mu, [60, 61, 62])
        self.assertEqual(self.press(mu, number=TOGGLE - 0x2020), [('instant', 0x400D, TOGGLE - 0x2020)])   # 마나 0: 모두에게
        self.assertEqual(self.press(mu, number=0x41), [('instant', 0x400D, 0x41)])                         # 건물 마법
        self.assertEqual(self.press(mu, number=0), [('instant', 0x400D, 0)])
        for command in (0x400C, 0x4006, 0x4011):                                                           # 같은 함수로 보내는 다른 명령
            self.assertEqual(self.press(mu, command=command), [('instant', command, INSTANT - 0x2020)])
        self.select(mu, [60])                                                                              # 하나만 골랐을 때
        self.assertEqual(self.press(mu), [('instant', 0x400D, INSTANT - 0x2020)])
        self.select(mu, [60, 61, 62], shown=0)
        self.assertEqual(self.press(mu), [('instant', 0x400D, INSTANT - 0x2020)])

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



class MinimapVisionTests(Base):
    """미니맵 시야 표시: 시야 계산 끝(0x49BE70)에서 지형 반 밝기 + 내가 보는 칸만 원래 밝기, 그 뒤 원래 함수 0x469030."""
    OBJ = SCRATCH + 0x100000
    DEVICE = SCRATCH + 0x80000
    MASK = 0xF7DE

    def _run(self, visible, width=128, height=128, table=None, all_view=False, me=1, bits=0x02):
        built = minimap_patch.build(self.original, False)
        self.assertEqual(built[sc.SITE3], 0xE8)
        mu = _emulator(built)
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_EBX, UC_X86_REG_EBP
        from unicorn import UC_HOOK_CODE
        terrain = b"".join(struct.pack("<H", 0x8000 | (i * 7 & 0x7FFF)) for i in range(0x4000))
        mu.mem_write(self.OBJ + 0x2C, terrain)
        mu.mem_write(self.OBJ + 0x1002C, b"\xAA" * 0x8000)
        table = table or (lambda v: v * 128 // max(width, height))
        for k in range(520):
            mu.mem_write(self.OBJ + 0x20254 + k * 2, struct.pack("<H", min(table(k), 0x7FFF)))
            mu.mem_write(self.OBJ + 0x20664 + k * 2, struct.pack("<H", min(table(k), 0x7FFF)))
        mu.mem_write(0x4EC438, struct.pack("<I", self.DEVICE))
        mu.mem_write(self.DEVICE + 0x38, struct.pack("<I", self.MASK))
        mu.mem_write(sc.MAP_W, struct.pack("<HH", width, height))
        mu.mem_write(sc.LOCAL_PLAYER, bytes([me]))
        mu.mem_write(sc.PLAYER_BITS + me * 2, struct.pack("<H", bits))
        mu.mem_write(0xB412C8, struct.pack("<H", 1 if all_view else 0))
        mu.mem_write(sc.VISIBLE, bytes(0x42040))
        for (x, y), value in visible.items():
            mu.mem_write(sc.VISIBLE + y * 0x208 + x, bytes([value]))
        seen = {}

        def hook(uc, address, size, user):               # 원래 함수에 닿으면 거기서 멈춘다
            if address == sc.DRAW_DOTS:
                seen["ecx"] = uc.reg_read(UC_X86_REG_ECX)
                seen["ret"] = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 4))[0]
                seen["regs"] = (uc.reg_read(UC_X86_REG_EBX), uc.reg_read(UC_X86_REG_EBP))
                uc.emu_stop()
        mu.hook_add(UC_HOOK_CODE, hook, begin=sc.DRAW_DOTS, end=sc.DRAW_DOTS)
        esp = SCRATCH + 0x8000
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, self.OBJ)
        mu.reg_write(UC_X86_REG_EBX, 0x11111111)
        mu.reg_write(UC_X86_REG_EBP, 0x22222222)
        mu.emu_start(0x400000 + sc.SITE3, 0, count=20000000)
        self.assertEqual(seen, {"ecx": self.OBJ, "ret": 0x400000 + sc.SITE3 + 5, "regs": (0x11111111, 0x22222222)})
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp - 4)
        frame = struct.unpack("<16384H", mu.mem_read(self.OBJ + 0x1002C, 0x8000))
        return struct.unpack("<16384H", terrain), frame

    def test_only_my_vision_is_bright(self):
        terrain, frame = self._run({(10, 20): 0x02, (11, 20): 0x06, (50, 60): 0x04, (127, 127): 0xFF})
        bright = {20 * 128 + 10, 20 * 128 + 11, 127 * 128 + 127}       # (50, 60) 은 다른 플레이어만 봄
        for k in range(0x4000):
            self.assertEqual(frame[k], terrain[k] if k in bright else (terrain[k] & self.MASK) >> 1, k)

    def test_small_map_fills_the_whole_cell(self):
        terrain, frame = self._run({(3, 5): 0x02, (63, 63): 0x02}, width=64, height=64)
        bright = {y * 128 + x for x in (6, 7) for y in (10, 11)} | {y * 128 + x for x in (126, 127) for y in (126, 127)}
        for k in range(0x4000):
            self.assertEqual(frame[k], terrain[k] if k in bright else (terrain[k] & self.MASK) >> 1, k)

    def test_large_map_and_bad_table_stay_inside_the_picture(self):
        terrain, frame = self._run({(x, y): 0x02 for x in range(0, 300, 7) for y in range(0, 300, 11)}, 300, 300)
        bright = {(y * 128 // 300) * 128 + x * 128 // 300 for x in range(0, 300, 7) for y in range(0, 300, 11)}
        self.assertEqual({k for k in range(0x4000) if frame[k] == terrain[k] and terrain[k] != (terrain[k] & self.MASK) >> 1}, bright)
        terrain, frame = self._run({(x, y): 0x02 for x in range(40) for y in range(40)}, 40, 40, table=lambda v: v * 9)
        for k in range(0x4000):                          # 표가 이상해도(칸마다 9점) 그림 밖으로 쓰지 않고, 칸마다 1점만
            x, y = k % 128, k // 128
            self.assertEqual(frame[k] == terrain[k], x % 9 == 0 and y % 9 == 0, k)

    def test_reveal_all_mode_is_left_alone(self):
        terrain, frame = self._run({(1, 1): 0x02}, all_view=True)
        self.assertEqual(set(frame), {0xAAAA})


class AttackKeyTests(Base):
    """공격이 없는 유닛의 A 키: A 칸(0)이 비어 있고 D 칸이 이동(3)이면 D 칸으로 처리 (0x45CF60 의 앞부분)."""
    PANEL = SCRATCH + 0x20000

    def _slot(self, image, pressed, commands, building=0, shown=7):
        """0x45CF82 부터 '칸이 비었나' 검사(0x45CF91) 직전까지 실행해 (볼 칸, 인자에 남은 칸) 을 돌려준다."""
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_ECX, UC_X86_REG_EAX
        mu = _emulator(image)
        ebp = SCRATCH + 0x8000
        mu.reg_write(UC_X86_REG_EBP, ebp)
        mu.reg_write(UC_X86_REG_ESP, ebp - 0x100)
        mu.mem_write(ebp + 8, struct.pack("<H", pressed))
        mu.mem_write(ebp - 4, struct.pack("<I", self.PANEL))
        mu.mem_write(self.PANEL + 0x1BA, struct.pack("<10H", *commands))
        mu.mem_write(SHOWN, struct.pack("<h", shown))
        if shown > 0:
            mu.mem_write(UNITS + shown * UNIT_SIZE + 2, struct.pack("<H", building))
        mu.emu_start(0x45CF82, 0x45CF91, count=200)
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), ebp - 0x100)
        slot = mu.reg_read(UC_X86_REG_ECX)
        self.assertEqual(mu.reg_read(UC_X86_REG_EAX), commands[slot])            # 그 칸의 명령을 읽어 둠
        return slot, struct.unpack("<H", mu.mem_read(ebp + 8, 2))[0]

    def test_a_key_moves_units_that_cannot_attack(self):
        built = minimap_patch.build(self.original, False)
        fighter = [1, 2, 3, 4, 5, 0, 0, 0, 0, 0]                 # 공격 정지 이동 순찰 고정
        gon = [0, 2, 3, 4, 5, 36, 37, 35, 6, 0]                  # 아스트리아 일꾼 곤: A 칸이 빔
        self.assertEqual(self._slot(built, 0, gon), (2, 2))      # A -> 이동
        self.assertEqual(self._slot(built, 0, fighter), (0, 0))  # 공격이 있으면 그대로
        for k in range(1, 10):
            self.assertEqual(self._slot(built, k, gon), (k, k))  # 다른 키는 그대로
        self.assertEqual(self._slot(built, 0, [0, 0, 17, 0, 0, 0, 0, 0, 0, 0]), (0, 0))   # D 칸이 이동이 아니면 그대로
        self.assertEqual(self._slot(built, 0, gon, building=1), (0, 0))                   # 건물은 그대로
        self.assertEqual(self._slot(built, 0, gon, shown=0), (0, 0))                      # 고른 것이 없으면 그대로
        self.assertEqual(self._slot(self.original, 0, gon), (0, 0))                       # 원래 게임: A 칸이 비어 아무 일도 없음


if __name__ == '__main__':
    unittest.main()
