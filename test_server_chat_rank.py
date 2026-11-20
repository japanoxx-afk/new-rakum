"""Lobby chat and in-game ranking packets use the formats Rhakmu.exe actually parses.

Formats come from the client's lobby dispatcher (Rhakmu.exe 0x44B1D0):
  chat 0x12FF -> 0x44C2B0, rank 0x16FF/0x15FF/0x17FF -> 0x44D050/0x44D0B0/0x44D080,
  rank search 0x14FF -> 0x44D270, account info 0x02FF -> 0x44BB60, game report codes 0x41A9B0.
"""
import asyncio
import json
import os
import shutil
import struct
import tempfile
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


def packets(data):
    out, i = [], 0
    while i + 4 <= len(data):
        t, n = struct.unpack_from('<HH', data, i)
        out.append((t, data[i + 4:i + n]))
        i += max(n, 4)
    return out


def cstrings(b):
    return [s.decode('latin-1') for s in b.split(b'\0')[:-1]]


class TmpMatches(unittest.TestCase):
    def setUp(self):
        server.STATE.clients.clear()
        server.STATE.rooms.clear()
        self.tmp = tempfile.mkdtemp()
        self._old = server.MATCH_LOG
        server.MATCH_LOG = os.path.join(self.tmp, 'matches.json')

    def tearDown(self):
        server.MATCH_LOG = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_matches(self, matches):
        with open(server.MATCH_LOG, 'w', encoding='utf-8') as f:
            json.dump(matches, f)


class ChatTests(TmpMatches):
    def test_chat_is_sent_as_0x12ff_type1_to_lobby_players_only(self):
        a = sess('26.0.0.1', 'seo')
        b = sess('26.0.0.2', 'nyai')
        busy = sess('26.0.0.3', 'gamer')
        busy.in_game = True
        hangul = '안녕'.encode('cp949').decode('latin-1')
        asyncio.run(a._handle(server.P_CHAT, server.nul(hangul) + server.nul('seo')))
        for c in (a, b):
            (t, p), = packets(c.writer.data)
            self.assertEqual(t, 0x12FF)
            self.assertEqual(p[0], 1)                    # client switch: type 1 = lobby chat
            self.assertEqual(cstrings(p[3:]), ['seo', hangul])
        self.assertEqual(busy.writer.data, b'')

    def test_slash_commands_are_not_broadcast(self):
        a = sess('26.0.0.1', 'seo')
        b = sess('26.0.0.2', 'nyai')
        asyncio.run(a._handle(server.P_CHAT, server.nul('/status') + server.nul('seo')))
        self.assertEqual(a.writer.data + b.writer.data, b'')


class ResultTests(TmpMatches):
    def test_result_codes_decide_win_lose(self):
        server.record_match_start('m', ['aa', 'bb'], 'aa')
        server.record_match_result('aa', 1, 0)
        server.record_match_result('bb', 2, 0)
        rank = server.compute_ranking()
        self.assertEqual((rank['aa']['win'], rank['bb']['lose']), (1, 1))

    def test_ladder_codes_and_negative_score(self):
        server.record_match_start('m', ['aa', 'bb'], 'aa')
        server.record_match_result('aa', 0x81, 30)
        server.record_match_result('bb', 0x82, -30)
        rank = server.compute_ranking()
        self.assertEqual((rank['aa']['win'], rank['bb']['lose']), (1, 1))

    def test_old_score_based_records_are_corrected_and_solo_games_ignored(self):
        self.write_matches([
            {"time": "t1", "players": ["aa"], "results": {"aa": {"code": 3, "score": 0, "wl": "win"}}},
            {"time": "t2", "players": ["aa", "-"], "results": {
                "-": {"code": 2, "score": 0, "wl": "draw"}, "aa": {"code": 1, "score": 0, "wl": "draw"}}},
        ])
        rank = server.compute_ranking()
        self.assertEqual({k: (v['win'], v['lose'], v['draw']) for k, v in rank.items()},
                         {'aa': (1, 0, 0), '-': (0, 1, 0)})


