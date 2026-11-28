import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import diag_report as d
import game_version


class DiagReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.game = self.base / "game"
        self.game.mkdir()
        (self.game / "Rhakmu.exe").write_bytes(b"MZ-test")
        (self.game / "ddraw.ini").write_text("[ddraw]\nwidth=1280\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_error_is_appended_and_shown_in_report(self):
        d.log_error(self.base, "게임 실행 중단", ValueError("WinError 5 테스트"))
        d.log_error(self.base, "게임 실행 중단", ValueError("두 번째"))
        text = d.build_report(self.base, self.game, "0.9114", {"game_dir": str(self.game)})
        self.assertIn("WinError 5 테스트", text)
        self.assertIn("두 번째", text)
        self.assertIn("width=1280", text)                  # ddraw.ini 내용
        self.assertIn("Rhakmu.exe: 7 bytes", text)          # 게임 파일 크기

    def test_secret_settings_are_left_out(self):
        text = d.build_report(self.base, self.game, "0.9114",
                              {"nick": "aa", "arena_token": "SECRET-1", "lobby_password": "pw"})
        self.assertIn("nick = aa", text)
        self.assertNotIn("SECRET-1", text)
        self.assertNotIn("lobby_password", text)

    def test_report_survives_missing_game_folder(self):
        text = d.build_report(self.base, self.base / "nothing", "0.9114", None)
        self.assertIn("설치 폴더", text)
        self.assertIn("Rhakmu.exe: 없음", text)

    def test_write_report_goes_to_given_folder(self):
        path = d.write_report(self.base, self.game, "0.9114", {}, out_dir=self.base)
        self.assertTrue(path.is_file())
        self.assertTrue(path.name.startswith("rhakmu-report-"))


class ReplaceExeErrorTests(unittest.TestCase):
    def test_permission_error_gets_a_clear_message(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t) / "a.tmp"
            tmp.write_bytes(b"x")
            target = Path(t) / "Rhakmu.exe"
            target.write_bytes(b"y")
            with mock.patch("game_version.os.replace", side_effect=PermissionError(13, "denied")):
                with self.assertRaises(ValueError) as ctx:
                    game_version._replace_exe(str(tmp), target)
            self.assertIn("WinError 5", str(ctx.exception))
            self.assertIn("관리자 권한", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
