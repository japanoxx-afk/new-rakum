"""빈 방이 로비에 남지 않게, 끊긴 접속을 알아채게 (서버 0.9018)."""
import asyncio
import socket
import struct
import unittest

import server
from test_server_chat_rank import W, sess, packets


def create_payload(title, owner):
    # [0:2] ?, [2:4] mode, [4:6] max players, [6:8] time, then strings
    return struct.pack('<HHHH', 0, 0, 4, 0) + server.nul(title) + b'\x01' + server.nul('[2]A.rkm') + b'\x01' + server.nul(owner)


def room_titles(c):
    out = []
    for t, p in packets(c.writer.data):
        if t == server.P_ROOM_LIST_REQ:
            out.append(p[10:].split(b'\0')[0].decode('latin-1'))
    return out


class LobbyCleanupTests(unittest.TestCase):
    def setUp(self):
        server.STATE.clients.clear()
        server.STATE.rooms.clear()

    def make_room(self, c, title='room1'):
        asyncio.run(c._handle(server.P_CREATE_ROOM, create_payload(title, 'zz')))
        c.room_since -= 10                    # 방을 만든 지 조금 지남

    def test_owner_is_the_creating_account(self):
        a = sess('26.0.0.1', '\xb1\xe8')     # 한글 계정 (cp949 바이트)
        self.make_room(a)
        self.assertEqual(server.STATE.rooms[0].owner, a.account)

    def test_room_removed_when_owner_back_in_lobby_without_leave(self):
        a = sess('26.0.0.1', 'aa')
        b = sess('26.0.0.2', 'big')
        self.make_room(a)
        asyncio.run(b._handle(server.P_JOIN_ROOM, server.nul('room1')))
        b.room_since -= 10
        a.in_game = b.in_game = True          # 게임 시작 뒤 결과 보고 없이 로비로 (튕김 등)
        asyncio.run(b._handle(server.P_ROOM_LIST_REQ, b''))
        self.assertEqual(server.STATE.rooms[0].members, [])
        self.assertFalse(b.in_game)
        a.writer.data = b''
        asyncio.run(a._handle(server.P_ROOM_LIST_REQ, b''))
        self.assertEqual(server.STATE.rooms, [])
        self.assertEqual(room_titles(a), [])

    def test_lobby_request_right_after_create_is_ignored(self):
        a = sess('26.0.0.1', 'aa')
        asyncio.run(a._handle(server.P_CREATE_ROOM, create_payload('room1', 'aa')))
        asyncio.run(a._handle(server.P_ROOM_LIST_REQ, b''))
        self.assertEqual(len(server.STATE.rooms), 1)

    def test_rooms_of_disconnected_owner_not_listed(self):
        a = sess('26.0.0.1', 'aa')
        self.make_room(a)
        server.STATE.clients.remove(a)        # 접속은 사라졌는데 정리가 안 된 경우
        v = sess('26.0.0.3', 'viewer')
        asyncio.run(v._handle(server.P_ROOM_LIST_REQ, b''))
        self.assertEqual(room_titles(v), [])
        self.assertEqual(server.STATE.rooms, [])

    def test_live_room_still_listed(self):
        a = sess('26.0.0.1', 'aa')
        self.make_room(a)
        v = sess('26.0.0.3', 'viewer')
        asyncio.run(v._handle(server.P_ROOM_LIST_REQ, b''))
        self.assertEqual(room_titles(v), ['room1'])

    def test_keepalive_enabled_on_real_socket(self):
        s = socket.socket()
        try:
            self.assertTrue(server.enable_keepalive(s))
            self.assertEqual(s.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0, True)
        finally:
            s.close()
        self.assertFalse(server.enable_keepalive(None))


if __name__ == '__main__':
    unittest.main()