class RankPacketTests(TmpMatches):
    def setUp(self):
        super().setUp()
        games = []
        for i in range(20):                      # p00 wins most
            games.append({"time": "2026-11-21 10:00:00", "players": [f"p{i:02d}", "loser"],
                          "results": {f"p{i:02d}": {"code": 1}, "loser": {"code": 2}}})
        games.append({"time": "2026-11-21 11:00:00", "players": ["p00", "loser"],
                      "results": {"p00": {"code": 1}, "loser": {"code": 2}}})
        self.write_matches(games)

    def test_rank_list_layout_matches_client_parser(self):
        c = sess('26.0.0.1', 'seo')
        asyncio.run(c._handle(server.P_RANK_LIST, bytes([0]) + struct.pack('<ii', 1, 18)))
        pk = packets(c.writer.data)
        self.assertEqual([t for t, _ in pk], [0x16FF, 0x15FF, 0x17FF])
        body = pk[1][1]
        self.assertEqual(body[0], 0)                 # sort type
        off, rows = 1, []
        while off < len(body):                       # same walk as Rhakmu.exe 0x44D0B0
            rank, points, win, lose, draw, grade = struct.unpack_from('<iiiiih', body, off)
            off += 22
            extra_end = body.index(b'\0', off); extra = body[off:extra_end]; off = extra_end + 1
            name_end = body.index(b'\0', off); name = body[off:name_end]; off = name_end + 1
            rows.append((rank, name.decode(), points, win, lose))
        self.assertEqual(len(rows), 17)              # one page
        self.assertEqual(rows[0], (1, 'p00', 1020, 2, 0))
        self.assertEqual([r[0] for r in rows], list(range(1, 18)))
        self.assertLessEqual(len(body) + 4, server.MAX_PACKET)

    def test_second_page_and_empty_page(self):
        c = sess('26.0.0.1', 'seo')
        asyncio.run(c._handle(server.P_RANK_LIST, bytes([0]) + struct.pack('<ii', 18, 35)))
        pk = packets(c.writer.data)
        ranks = []
        body = pk[1][1]; off = 1
        while off < len(body):
            ranks.append(struct.unpack_from('<i', body, off)[0]); off += 22
            off = body.index(b'\0', off) + 1; off = body.index(b'\0', off) + 1
        self.assertEqual(ranks, [18, 19, 20, 21])    # 21 players in total
        c.writer.data = b''
        asyncio.run(c._handle(server.P_RANK_LIST, bytes([0]) + struct.pack('<ii', 100, 117)))
        self.assertEqual([t for t, _ in packets(c.writer.data)], [0x16FF, 0x17FF])

    def test_rank_search(self):
        c = sess('26.0.0.1', 'seo')
        asyncio.run(c._handle(server.P_RANK_SEARCH, server.nul('loser')))
        (t, p), = packets(c.writer.data)
        self.assertEqual(t, 0x14FF)
        self.assertEqual(struct.unpack_from('<i', p, 1)[0], 21)
        self.assertEqual(cstrings(p[5:]), ['loser'])

    def test_account_info_type3(self):
        c = sess('26.0.0.1', 'seo')
        asyncio.run(c._handle(server.P_USERNAME, b'\x01' + server.nul('p00')))
        (t, p), = packets(c.writer.data)
        self.assertEqual((t, p[0]), (0x02FF, 3))
        points, win, lose = struct.unpack_from('<iii', p, 1)   # client reads pkt+5, +9, +0xD
        self.assertEqual((points, win, lose), (1020, 2, 0))
        self.assertEqual(cstrings(p[19:])[0], 'p00')            # strings start at pkt+0x17

    def test_http_ranking_still_counts(self):
        self.assertEqual(server.compute_ranking()['p00']['win'], 2)


if __name__ == '__main__':
    unittest.main()
