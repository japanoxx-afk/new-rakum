import os
import tempfile
import unittest
from pathlib import Path

import replay_assoc as ra


class ReplayAssocTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.replay = self.dir / "20261122_[4]Map.rkr"
        self.replay.write_bytes(b"x")

    def test_find_replay_arg(self):
        self.assertIsNone(ra.find_replay_arg([]))
        self.assertIsNone(ra.find_replay_arg(["--server", str(self.dir / "none.rkr"), "a.txt"]))
        self.assertEqual(ra.find_replay_arg(["--x", str(self.replay)]), os.path.abspath(self.replay))
        upper = self.dir / "B.RKR"
        upper.write_bytes(b"x")
        self.assertEqual(ra.find_replay_arg([str(upper)]), os.path.abspath(upper))

    def test_request_round_trip(self):
        req = self.dir / "sub" / "open_replay.txt"
        self.assertIsNone(ra.take_request(req))
        ra.write_request(self.replay, req)
        self.assertEqual(ra.take_request(req), str(self.replay))
        self.assertFalse(req.exists())                       # 한 번만
        ra.write_request(self.dir / "gone.rkr", req)         # 없는 파일·다른 종류는 무시
        self.assertIsNone(ra.take_request(req))
        ra.write_request(self.dir / "x.exe", req)
        self.assertIsNone(ra.take_request(req))

    def test_open_command_quotes_paths(self):
        self.assertEqual(ra.open_command(r"C:\Program Files (x86)\R\RhakMuLauncher_v0.9088.exe"),
                         r'"C:\Program Files (x86)\R\RhakMuLauncher_v0.9088.exe" "%1"')

    @unittest.skipUnless(os.name == "nt", "Windows 전용")
    def test_running_mark(self):
        ra.mark_running()
        self.assertTrue(ra.launcher_running())


if __name__ == "__main__":
    unittest.main()
