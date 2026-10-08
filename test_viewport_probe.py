import hashlib
from pathlib import Path
import unittest
import viewport_probe


class ViewportProbeTests(unittest.TestCase):
    def test_dynamic_clip_preserves_menu_and_game_surfaces(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_EBP
        import struct
        code = viewport_probe.HIGHMODE_CODE
        for width, height in ((1024, 768), (1280, 720)):
            vm = Uc(UC_ARCH_X86, UC_MODE_32)
            vm.mem_map(0x400000, 0x200000)
            vm.mem_map(0x106a000, 0x1000)
            vm.mem_write(0x4dc3fa, code)
            vm.mem_write(0x106a5e0, struct.pack('<hh', width, height))
            vm.reg_write(UC_X86_REG_EBP, 0x580100)
            vm.mem_write(0x5800fc, struct.pack('<I', 0x106a5e0))
            vm.emu_start(0x4dc3fa, 0x4dc3fa + len(code))
            self.assertEqual(struct.unpack('<iiii', vm.mem_read(0x106a604, 16)), (0, 0, width, height))
            self.assertEqual(struct.unpack('<iiii', vm.mem_read(0x106a690, 16)),
                             ((width-800)//2, height-185, (width-800)//2+799, height-1))
            self.assertEqual(struct.unpack('<hh', vm.mem_read(0x501ea0, 4)), ((width-800)//2, height-600))

    def test_unknown_binary_rejected(self):
        with self.assertRaises(ValueError):
            viewport_probe.transform(b'MZ' + bytes(1100000))

    def test_unsupported_resolution_rejected(self):
        with self.assertRaises(ValueError):
            viewport_probe.transform(b'', 1920, 1080)

    def test_known_binary_changes_only_manifest_regions(self):
        path = Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe')
        if not path.exists():
            self.skipTest('Local reference executable unavailable')
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != viewport_probe.SOURCE_HASHES['Rhakmu.exe']:
            self.skipTest('Local reference executable changed')
        output, edits = viewport_probe.transform(source)
        self.assertEqual(len(output), len(source))
        restored = bytearray(output)
        for edit in edits:
            start = int(edit['va'], 16) - 0x400000
            before = bytes.fromhex(edit['before'])
            after = bytes.fromhex(edit['after'])
            self.assertEqual(output[start:start+len(after)], after)
            restored[start:start+len(before)] = before
        self.assertEqual(bytes(restored), source)
        self.assertEqual(output[0x49d80:0x4a500], source[0x49d80:0x4a500])
        self.assertEqual(output[0xeb420:0xeb700], source[0xeb420:0xeb700])


if __name__ == '__main__':
    unittest.main()
