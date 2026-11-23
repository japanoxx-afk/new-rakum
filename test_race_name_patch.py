"""방 화면 종족 이름 한글 그림 패치 (race_name_patch). 게임 자산 없이 같은 구조로 만든 S16 으로 시험한다."""
import hashlib
import random
import struct
import tempfile
import unittest
from pathlib import Path

import race_name_patch as rn

DIMS = [(51, 15), (51, 15), (37, 12), (37, 12), (69, 15), (69, 15)]
BODY_SIZES = [1188, 1188, 738, 738, 1492, 1492]      # 원본 여섯 장의 (줄 표+RLE) 크기와 같게


def frame(rng, width, height, body_size=None):
    """(머리 14바이트, 줄 표+크기+RLE) — 줄마다 화소 몇 칸. body_size 를 주면 RLE 를 그 크기로 채운다."""
    pixels = [rng.randrange(1, 0x10000) if rng.random() < 0.5 else 0 for _ in range(width * height)]
    rows, blob = rn._encode(width, height, pixels)
    if body_size is not None:
        blob = blob[:body_size - len(rows)].ljust(body_size - len(rows), b"\0")
    return struct.pack("<7h", rng.randrange(-30000, 30000), 1, 2, 3, 4, width, height), rows + struct.pack("<I", len(blob)) + blob


def make_s16(seed=1):
    rng = random.Random(seed)
    frames = [frame(rng, rng.randrange(4, 30), rng.randrange(3, 12)) for _ in range(rn.FIRST)]
    frames += [frame(rng, w, h, size) for (w, h), size in zip(DIMS, BODY_SIZES)]
    frames += [frame(rng, 20, 9) for _ in range(5)]
    groups = [len(frames) - 3, 1, 2]
    head_size = 18 + 2 * len(groups)
    table = bytes(rng.randrange(256) for _ in range(sum(18 + 4 * struct.unpack_from("<h", h, 12)[0] for h, _ in frames)))
    section = b"".join(h + b for h, b in frames)
    first = head_size + len(table)
    data = (struct.pack("<4IH", head_size, first, first + len(section), first + 2 * len(section), len(groups))
            + struct.pack(f"<{len(groups)}H", *groups) + table + section * 3)
    original = tuple((w, h, hashlib.sha256(body).hexdigest()[:32])
                     for (w, h), (_, body) in zip(DIMS, frames[rn.FIRST:rn.FIRST + 6]))
    return data, original


def decode(data, section, index):
    """게임처럼 구역을 차례로 읽어 index 번 장을 (너비, 높이, 화소 목록) 으로."""
    _, head, body = rn.parse(data)[1][section][index]
    width, height = struct.unpack_from("<2h", head, 10)
    rows = struct.unpack_from(f"<{height}I", body, 0)
    blob = body[4 * height + 4:]
    out = []
    for start in rows:
        line, pos, x = [0] * width, start * 2, 0
        while True:
            skip, run = struct.unpack_from("<HH", blob, pos)
            pos += 4
            if not skip and not run:
                break
            x += skip
            line[x:x + run] = struct.unpack_from(f"<{run}H", blob, pos)
            pos += 2 * run
            x += run
        assert len(line) == width
        out += line
    return width, height, out


