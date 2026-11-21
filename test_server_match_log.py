"""matches.json: 전체 기록 보관(500판 제한 없음), 경기 id, 깨진 파일 보호.
전적 사이트(rtsarena)가 이 파일로 게임 안 랭킹과 같은 리더보드를 만든다."""
import json
import os
import tempfile
import unittest

import server


class MatchLogTests(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old)

    def test_keeps_more_than_500_and_ids(self):
        for i in range(520):
            server.record_match_start("[2]Distant", [f"a{i}", "b"], "room")
        data = json.load(open(server.MATCH_LOG, encoding="utf-8"))
        self.assertEqual(len(data), 520)
        self.assertEqual(len({r["id"] for r in data}), 520)
        self.assertFalse(os.path.exists(server.MATCH_LOG + ".tmp"))

    def test_results_still_recorded(self):
        server.record_match_start("[2]Distant", ["aa", "bb"], "room")
        server.record_match_result("aa", 1, 0)
        server.record_match_result("bb", 2, 0)
        rec = json.load(open(server.MATCH_LOG, encoding="utf-8"))[0]
        self.assertEqual({k: v["wl"] for k, v in rec["results"].items()}, {"aa": "win", "bb": "lose"})

    def test_corrupt_file_is_kept_aside_not_overwritten(self):
        with open(server.MATCH_LOG, "w", encoding="utf-8") as f:
            f.write('[{"time": "2026-11-21 1')
        server.record_match_start("[2]Distant", ["aa", "bb"], "room")
        bad = [n for n in os.listdir(".") if n.startswith(server.MATCH_LOG + ".bad-")]
        self.assertEqual(len(bad), 1)
        self.assertEqual(len(json.load(open(server.MATCH_LOG, encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
