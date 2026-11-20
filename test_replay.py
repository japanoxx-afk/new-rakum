"""리플레이: 메모리 해석, 기록(가짜 게임 메모리), 파일 복원·통계, 보기 창."""
import os
import struct
import tempfile
import unittest
from pathlib import Path

import replay_memory as rm
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
        self.map = b"DATA\\MAPS\\[2]Test.rkm"
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

    def kill(self, uid):
        struct.pack_into("<h", self.units, uid * rm.UNIT_SIZE + 8, 0)

    def read(self, addr, size):
        regions = ((rm.UNITS, self.units), (rm.PLAYERS, self.players), (rm.UNIT_NAMES, self.names),
                   (rm.TYPE_INFO, self.info), (rm.TYPE_STATS, self.tstats), (0x9000000, self.heap),
                   (rm.MAP_NAME, self.map + bytes(300)), (rm.PLAY_SECONDS, struct.pack("<I", self.seconds)),
                   (rm.LOCAL_PLAYER, b"\x00"))
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
