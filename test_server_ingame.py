"""Lobby packets must not reach players in battle; joins to a running game are refused."""
import asyncio
import struct
import unittest

import server


class W:
    def __init__(self, ip):
        self.ip, self.data = ip, b''
    def get_extra_info(self, k):
        return (self.ip, 1234)
    def write(self, b):
        self.data += b
    async def drain(self):
        pass


def sess(ip, account):
    c = server.ClientSession(None, W(ip))
    c.account = account
    server.STATE.clients.append(c)
    return c


def types(data):
    out, i = [], 0
    while i + 4 <= len(data):
        t, n = struct.unpack_from('<HH', data, i)
        out.append(t)
        i += max(n, 4)
    return out


class InGameTests(unittest.TestCase):
    def setUp(self):
        server.STATE.clients.clear()
        server.STATE.rooms.clear()

    def test_join_refused_and_no_user_list_in_battle(self):
        host = sess('26.0.0.1', 'seo')
        room = server.Room(id=1, title='seo', map_name='m', owner='seo', host_ip='26.0.0.1', max_players=4)
        server.STATE.rooms.append(room)
        host.room_title = 'seo'
        asyncio.run(host._handle_game_start(b'\x02\x00\x00'))
        self.assertTrue(room.in_game and host.in_game)
        host.writer.data = b''
        guest = sess('26.0.0.2', 'nyai')
        asyncio.run(guest._handle_join_room(server.nul('seo')))
        self.assertEqual(guest.writer.data, server.pack_pkt(server.P_JOIN_ROOM, struct.pack('<I', 1)))
        self.assertNotIn('nyai', room.members)
        self.assertEqual(host.writer.data, b'')          # nothing sent to the player in battle
        # after the game the room accepts players again
        host._end_game()
        self.assertFalse(room.in_game)
        asyncio.run(guest._handle_join_room(server.nul('seo')))
        self.assertIn('nyai', room.members)
        self.assertIn(server.P_USER_LIST_ACK, types(host.writer.data))


if __name__ == '__main__':
    unittest.main()
