"""런처 exe 에 서버가 쓰는 모듈이 다 들어가고, 한 패킷 처리 오류로 로비 접속이 끊기지 않는다 (서버 0.9020).

0.9064~0.9067 런처 내장 서버는 게임 시작(0x0FFF) 때 record_match_start 의 `import uuid` 가 exe 에
없어 예외가 났고, 그 예외로 방장의 로비 접속이 끊겨 게임이 끝난 뒤 로비가 먹통이 됐다.
"""
import ast
import asyncio
import os
import struct
import unittest
from unittest import mock

import server
from test_server_chat_rank import sess, packets
from test_server_lobby_cleanup import create_payload

HERE = os.path.dirname(os.path.abspath(__file__))


def imported_modules(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = set()
    for node in ast.walk(tree):              # 함수 안의 import 까지
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module)
    return out


class BundledImportsTests(unittest.TestCase):
    def test_launcher_imports_every_module_server_uses(self):
        # server.py 는 exe 안에서 exec 로 돌아 PyInstaller 가 그 import 를 못 본다.
        launcher = imported_modules(os.path.join(HERE, "launcher.py"))
        missing = sorted(m for m in imported_modules(os.path.join(HERE, "server.py"))
                         if m not in launcher and m.split(".")[0] not in launcher)
        self.assertEqual(missing, [], "launcher.py 에서 import 해 exe 에 넣어야 하는 모듈")


class SessionSurvivesErrorsTests(unittest.TestCase):
    def setUp(self):
        server.STATE.clients.clear()
        server.STATE.rooms.clear()

    def test_game_start_still_sent_when_match_record_fails(self):
        a = sess("26.0.0.1", "aa")
        asyncio.run(a._handle(server.P_CREATE_ROOM, create_payload("room1", "aa")))
        a.writer.data = b""
        with mock.patch.object(server, "record_match_start", side_effect=ModuleNotFoundError("uuid")):
            asyncio.run(a._handle(server.P_GAME_START, b"\x02\x00\x00"))
        self.assertIn(server.P_BATTLE_START, [t for t, _ in packets(a.writer.data)])
        self.assertTrue(server.STATE.rooms[0].in_game)

    def test_handler_error_does_not_end_session(self):
        a = sess("26.0.0.1", "aa")
        a._buf = struct.pack("<HH", server.P_CHAT, 4) + struct.pack("<HH", server.P_ROOM_LIST_REQ, 4)
        a.writer.data = b""
        with mock.patch.object(a, "_handle_chat", side_effect=RuntimeError("boom")):
            asyncio.run(a._process())                 # 예외가 밖으로 나오지 않는다
        self.assertIn(server.P_ROOM_LIST_ACK, [t for t, _ in packets(a.writer.data)])   # 다음 패킷도 처리

    def test_post_game_ack_sent_when_result_record_fails(self):
        a = sess("26.0.0.1", "aa")
        a.writer.data = b""
        with mock.patch.object(server, "record_match_result", side_effect=OSError("disk")):
            asyncio.run(a._handle(server.P_POST_GAME, bytes([1, 0, 0, 0, 0])))
        self.assertIn(server.P_POST_GAME_ACK, [t for t, _ in packets(a.writer.data)])


if __name__ == "__main__":
    unittest.main()
