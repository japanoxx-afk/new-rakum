"""리플레이: 메모리 해석, 기록(가짜 게임 메모리), 파일 복원·통계, 보기 창."""
import os
import struct
import tempfile
import unittest
from pathlib import Path

import replay_memory as rm
import replay_record_patch as rrp
import replay_model as M
import replay_recorder as rr


class FakeGame:
    """게임 메모리 흉내: 주소 -> bytearray 영역."""

    def __init__(self):
        self.units = bytearray(rm.UNIT_SIZE * rm.UNIT_COUNT)
        self.players = bytearray(rm.PLAYER_SIZE * rm.PLAYER_COUNT)
        self.names = bytearray(rm.NAME_SIZE * rm.TYPE_COUNT)
        self.info = bytearray(rm.TYPE_INFO_STRIDE * rm.TYPE_COUNT)
        self.tstats = bytearray(rm.TYPE_STATS_STRIDE * rm.TYPE_COUNT)
        self.heap = bytearray(0x10000)
        self.seconds = 0
        self.frame = 0
        self.seed = 0x1234ABCD
        self.map = b"DATA\\MAPS\\[2]Test.rkm"
        self.sec_va = 0x1084000
        self.ring = bytearray(rrp.RING + 0x10)
        self.pe = bytearray(0x1000)                    # 최소 PE 머리: .rkrec 섹션 하나
        struct.pack_into("<I", self.pe, 0x3C, 0x80)
        self.pe[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", self.pe, 0x80 + 6, 1, 0)
        struct.pack_into("<H", self.pe, 0x80 + 20, 0xE0)
        h = 0x80 + 24 + 0xE0
        self.pe[h:h + 8] = rrp.SECTION_NAME
        struct.pack_into("<I", self.pe, h + 12, self.sec_va - 0x400000)
        for t, name, worker, hp in ((5, "일꾼", True, 40), (7, "검사", False, 60), (20, "병영", False, 900)):
            self.names[t * rm.NAME_SIZE:t * rm.NAME_SIZE + len(name.encode('cp949'))] = name.encode('cp949')
            struct.pack_into("<I", self.info, t * rm.TYPE_INFO_STRIDE, 0x9000000 + t * 0x100)
            struct.pack_into("<h", self.heap, t * 0x100 + 0x40, 1 if worker else 0)
            struct.pack_into("<I", self.tstats, t * rm.TYPE_STATS_STRIDE, 0x9000000 + t * 0x100 + 0x80)
            struct.pack_into("<h", self.heap, t * 0x100 + 0x82, hp)

    def player(self, p, name, race, res, pop=(5, 20)):
        o = p * rm.PLAYER_SIZE
        self.players[o + 5] = race
        self.players[o + 6] = 0x80
        self.players[o + 8:o + 8 + len(name)] = name.encode()
        struct.pack_into("<hh", self.players, o, pop[1], pop[0])
        for off, v in zip((0x864, 0x868, 0x870, 0x86C), res):
            struct.pack_into("<i", self.players, o + off, v)

    def unit(self, uid, typ, owner, x, y, hp=50, building=0, order=2, producing=0, progress=0.0):
        o = uid * rm.UNIT_SIZE
        struct.pack_into("<HHHHh", self.units, o, 0, building, 0, order, hp)
        struct.pack_into("<hBxhh", self.units, o + 0xE, typ, owner, x, y)
        struct.pack_into("<fh", self.units, o + 0x4C, progress, producing)

    def dispatch(self, player, batch):
        """게임 안 기록 코드(.rkrec)와 같은 방식으로 링 버퍼에 덧붙인다."""
        need = (8 + len(batch) + 3) & ~3
        total, pos = struct.unpack_from("<II", self.ring, 0)
        if pos + need > rrp.RING:
            rem = rrp.RING - pos
            if rem >= 4:
                struct.pack_into("<I", self.ring, 0x10 + pos, rrp.WRAP)
            total += rem; pos = 0
        o = 0x10 + pos
        struct.pack_into("<IBBH", self.ring, o, self.frame, player, 0, len(batch))
        self.ring[o + 8:o + 8 + len(batch)] = batch
        struct.pack_into("<II", self.ring, 0, total + need, pos + need)

    def kill(self, uid):
        struct.pack_into("<h", self.units, uid * rm.UNIT_SIZE + 8, 0)

    def read(self, addr, size):
        regions = ((rm.UNITS, self.units), (rm.PLAYERS, self.players), (rm.UNIT_NAMES, self.names),
                   (rm.TYPE_INFO, self.info), (rm.TYPE_STATS, self.tstats), (0x9000000, self.heap),
                   (rm.MAP_NAME, self.map + bytes(300)), (rm.PLAY_SECONDS, struct.pack("<I", self.seconds)),
                   (rm.LOCAL_PLAYER, b"\x00"), (rm.FRAME, struct.pack("<I", self.frame)),
                   (rm.SEED, struct.pack("<I", self.seed)), (rm.GAME_OPTIONS, bytes(range(8))),
                   (0x400000, self.pe), (self.sec_va + rrp.BUF, self.ring))
        for base, data in regions:
            if base <= addr and addr + size <= base + len(data):
                return bytes(data[addr - base:addr - base + size])
        raise OSError(f"unmapped {addr:#x}")

    def alive(self):
        return True

    def close(self):
        pass


class ParseTests(unittest.TestCase):
    def test_units_players_and_types(self):
        g = FakeGame()
        g.player(0, "aa", 0, [300, 500, 50, 7])
        g.unit(1, 20, 0, 1000, 1200, hp=900, building=1, producing=2, progress=0.5)
        g.unit(2, 7, 0, 1000, 1200)                   # 생산 중
        g.unit(3, 5, 0, 1100, 1300)
        g.unit(4, 7, 1, 2000, 2000, order=0x1002)     # 죽는 중 -> 제외
        units = {u.id: u for u in rm.parse_units(g.units)}
        self.assertEqual(sorted(units), [1, 2, 3])
        self.assertEqual(units[1].flags, rm.F_BUILDING)
        self.assertEqual((units[1].producing, units[1].progress), (2, 0.5))
        self.assertTrue(units[2].flags & rm.F_IN_PRODUCTION)
        self.assertEqual((units[3].x, units[3].y, units[3].owner), (1100, 1300, 0))
        r = rm.GameReader(g)
        p = r.players()[0]
        self.assertEqual((p.name, p.race, p.resources, p.pop), ("aa", 0, [300, 500, 50, 7], (5, 20)))
        types = r.type_table()
        self.assertEqual(types[5], {"name": "일꾼", "worker": True, "max_hp": 40})
        self.assertEqual(types[20]["max_hp"], 900)
        self.assertEqual(r.map_name(), "DATA\\MAPS\\[2]Test.rkm")


class RecordAndModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        game_dir = self.base / "game"
        (game_dir / "DATA" / "MAPS").mkdir(parents=True)
        (game_dir / "DATA" / "MAPS" / "[2]Test.rkm").write_bytes(b"J2M\0fake")
        self.g = FakeGame()
        self.clock = [0.0]
        self.game_dir = game_dir
        self.rec = rr.Recorder(self.base, lambda: str(game_dir), open_memory=lambda pid: self.g,
                               find_pid=lambda: 1234, clock=lambda: self.clock[0])

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, dt=0.5, advance=True):
        if advance and self.g.frame == 0:
            start = struct.pack(rrp.START_FMT, self.g.seed, 77, bytes(20), 0, 0, bytes(8))
            self.g.dispatch(rrp.P_START, start)
            save = self.game_dir / "USERs" / "aa" / "RKREPLAY.SAV"
            save.parent.mkdir(parents=True, exist_ok=True)
            save.write_bytes(b"SAVEDATA" * 100)
        self.clock[0] += dt
        if advance:
            for _ in range(int(dt * 30)):               # 30 프레임/초, 5프레임마다 턴
                self.g.frame += 1
                if self.g.frame % 5 == 0:
                    self.g.dispatch(rrp.P_CHECK, struct.pack(rrp.CHECK_FMT, self.g.frame, 1, 2, self.g.frame * 7, 3))
                    for p in (0, 1):
                        self.g.dispatch(p, struct.pack("<HHIH", 0x2000, 10, self.g.frame // 5, 7))
        if advance and int(self.clock[0]) != int(self.clock[0] - dt):
            self.g.seconds += 1
        self.rec.poll()

    def play_match(self):
        g = self.g
        self.rec.poll()                               # 런처는 경기 전(로비)부터 게임에 붙어 있음
        g.player(0, "aa", 0, [300, 500, 50, 0])
        g.player(1, "big", 2, [300, 500, 50, 0])
        g.unit(1, 20, 0, 1000, 1000, hp=900, building=1)
        g.unit(2, 5, 0, 1100, 1000)
        g.unit(10, 20, 1, 3000, 3000, hp=900, building=1)
        g.seconds = 1
        for k in range(10):                           # 10초: 일꾼 이동, 금 증가
            g.unit(2, 5, 0, 1100 + 20 * k, 1000)
            g.player(0, "aa", 0, [300 + 10 * k, 500, 50, 0])
            self.step(); self.step()
        g.unit(10, 20, 1, 3000, 3000, hp=900, building=1, producing=11, progress=0.4)
        g.unit(11, 7, 1, 3000, 3000)                  # 생산 중 (그리지 않음)
        self.step(); self.step()
        g.unit(10, 20, 1, 3000, 3000, hp=900, building=1)
        g.unit(11, 7, 1, 3100, 3050)                  # 생산 완료
        for _ in range(6):
            self.step()
        g.kill(2)                                     # aa 의 일꾼 죽음
        for _ in range(50):
            self.step()
        for _ in range(10):                           # 일시정지: 기록 안 함
            self.step(advance=False)

    def test_record_load_and_stats(self):
        self.play_match()
        self.assertIsNotNone(self.rec.writer)
        self.g.seconds = 0                            # 새 경기 -> 파일 닫힘
        self.step(advance=False)
        self.assertIsNone(self.rec.writer)
        files = list((self.base / "replays").glob("*.rkr"))
        self.assertEqual(len(files), 1)
        h, dur = M.load_header(files[0])
        self.assertEqual([(p["name"], p["race"]) for p in h["players"]], [("aa", 0), ("big", 2)])
        self.assertEqual(h["map"], "DATA\\MAPS\\[2]Test.rkm")
        self.assertEqual((h["seed"], h["options"], h["commands"], h["format"]), (0x1234ABCD, "0001020304050607", True, 3))
        rp = M.load(files[0])
        self.assertEqual(rp.map_bytes(), b"J2M\0fake")
        self.assertAlmostEqual(rp.duration, dur)
        self.assertGreater(rp.duration, 30)
        self.assertGreaterEqual(len(rp.keys), 2)        # 20초마다 키 장면
        units, fr = rp.state_at(5.0)
        self.assertEqual(sorted(units), [1, 2, 10])
        self.assertEqual(units[2][1], 5)
        units, fr = rp.state_at(11.6)
        self.assertNotIn(11, units)                   # 생산 중인 유닛은 아직 안 보임
        self.assertEqual(fr["b"][0][:2], [10, 7])
        units, _ = rp.state_at(rp.duration)
        self.assertEqual(sorted(units), [1, 10, 11])
        # 명령 기록: 프레임 순서대로, 두 플레이어 모두, 5프레임 간격, 빠짐 없음
        cmds = [c for fr in rp.frames for c in fr.get("cmd", ())]
        frames = [c[0] for c in cmds]
        self.assertEqual(frames, sorted(frames))
        p0 = [c[0] for c in cmds if c[1] == 0]
        self.assertTrue(all(b - a == 5 for a, b in zip(p0, p0[1:])), p0[:10])
        self.assertEqual(len(p0), len([c for c in cmds if c[1] == 1]))
        import base64 as b64
        self.assertEqual(struct.unpack("<HHIH", b64.b64decode(cmds[0][2]))[0], 0x2000)
        self.assertIn("f", rp.frames[1])
        starts = [fr["start"] for fr in rp.frames if "start" in fr]
        self.assertEqual(len(starts), 1)
        self.assertEqual((starts[0]["seed"], starts[0]["rand"], starts[0]["local"]), (0x1234ABCD, 77, 0))
        saves = [fr for fr in rp.frames if "save" in fr]
        self.assertEqual(len(saves), 1)
        self.assertEqual(b64.b64decode(saves[0]["save"]), b"SAVEDATA" * 100)
        chk = [c for fr in rp.frames for c in fr.get("chk", ())]
        self.assertTrue(chk and all(c[3] == c[0] * 7 for c in chk))
        self.assertEqual([c[0] for c in chk], sorted(c[0] for c in chk))
        st = M.stats(rp)["players"]
        self.assertEqual(st[1]["units"], {"검사": 1})
        self.assertEqual(st[0]["lost_units"], 1)
        self.assertEqual(st[0]["final_resources"][0], 390)
        self.assertEqual(st[1]["peak_army"], 1)
        self.assertIn("big (마르두크)", M.summary_text(rp))
        # 보간: 이동 중인 일꾼 위치는 두 장면 사이 값
        i = rp.index_at(3.0)
        a = rp.units_at_index(i)[2][3]
        b = rp.units_at_index(i + 1)[2][3]
        mid = rp.state_at((rp.times[i] + rp.times[i + 1]) / 2)[0][2][3]
        self.assertTrue(min(a, b) <= mid <= max(a, b))

    def test_short_or_idle_sessions_leave_no_file(self):
        self.g.player(0, "aa", 0, [0, 0, 0, 0])
        self.g.seconds = 5
        self.step(advance=False)                      # 로비에 남은 이전 시간: 한 장면뿐
        for _ in range(10):
            self.step(advance=False)
        self.rec._finish()
        self.assertEqual(list((self.base / "replays").glob("*.rkr")), [])

    def test_game_closed_finishes_file(self):
        self.play_match()
        self.rec.find_pid = lambda: None
        self.rec._drop()
        self.assertEqual(len(list((self.base / "replays").glob("*.rkr"))), 1)


class CommandRingTests(unittest.TestCase):
    def test_reader_handles_wrap_and_overflow(self):
        g = FakeGame()
        rd = rrp.CommandReader(g.read, rrp.find_section(g.read))
        self.assertEqual(rd.poll(), ([], 0))
        big = bytes(range(256)) * 15                    # 3840 바이트 묶음
        got = []
        for k in range(rrp.RING // 3000):               # 링을 한 바퀴 넘게 (중간에 자주 읽음)
            g.frame = k
            g.dispatch(k % 3, big[:100 + k % 50])
            if k % 50 == 0:
                c, lost = rd.poll(); got += c; self.assertEqual(lost, 0)
            if k % 7 == 0:
                g.dispatch(1, big)
        c, lost = rd.poll(); got += c
        self.assertEqual(lost, 0)
        main = [x for x in got if len(x[2]) != len(big)]
        self.assertEqual([x[0] for x in main], list(range(rrp.RING // 3000)))
        self.assertTrue(all(x[2] == big[:100 + x[0] % 50] and x[1] == x[0] % 3 for x in main))
        for _ in range(rrp.RING // 1000):               # 읽지 않고 링보다 많이 쓰면 잃은 양을 알려 줌
            g.dispatch(0, big)
        c, lost = rd.poll()
        self.assertGreater(lost, 0)

    def test_in_game_code_writes_same_layout(self):
        """실제 .rkrec 코드를 에뮬레이터로 실행: 기록 형식과 원래 0x4407E0 호출이 그대로인지."""
        try:
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP
        except ImportError as e:
            self.skipTest(str(e))
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        base = 0x1084000
        mu.mem_map(0x400000, 0x100000)                 # 0x4407E0 (가짜), 0x44AAC1
        mu.mem_map(0xB00000, 0x100000)                 # 프레임 번호
        mu.mem_map(base, rrp.VIRTUAL_SIZE)
        mu.mem_map(0x2000000, 0x100000)
        mu.mem_write(base, rrp.body())
        mu.mem_write(0x4407E0, b"\xc3")
        mu.mem_write(0x44AAC1, b"\xf4")
        seen = []
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, s, _: seen.append(struct.unpack("<III", uc.mem_read(uc.reg_read(UC_X86_REG_ESP) + 4, 12))),
                    begin=0x4407E0, end=0x4407E0)
        rd = rrp.CommandReader(lambda a, n: bytes(mu.mem_read(a, n)), base)
        rd.poll()
        batches = [(3, b"\x00\x20\x0a\x00" + bytes(range(6))), (1, b"\x02\x40" + bytes(51)), (0, b"")]
        for k, (player, data) in enumerate(batches * 3):
            mu.mem_write(rrp.FRAME, struct.pack("<I", 1000 + 5 * k))
            mu.mem_write(0x2010000, data)
            esp = 0x2080000
            mu.mem_write(esp, struct.pack("<IIII", 0x44AAC1, player, 0x2010000, len(data)))
            mu.reg_write(UC_X86_REG_ESP, esp)
            mu.emu_start(base, 0x44AAC1, count=10000)
            self.assertEqual(seen[-1], (player, 0x2010000, len(data)))   # 원래 함수에 같은 인자
            self.assertEqual(mu.reg_read(UC_X86_REG_ESP), esp + 4)
        got, lost = rd.poll()
        self.assertEqual(lost, 0)
        self.assertEqual([(f, p, b) for f, p, b in got],
                         [(1000 + 5 * k, p, d) for k, (p, d) in enumerate(batches * 3)])


class RecordPatchTests(unittest.TestCase):
    def test_patch_roundtrip_in_every_combination(self):
        exe = Path(__file__).resolve().parent / "game_backup" / "Rhakmu.exe"
        if not exe.is_file():
            self.skipTest("game_backup/Rhakmu.exe 없음")
        import hotkey_patch as hk, minimap_patch as mm, selection_patch as sp
        o = exe.read_bytes()
        try:
            self.assertEqual(rrp.assemble(), rrp.CODE.ljust(rrp.NAME_OFF, b"\0"))
        except ImportError:
            pass
        for wide in (False, True):
            for hot in (False, True):
                off = mm.build(o, False, True, hot, wide, False)
                on = mm.build(o, False, True, hot, wide, True)
                under = hk.strip(on)
                self.assertTrue(rrp.state(under))
                self.assertFalse(rrp.state(hk.strip(off)))
                self.assertEqual(rrp.strip(under), hk.strip(off))
                self.assertEqual(mm.build(on, False, True, hot, wide, False), off)
                self.assertEqual(mm.build(off, False, True, hot, wide, True), on)
                self.assertEqual(sp.state(rrp.strip(under)), wide)
                sec = rrp.find_section(lambda a, n: __import__("pefile").PE(data=on).get_memory_mapped_image()[a - 0x400000:a - 0x400000 + n])
                self.assertIsNotNone(sec)
                site = on[rrp.SITE:rrp.SITE + 5]
                self.assertEqual(rrp.SITE_VA + 5 + struct.unpack("<i", site[1:])[0], sec)   # 호출이 섹션 코드로


class InGameHookTests(unittest.TestCase):
    """시작 저장·턴 검사값 코드를 에뮬레이터로 실행."""
    BASE = 0x1084000

    def machine(self):
        try:
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EAX, UC_X86_REG_EBP
        except ImportError as e:
            self.skipTest(str(e))
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, 0xC00000)                 # 게임 코드·데이터 (0x400000..0x1000000)
        mu.mem_map(self.BASE, rrp.VIRTUAL_SIZE)
        mu.mem_map(0x2000000, 0x100000)
        mu.mem_write(self.BASE, rrp.body())
        self.saved = []

        def save(uc, a, s, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            p = struct.unpack("<I", uc.mem_read(esp + 4, 4))[0]
            self.saved.append(bytes(uc.mem_read(p, 16)).split(b"\0")[0])
            uc.reg_write(UC_X86_REG_EAX, 1)
        mu.mem_write(0x4D9120, b"\xc3")
        mu.hook_add(UC_HOOK_CODE, save, begin=0x4D9120, end=0x4D9120)
        # Windows API 대체 (stdcall): 주소 -> (인자 수, 처리)
        STUB = 0x3000000
        mu.mem_map(STUB, 0x1000)
        self.files, self.dirs, self.keys, self.calls = {}, [], set(), []
        self.names_at_save = []

        def arg(uc, k):
            return struct.unpack("<I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP) + 4 + 4 * k, 4))[0]

        def cstr(uc, a):
            return bytes(uc.mem_read(a, 64)).split(b"\0")[0]

        def create_dir(uc):
            self.dirs.append(cstr(uc, arg(uc, 0)))
            return 1

        def create_file(uc):
            name = cstr(uc, arg(uc, 0))
            return 0x55 if name in self.files else 0xFFFFFFFF

        def read_file(uc):
            data = self.files[b"RKREPLAY.RKP"][:arg(uc, 2)]
            uc.mem_write(arg(uc, 1), data)
            uc.mem_write(arg(uc, 3), struct.pack("<I", len(data)))
            return 1

        apis = {0x4EC284: (2, create_dir), 0x4EC27C: (7, create_file), 0x4EC260: (5, read_file),
                0x4EC1AC: (1, lambda uc: 1), 0x4EC350: (1, lambda uc: 0xFF80 if arg(uc, 0) in self.keys else 0)}
        for k, (imp, (n, fn)) in enumerate(apis.items()):
            at = STUB + 0x20 * k
            mu.mem_write(at, b"\xc2" + struct.pack("<H", 4 * n))
            mu.mem_write(imp, struct.pack("<I", at))
            mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _, fn=fn: uc.reg_write(UC_X86_REG_EAX, fn(uc)), begin=at, end=at)
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: self.names_at_save.append(cstr(uc, 0x6E61F4)), begin=0x4D9120, end=0x4D9120)
        # 게임 함수 대체: 지도 공개, 명령 실행, 0x447AF0 본문(끝부분)
        mu.mem_write(0x4991E0, b"\xc3")
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: self.calls.append(("reveal", uc.reg_read(UC_X86_REG_ECX))), begin=0x4991E0, end=0x4991E0)
        mu.mem_write(0x4407E0, b"\xc3")
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: self.calls.append(
            ("dispatch", arg(uc, 0) & 0xFF, bytes(uc.mem_read(arg(uc, 1), arg(uc, 2))))), begin=0x4407E0, end=0x4407E0)
        mu.mem_write(0x447AF6, b"\x8b\xe5\x5d\xc3")              # mov esp,ebp; pop ebp; ret (원래 함수 끝)
        mu.hook_add(UC_HOOK_CODE, lambda uc, a, sz, _: self.calls.append(("send",)), begin=0x447AF6, end=0x447AF6)
        self.regs = (UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EBP)
        rd = rrp.CommandReader(lambda a, n: bytes(mu.mem_read(a, n)), self.BASE)
        rd.poll()
        return mu, rd

    def test_start_hook_records_state_and_saves(self):
        mu, rd = self.machine()
        ESP, ECX, EBP = self.regs
        mu.mem_write(0x6E1A78, struct.pack("<I", 0xCAFEBABE))
        mu.mem_write(0x501EC0, struct.pack("<I", 0x12345678))
        mu.mem_write(0xB40FE8, bytes(range(1, 21)))
        mu.mem_write(rrp.FRAME, struct.pack("<I", 4321))
        mu.mem_write(0xB412CC, b"\x02")
        mu.mem_write(0x6DFF88, bytes(range(10, 18)))
        mu.mem_write(0xB411A4, struct.pack("<I", 0x2222))
        mu.mem_write(0x4D7559, b"\xf4")
        for nosave in (0, 1):
            mu.mem_write(self.BASE + rrp.FLAGS_OFF, struct.pack("<I", nosave))   # body() 기본은 1 (끔)
            esp = 0x2080000
            mu.mem_write(esp, struct.pack("<I", 0x4D7559))
            mu.reg_write(ESP, esp)
            mu.reg_write(EBP, 0x1111)
            mu.emu_start(self.BASE + rrp.OFF["start"], 0x4D7559, count=10000)
            self.assertEqual(mu.reg_read(ECX), 0x2222)             # 원래 mov ecx,[0xB411A4]
            self.assertEqual(mu.reg_read(EBP), 0x1111)
            self.assertEqual(mu.reg_read(ESP), esp + 4)
        self.assertEqual(self.saved, [b"RKREPLAY"])                # 두 번째는 저장 끄기
        self.assertEqual(struct.unpack("<I", mu.mem_read(self.BASE + rrp.FLAGS_OFF + 4, 4))[0], 1)
        got, _ = rd.poll()
        self.assertEqual([(f, p) for f, p, b in got], [(4321, rrp.P_START)] * 2)
        st = rrp.parse_start(got[0][2])
        self.assertEqual(st, {"seed": 0xCAFEBABE, "rand": 0x12345678, "rng": bytes(range(1, 21)).hex(),
                              "frame": 4321, "local": 2, "options": bytes(range(10, 18)).hex()})

    def test_record_start_save_uses_player_name_folder(self):
        mu, rd = self.machine()
        ESP, ECX, EBP = self.regs
        mu.mem_write(0xB412CC, b"\x01")
        mu.mem_write(0x7F7910 + 0x11E0, b"big\0")
        mu.mem_write(0x6E61F4, b"RhakMu\0")
        mu.mem_write(self.BASE + rrp.FLAGS_OFF, struct.pack("<I", 0))   # 시작 저장 켬
        mu.mem_write(0x4D7559, b"\xf4")
        esp = 0x2080000
        mu.mem_write(esp, struct.pack("<I", 0x4D7559))
        mu.reg_write(ESP, esp)
        mu.emu_start(self.BASE + rrp.OFF["start"], 0x4D7559, count=20000)
        self.assertEqual(self.dirs, [b"USERs\\big"])
        self.assertEqual(self.saved, [b"RKREPLAY"])
        self.assertEqual(self.names_at_save, [b"big"])                 # 저장 경로 USERs\big\RKREPLAY.SAV
        self.assertEqual(bytes(mu.mem_read(0x6E61F4, 7)), b"RhakMu\0")   # 계정 이름 되돌림

    def play_machine(self, records, start_frame=100):
        mu, rd = self.machine()
        mu.mem_write(self.BASE, rrp.body(play=True))
        start = {"frame": start_frame, "rand": 0x11111111, "rng": bytes(range(40, 60)).hex(), "seed": 0x2222}
        self.files[b"RKREPLAY.RKP"] = rrp.build_rkp(start, records)
        return mu

    def run_entry(self, mu, entry, ret):
        ESP, ECX, EBP = self.regs
        mu.mem_write(ret, b"\xf4")
        esp = 0x2080000
        mu.mem_write(esp, struct.pack("<I", ret))
        mu.reg_write(ESP, esp)
        mu.reg_write(EBP, 0x6666)
        mu.emu_start(self.BASE + rrp.OFF[entry], ret, count=200000)
        self.assertEqual(mu.reg_read(ESP), esp + 4)
        self.assertEqual(mu.reg_read(EBP), 0x6666)

    def flags(self, mu):
        return rrp.read_flags(lambda a, n: bytes(mu.mem_read(a, n)), self.BASE)

    def test_play_start_loads_file_restores_state_and_reveals_map(self):
        mu = self.play_machine([(105, 0, b"\x00\x20\x0a\x00abcdef")])
        mu.mem_write(0xB412C8, struct.pack("<H", 0x8))
        self.run_entry(mu, "start", 0x4D7559)
        self.assertEqual(struct.unpack("<I", mu.mem_read(0x501EC0, 4))[0], 0x11111111)
        self.assertEqual(bytes(mu.mem_read(0xB40FE8, 20)), bytes(range(40, 60)))
        self.assertEqual(struct.unpack("<I", mu.mem_read(0x6E1A78, 4))[0], 0x2222)
        self.assertEqual(struct.unpack("<I", mu.mem_read(rrp.FRAME, 4))[0], 100)
        self.assertEqual(struct.unpack("<H", mu.mem_read(0xB412C8, 2))[0], 0x9)          # 지도 공개 비트
        self.assertIn(("reveal", 0x915698), self.calls)
        self.assertEqual(self.saved, [])                                                # 재생 땐 저장 안 함
        self.assertEqual(self.flags(mu)["diverged"], 0)

    def test_play_start_without_file_flags_missing_data(self):
        mu = self.play_machine([])
        del self.files[b"RKREPLAY.RKP"]
        self.run_entry(mu, "start", 0x4D7559)
        self.assertEqual(self.flags(mu)["diverged"], 0xFFFFFFFF)

    def test_play_feeds_recorded_batches_on_turn_frames(self):
        b1, b2, b3 = b"\x00\x20\x0a\x00" + bytes(6), b"\x02\x40" + bytes(51), b"\x03\x40ABC"
        chk_ok = struct.pack(rrp.CHECK_FMT, 105, 0x11111111, 0, 0, 0)       # 유닛 없음: 해시 0, 수 0
        chk_bad = struct.pack(rrp.CHECK_FMT, 110, 0x99999999, 0, 0, 0)
        recs = [(105, rrp.P_CHECK, chk_ok), (105, 0, b1), (105, 1, b2), (110, rrp.P_CHECK, chk_bad), (110, 0, b3), (115, 1, b1)]
        mu = self.play_machine(recs)
        self.run_entry(mu, "start", 0x4D7559)
        for frame in range(100, 113):
            mu.mem_write(rrp.FRAME, struct.pack("<I", frame))
            self.calls.clear()
            if frame == 110:
                self.keys = {0x32}
            self.run_entry(mu, "send", 0x4D79FB)
            if frame % 5:
                self.assertEqual(self.calls, [], frame)                   # 5프레임마다만 (멀티 루프와 같은 rand 소비)
            else:
                self.assertEqual(self.calls[0], ("send",), frame)        # 원래 0x447AF0 (rand 1회)
                got = [c[1:] for c in self.calls if c[0] == "dispatch"]
                want = {100: [], 105: [(0, b1), (1, b2)], 110: [(0, b3)]}[frame]
                self.assertEqual(got, want, frame)
        f = self.flags(mu)
        self.assertEqual(f["fed"], 3)
        self.assertEqual(f["diverged"], 110)                              # 첫 어긋남
        self.assertEqual(struct.unpack("<I", mu.mem_read(0xB412B8, 4))[0], 16)   # 2 키 -> 2배속

    def test_play_turn_hook_skips_live_dispatch(self):
        from unicorn.x86_const import UC_X86_REG_EAX
        mu = self.play_machine([])
        mu.mem_write(0x44A846, b"\xcc")                                  # 원래 함수로 가면 안 됨
        self.run_entry(mu, "turn", 0x4D7A18)
        self.assertEqual(mu.reg_read(UC_X86_REG_EAX) & 0xFF, 1)

    def test_play_game_loop_hook_turns_on_save_loading(self):
        """게임에 불러오기 메뉴가 없음: 재생 모드 싱글 게임이면 Game_Loop 의 저장 불러오기 경로를 켠다."""
        from unicorn.x86_const import UC_X86_REG_EAX
        for play, multi, already, want_flag, want_name in (
                (True, 0, 0, 1, b"RKREPLAY\0"), (False, 0, 0, 0, b"\0" * 9),
                (True, 1, 0, 0, b"\0" * 9), (True, 0, 2, 2, b"\0" * 9)):
            mu = self.play_machine([]) if play else self.machine()[0]
            mu.mem_write(0xB412CB, bytes([multi]))
            mu.mem_write(0x6DFF8D, bytes([already]))
            mu.mem_write(0x6E62F4, b"\0" * 16)
            self.run_entry(mu, "load", 0x4D731E)
            self.assertEqual(mu.mem_read(0x6DFF8D, 1)[0], want_flag, (play, multi, already))
            self.assertEqual(mu.reg_read(UC_X86_REG_EAX), want_flag)            # 원래 movsx eax, [0x6DFF8D]
            self.assertEqual(bytes(mu.mem_read(0x6E62F4, 9)), want_name)

    def test_upgrade_from_v0_9055_install(self):
        exe = Path(__file__).resolve().parent / "game_backup" / "Rhakmu.exe"
        if not exe.is_file():
            self.skipTest("game_backup/Rhakmu.exe 없음")
        import subprocess, types
        src = subprocess.run(["git", "show", "0ae10e0:replay_record_patch.py"], capture_output=True,
                             cwd=Path(__file__).resolve().parent).stdout.decode("utf-8")
        if not src:
            self.skipTest("git 기록 없음")
        old = types.ModuleType("rrp_9055")
        exec(compile(src, "rrp_9055", "exec"), old.__dict__)
        import minimap_patch as mm
        o = mm.build(exe.read_bytes(), False, True, False, False, False)      # 단축키 없음, 기록 없음
        for save in (False, True):
            for play in (False, True):
                installed = old.apply(o, True, save, play)
                self.assertTrue(rrp.state(installed))
                self.assertFalse(rrp.plays(installed))
                self.assertEqual(rrp.strip(installed), o)
                new = rrp.apply(installed, True, save, play)
                self.assertEqual(new, rrp.apply(o, True, save, play))
                self.assertEqual(rrp.plays(new), play)

    def test_recorded_match_plays_back_identically(self):
        """기록(가짜 게임) -> 리플레이 파일 -> .rkp -> 실제 재생 코드: 같은 명령이 같은 프레임·순서로 실행."""
        t = RecordAndModelTests("test_record_load_and_stats")
        t.setUp()
        try:
            t.play_match()
            t.rec._finish()
            rp = M.load(next((t.base / "replays").glob("*.rkr")))
        finally:
            t.tearDown()
        data = M.ingame_data(rp)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["save"], b"SAVEDATA" * 100)
        want = [(r[0], r[1], r[2]) for r in data["records"] if r[1] < 8]
        self.assertGreater(len(want), 20)
        recs = [r for r in data["records"] if r[1] < 8]                 # 검사값은 가짜라 빼고 명령만
        mu = self.play_machine(recs, start_frame=data["start"]["frame"])
        self.run_entry(mu, "start", 0x4D7559)
        got = []
        for frame in range(data["start"]["frame"], max(r[0] for r in want) + 6):
            mu.mem_write(rrp.FRAME, struct.pack("<I", frame))
            self.calls.clear()
            self.run_entry(mu, "send", 0x4D79FB)
            got += [(frame, c[1], c[2]) for c in self.calls if c[0] == "dispatch"]
        self.assertEqual(got, want)
        self.assertEqual(self.flags(mu)["diverged"], 0)

    def test_ingame_data_requires_start_and_save(self):
        rp = M.Replay(Path("x"), {"players": []}, [{"t": 0, "cmd": [[5, 0, "AA=="]]}], [0], [0])
        self.assertIn("시작 기록", M.ingame_data(rp))
        rp.frames[0]["start"] = {"frame": 0, "rand": 0, "rng": "00" * 20, "seed": 0, "local": 0}
        self.assertIn("시작 저장", M.ingame_data(rp))

    def test_rkp_layout(self):
        st = {"frame": 7, "rand": 1, "rng": "00" * 20, "seed": 2}
        blob = rrp.build_rkp(st, [(10, 0, b"abc"), (15, rrp.P_CHECK, bytes(20))])
        self.assertEqual(blob[:4], rrp.RKP_MAGIC)
        n, cur, frame = struct.unpack_from("<III", blob, 4)
        self.assertEqual((n, cur, frame), (len(blob) - rrp.RKP_HEAD, 0, 7))
        self.assertEqual(struct.unpack_from("<I", blob, 0x2C)[0], 15)

    def test_turn_hook_checksum_and_prologue(self):
        mu, rd = self.machine()
        ESP, ECX, EBP = self.regs
        units = {3: (50, 1000, 2000, 7), 9: (5, 300, 400, 5), 12: (0, 1, 1, 7)}
        for uid, (hp, x, y, t) in units.items():
            o = 0x775A38 + uid * 0x138
            mu.mem_write(o + 8, struct.pack("<h", hp))
            mu.mem_write(o + 0xE, struct.pack("<h", t))
            mu.mem_write(o + 0x12, struct.pack("<hh", x, y))
        mu.mem_write(0x501EC0, struct.pack("<I", 99))
        mu.mem_write(0xB40FF8, struct.pack("<I", 1234))
        mu.mem_write(rrp.FRAME, struct.pack("<I", 500))
        mu.mem_write(0x44A846, b"\xf4")                          # 원래 함수 이어서
        esp = 0x2080000
        mu.mem_write(esp, struct.pack("<I", 0xDEAD))              # 호출자 복귀 주소
        mu.reg_write(ESP, esp)
        mu.reg_write(EBP, 0x7777)
        mu.emu_start(self.BASE + rrp.OFF["turn"], 0x44A846, count=200000)
        self.assertEqual(mu.reg_read(ESP), esp - 4 - 0x44)        # push ebp; mov ebp,esp; sub esp,0x44
        self.assertEqual(mu.reg_read(EBP), esp - 4)
        self.assertEqual(struct.unpack("<I", mu.mem_read(esp - 4, 4))[0], 0x7777)
        h, n = 0, 0
        for uid in sorted(units):
            hp, x, y, t = units[uid]
            if hp <= 0:
                continue
            n += 1
            h = (h * 31 + hp) & 0xFFFFFFFF
            h = (h * 31 + (x | y << 16)) & 0xFFFFFFFF
            h = (h * 31 + t) & 0xFFFFFFFF
        got, _ = rd.poll()
        self.assertEqual([(f, p) for f, p, b in got], [(500, rrp.P_CHECK)])
        self.assertEqual(rrp.parse_check(got[0][2]), [500, 99, 1234, h, n])


class ViewerTests(unittest.TestCase):
    def test_viewer_keys_click_and_escape(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as e:
            self.skipTest(f"Tk 없음: {e}")
        root.withdraw()
        t = RecordAndModelTests("test_record_load_and_stats")
        t.setUp()
        try:
            t.play_match()
            t.rec._finish()
            path = next((t.base / "replays").glob("*.rkr"))
            import replay_viewer as V
            v = V.ReplayViewer(root, path, None, autoplay=False)
            v.update()
            for key, sp in (("2", 2.0), ("4", 4.0), ("1", 1.0)):
                v.event_generate(key)
                v.set_speed(V.SPEEDS[key])
                self.assertEqual(v.speed, sp)
            v.seek(12.5)
            v.update()
            sx, sy = v.to_screen(3000, 3000)
            v.click(type("E", (), {"x": sx, "y": sy})())
            self.assertEqual(v.selected, 10)
            self.assertIn("생산 중", " ".join(v.cv.itemcget(i, "text") for i in v.cv.find_all()
                                             if v.cv.type(i) == "text"))
            v.show_stats()
            v.update()
            v.close()
            self.assertFalse(v.winfo_exists())
        finally:
            t.tearDown()
            root.destroy()

    def test_viewer_with_real_map(self):
        game = Path(r"C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps\[4]Abstruse.rkm")
        res = Path(__file__).resolve().parent
        if not game.is_file() or not (res / "map_preview_tiles").is_dir():
            self.skipTest("게임 맵 없음")
        import base64, gzip, json
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x.rkr")
            with gzip.open(p, "wt", encoding="utf-8") as f:
                f.write(json.dumps({"format": 1, "map": "DATA\\MAPS\\[4]Abstruse.rkm", "players": [{"index": 0, "name": "aa", "race": 1}],
                                    "map_rkm": base64.b64encode(game.read_bytes()).decode(), "types": {}}) + "\n")
                f.write(json.dumps({"t": 0, "k": [[1, 7, 0, 2000, 2000, 50, 0]], "p": [[1, 2, 3, 4, 5, 6]]}) + "\n")
                f.write(json.dumps({"t": 1, "c": [[1, 7, 0, 2100, 2000, 50, 0]]}) + "\n")
            import replay_viewer as V
            v = V.ReplayViewer(root, p, str(res), autoplay=False)
            v.update()
            self.assertIsNotNone(v._map_img)
            z, ox, oy = v._view()
            self.assertAlmostEqual((z * v.scale) % 1 if z * v.scale >= 1 else (1 / (z * v.scale)) % 1, 0, places=6)
            v.close()
        root.destroy()


if __name__ == "__main__":
    unittest.main()
