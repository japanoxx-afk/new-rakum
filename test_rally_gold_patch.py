"""집결지 금광 인식 패치: 원본 바이트/동굴 비어 있음, 적용·해제 왕복, 다른 패치와 겹침 없음, (가능하면) 실제 함수 에뮬레이션."""
import json
import struct
import unittest
from pathlib import Path

import rally_gold_patch as r

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'


class RallyGoldPatchTests(unittest.TestCase):
    def setUp(self):
        if not EXE.is_file():
            self.skipTest('game_backup/Rhakmu.exe 없음')
        self.data = EXE.read_bytes()

    def test_roundtrip(self):
        self.assertFalse(r.state(self.data))
        p = r.apply(self.data)
        self.assertTrue(r.state(p))
        self.assertEqual(r.apply(p), p)
        self.assertEqual(r.strip(p), self.data)
        self.assertEqual(r.apply(p, False), self.data)
        bad = bytearray(p); bad[r.CAVE + 3] ^= 1
        with self.assertRaises(ValueError):
            r.state(bytes(bad))

    def test_no_overlap_with_other_patches(self):
        mine = [(r.SITE, len(r.SITE_PATCHED)), (r.CAVE, len(r.CODE))]
        used = [(int(e['va'], 16) - 0x400000, len(bytes.fromhex(e['after'])))
                for e in json.loads((HERE / 'viewport_release.json').read_text())['edits']]
        for v in json.loads((HERE / 'minimap_release.json').read_text())['variants']:
            used += [(e['offset'], len(bytes.fromhex(e['after']))) for e in v['edits']]
        used += [(0xeb420, 256), (0xeb600, 256)]
        for a, n in mine:
            for b, m in used:
                self.assertFalse(a < b + m and b < a + n, (hex(a), hex(b)))

    def test_emulated_decision(self):
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
            from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_EAX
        except ImportError as e:
            self.skipTest(str(e))
        img = pefile.PE(data=r.apply(self.data)).get_memory_mapped_image()

        def call(click):
            mu = Uc(UC_ARCH_X86, UC_MODE_32)
            mu.mem_map(0x400000, (len(img) + 0xfff) & ~0xfff); mu.mem_write(0x400000, img)
            mu.mem_map(0x2000000, 0x100000)
            for x in (50, 51, 52):
                mu.mem_write(0xb4198a + 40 * 0x208 + x, b'\x53')
            mu.mem_write(0xb4198a + 30 * 0x208 + 30, b'\x41')   # 다른 장식물
            esp, cebp, ret = 0x2080000, 0x2090000, 0x2000010
            mu.mem_write(ret, b'\xf4'); mu.mem_write(cebp + 0x14, struct.pack('<hh', *click))
            for v in (struct.unpack('<I', struct.pack('<hh', *click))[0], 0, 0, 0x20a0000, ret):
                esp -= 4; mu.mem_write(esp, struct.pack('<I', v))
            mu.reg_write(UC_X86_REG_ESP, esp); mu.reg_write(UC_X86_REG_EBP, cebp)
            mu.emu_start(0x473410, ret + 1, count=20000)
            nx, ny = struct.unpack('<hh', mu.mem_read(cebp + 0x14, 4))
            return mu.reg_read(UC_X86_REG_EAX) & 0xffff, (nx // 32, ny // 32)

        self.assertEqual(call((51 * 32 + 5, 40 * 32 + 5)), (0x2006, (51, 40)))
        self.assertEqual(call((51 * 32 + 5, 39 * 32 + 5)), (0x2006, (50, 40)))
        self.assertEqual(call((48 * 32 + 5, 40 * 32 + 5)), (0x2006, (50, 40)))
        self.assertEqual(call((47 * 32 + 5, 40 * 32 + 5))[0], 0x2003)
        self.assertEqual(call((31 * 32 + 5, 31 * 32 + 5))[0], 0x2003)


if __name__ == '__main__':
    unittest.main()
