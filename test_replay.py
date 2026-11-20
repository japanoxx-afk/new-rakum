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
        self.rec = rr.Recorder(self.base, lambda: str(game_dir), open_memory=lambda pid: self.g,
                               find_pid=lambda: 1234, clock=lambda: self.clock[0])

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, dt=0.5, advance=True):
        self.clock[0] += dt
        if advance:
            for _ in range(int(dt * 30)):               # 30 프레임/초, 5프레임마다 턴
                self.g.frame += 1
                if self.g.frame % 5 == 0:
                    for p in (0, 1):
                        self.g.dispatch(p, struct.pack("<HHIH", 0x2000, 10, self.g.frame // 5, 7))
        if advance and int(self.clock[0]) != int(self.clock[0] - dt):
            self.g.seconds += 1
        self.rec.poll()

    def play_match(self):
        g = self.g
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
        self.assertEqual((h["seed"], h["options"], h["commands"], h["format"]), (0x1234ABCD, "0001020304050607", True, 2))
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
            self.assertEqual(rrp.assemble(), rrp.CODE)
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
