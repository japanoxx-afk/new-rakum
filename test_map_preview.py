import struct
import tempfile
import unittest
from pathlib import Path

import map_preview as mp

HERE = Path(__file__).resolve().parent


def _blank_map(w=40, h=40, ts=1, players=((10, 12), (30, 28))):
    cols, rows = (w + 7) // 8, (h + 1) // 2
    s0 = struct.pack('<IIHHB', ts, 0, w, h, 0) + bytes([len(players)]) + bytes(6)
    s1 = bytes(264) + b''.join(bytes(6) + struct.pack('<HH', x, y) + bytes(14) for x, y in players)
    s2 = struct.pack('<HBBB', 10, 0, 0, 0) * (cols * rows)
    gold = bytes([0, 0, 7, 0]) + struct.pack('<H', 18) + bytes([1, 0]) + struct.pack('<III', 5, 6, 5000)
    ramp = bytes([0, 0, 3, 0]) + struct.pack('<H', 9) + bytes([0xcd, 0]) + struct.pack('<III', 8, 8, 0)
    s3 = struct.pack('<II', 0, 2) + gold + ramp
    secs = [s0, s1, s2, s3, bytes(2), bytes(4808), bytes(4), bytes(16)]
    head = bytearray(b'J2M\0' + struct.pack('<II', 8, 0))
    off = 76
    for i, s in enumerate(secs):
        head += struct.pack('<II', i, off)
        off += len(s)
    return bytes(head) + b''.join(secs)


class MapPreviewTests(unittest.TestCase):
    def test_load_render_summary(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'Data' / 'Maps' / 'Download'
            p.mkdir(parents=True)
            (p / '[2]X.rkm').write_bytes(_blank_map())
            self.assertEqual(mp.list_maps(t), [str(Path('Download') / '[2]X.rkm')])
            info = mp.load(p / '[2]X.rkm')
            self.assertEqual((info.tileset, info.width, info.height), (1, 40, 40))
            self.assertEqual(info.players, [(10, 12), (30, 28)])
            self.assertEqual(info.gold, [(5, 6, 5000)])
            self.assertEqual(info.subs, [(9, 8, 8)])
            w, h, rows, s = mp.render_rows(info, HERE, 64)
            self.assertEqual((w, h, len(rows)), (64, 64, 64))
            colour = mp._colors(HERE)[1][10]
            self.assertIn(colour, rows[30])
            text = mp.summary(info)
            self.assertIn('설원', text)
            self.assertIn('2인', text)
            self.assertIn('타일 모드', text)

    def test_colour_table_covers_mod_tiles(self):
        cols = mp._colors(HERE)
        self.assertEqual(sorted(cols), [0, 1, 2, 3])
        self.assertTrue(all(len(v) >= 224 for v in cols.values()))


if __name__ == '__main__':
    unittest.main()