class RaceNamePatchTests(unittest.TestCase):
    def setUp(self):
        self.data, original = make_s16()
        self.saved = rn.ORIGINAL
        rn.ORIGINAL = original
        self.addCleanup(lambda: setattr(rn, "ORIGINAL", self.saved))

    def test_sprites_fit_the_original_space(self):
        """한글 그림 여섯 장은 원본 여섯 장 자리(구역마다 6836바이트)에 들어가야 한다."""
        for frames in rn.new_frames(sum(BODY_SIZES)):
            self.assertEqual(sum(len(body) for _, _, body in frames), sum(BODY_SIZES))
        self.assertEqual(len(rn.SPRITES), 6)
        for normal, picked in zip(rn.SPRITES[::2], rn.SPRITES[1::2]):
            self.assertEqual(normal[:2], picked[:2])                       # 보통·고른 것은 같은 크기

    def test_transform_changes_only_the_six_frames(self):
        self.assertEqual(rn.state(self.data), "original")
        new = rn.transform(self.data)
        self.assertEqual(rn.state(new), "patched")
        self.assertEqual(len(new), len(self.data))
        before, after = rn.parse(self.data)[1], rn.parse(new)[1]
        changed = [i for i in range(len(new)) if new[i] != self.data[i]]
        for s in range(3):
            self.assertEqual(before[s][:rn.FIRST], after[s][:rn.FIRST])
            self.assertEqual(before[s][rn.FIRST + 6:], after[s][rn.FIRST + 6:])
        spans = [(before[s][rn.FIRST][0], before[s][rn.FIRST + 6][0]) for s in range(3)]
        self.assertTrue(all(any(a <= i < b for a, b in spans) for i in changed))
        with self.assertRaises(rn.FormatError):
            rn.transform(new)

    def test_new_frames_decode_to_the_sprites_in_every_pixel_format(self):
        import base64, zlib
        new = rn.transform(self.data)
        for k, (width, height, packed) in enumerate(rn.SPRITES):
            pixels = list(struct.unpack(f"<{width * height}H", zlib.decompress(base64.b64decode(packed))))
            self.assertEqual(decode(new, 0, rn.FIRST + k), (width, height, pixels))
            self.assertEqual(decode(new, 2, rn.FIRST + k), (width, height, pixels))
            self.assertEqual(decode(new, 1, rn.FIRST + k), (width, height, [rn._to555(p) for p in pixels]))
        self.assertEqual(rn._to555(0xFFDF), 0x7FFF)
        self.assertEqual(rn._to555(0x7ACB), 0x3D6B)                       # 원본 두 구역에서 읽은 같은 화소

    def test_unknown_images_are_left_alone(self):
        other, _ = make_s16(seed=2)
        self.assertEqual(rn.state(other), "unknown")
        self.assertEqual(rn.state(b"\0" * 64), "unknown")
        with self.assertRaises(rn.FormatError):
            rn.transform(other)

    def folder(self, data, pad=b"JPG!" * 50):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        fdb = b"\0" * 5 + struct.pack("<I", len(pad)) + pad
        offset = len(fdb)
        fdb += struct.pack("<I", len(data)) + data + struct.pack("<I", 8) + b"TAILFILE"
        (folder / "Data002.FDB").write_bytes(fdb)
        (folder / "Data002.IDX").write_bytes(
            struct.pack("<II", 0, 3) + b"\xff" * 8 + struct.pack("<I", 5) + b"DATA\\MENUDATA\\B0.JPG\0"
            + b"\xff" * 4 + struct.pack("<I", offset) + b"DATA\\MENUDATA\\MENUCOMMON.S16\0"
            + b"\xff" * 4 + struct.pack("<I", offset + 4 + len(data)) + b"DATA\\MENUDATA\\TRIGGERNET.S16\0")
        return folder, fdb, offset

    def test_apply_patches_in_place_keeps_backup_and_repairs(self):
        folder, fdb, offset = self.folder(self.data)
        self.assertTrue(rn.apply(folder))
        after = (folder / "Data002.FDB").read_bytes()
        self.assertEqual(len(after), len(fdb))
        self.assertEqual(after[:offset + 4], fdb[:offset + 4])
        self.assertEqual(after[offset + 4 + len(self.data):], fdb[offset + 4 + len(self.data):])
        self.assertEqual(after[offset + 4:offset + 4 + len(self.data)], rn.transform(self.data))
        self.assertEqual((folder / rn.BACKUP).read_bytes(), self.data)
        self.assertEqual(rn.apply(folder), "")                              # 두 번째는 할 일 없음
        self.assertEqual((folder / "Data002.FDB").read_bytes(), after)
        # 쓰다 끊긴 것처럼 망가뜨려도 원본 사본에서 다시 만든다
        broken = bytearray(after)
        at = offset + 4 + rn.parse(self.data)[1][0][rn.FIRST + 2][0] + 30
        broken[at:at + 40] = b"\x55" * 40
        (folder / "Data002.FDB").write_bytes(broken)
        self.assertTrue(rn.apply(folder))
        self.assertEqual((folder / "Data002.FDB").read_bytes(), after)
        self.assertTrue(rn.restore(folder))
        self.assertEqual((folder / "Data002.FDB").read_bytes(), fdb)

    def test_apply_leaves_unknown_game_data_alone(self):
        other, _ = make_s16(seed=2)
        folder, fdb, _ = self.folder(other)
        self.assertEqual(rn.apply(folder), "")
        self.assertEqual((folder / "Data002.FDB").read_bytes(), fdb)
        self.assertFalse((folder / rn.BACKUP).exists())
        self.assertFalse(rn.restore(folder))


if __name__ == "__main__":
    unittest.main()
