"""Joins between different game versions are refused by the server (the host's game would bounce
the joiner to the lobby and leave a ghost member), and same-version joins still work."""
import asyncio
import struct
import unittest

import server
from test_server_ingame import sess


def handshake(c, version):
    asyncio.run(c._handle(server.P_CONNECT, b'RHAK' + struct.pack('<I', version)))


class VersionTests(unittest.TestCase):
    def setUp(self):
        server.STATE.clients.clear()
        server.STATE.rooms.clear()
        self.host = sess('26.0.0.1', 'aa')
        self.room = server.Room(id=1, title='aa', map_name='m', owner='aa', host_ip='26.0.0.1', max_players=4)
        server.STATE.rooms.append(self.room)
        self.host.room_title = 'aa'

    def test_handshake_records_version(self):
        handshake(self.host, 1003)
        self.assertEqual(self.host.game_version, 1003)

    def test_mismatched_join_refused_without_ghost_member(self):
        handshake(self.host, 1003)
        guest = sess('26.0.0.2', 'big')
        handshake(guest, 1000)
        guest.writer.data = self.host.writer.data = b''
        with self.assertLogs(server.log, 'WARNING') as logs:
            asyncio.run(guest._handle_join_room(server.nul('aa')))
        self.assertEqual(guest.writer.data, server.pack_pkt(server.P_JOIN_ROOM, struct.pack('<I', 1)))
        self.assertNotIn('big', self.room.members)
        self.assertEqual(guest.room_title, '')
        self.assertEqual(self.host.writer.data, b'')
        self.assertIn('1000 != host 1003', logs.output[0])

    def test_same_version_join_works(self):
        handshake(self.host, 1003)
        guest = sess('26.0.0.2', 'nyai')
        handshake(guest, 1003)
        guest.writer.data = b''
        asyncio.run(guest._handle_join_room(server.nul('aa')))
        self.assertIn('nyai', self.room.members)
        reply = server.pack_pkt(server.P_JOIN_ROOM, b'\0' + server.nul('aa') + server.nul('26.0.0.1'))
        self.assertTrue(guest.writer.data.startswith(reply))

    def test_unknown_version_is_not_blocked(self):
        guest = sess('26.0.0.2', 'nyai')                 # no handshake recorded (0)
        asyncio.run(guest._handle_join_room(server.nul('aa')))
        self.assertIn('nyai', self.room.members)


if __name__ == '__main__':
    unittest.main()
