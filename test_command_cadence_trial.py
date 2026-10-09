"""Execute actual native scheduler branch with mocked send/render/receive.

Proves cadence and buffer gating, NOT multiplayer determinism or visible delay.
"""
import struct
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EBP
import command_cadence_trial as trial

SOURCE = Path(__file__).parent / 'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'


@unittest.skipUnless(SOURCE.exists(), 'Known reference game not available')
class SchedulerTests(unittest.TestCase):
    def run_branch(self, data, queued):
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x400000, 0xD00000)
        uc.mem_write(0x400000, data)
        manager, stack = 0xC00000, 0xC10000
        def put(at, value):
            uc.mem_write(at, struct.pack('<I', value))
        put(0xB411A4, manager)
        uc.mem_write(0xB412CC, b'\0')
        uc.mem_write(manager + 0x48, struct.pack('<H', 4))
        uc.mem_write(manager + 0x62, struct.pack('<H', queued))
        put(stack - 0x14, 1)  # Suppress rendering, no change to simulation.
        calls = []
        def hook(emu, pc, size, _):
            if pc in (0x447AF0, 0x44A840, 0x449AB0):
                calls.append(pc)
                esp = emu.reg_read(UC_X86_REG_ESP)
                ret = struct.unpack('<I', emu.mem_read(esp, 4))[0]
                emu.reg_write(UC_X86_REG_ESP, esp + 4)
                emu.reg_write(UC_X86_REG_EIP, ret)
        uc.hook_add(UC_HOOK_CODE, hook)
        sealed = []
        for frame in range(30):
            put(0xB412B4, frame)
            uc.reg_write(UC_X86_REG_EBP, stack)
            uc.reg_write(UC_X86_REG_ESP, stack - 0x100)
            before = len(calls)
            uc.emu_start(0x4D7B8F, 0x4D7C2D, count=1000)
            if len(calls) != before:
                sealed.append(frame)
        return sealed, calls

    def test_native_cadence_and_four_turn_gate(self):
        source = SOURCE.read_bytes()
        patched = trial.transform(source)
        self.assertEqual(self.run_branch(source, 4)[0], list(range(0, 30, 5)))
        self.assertEqual(self.run_branch(patched, 4)[0], list(range(0, 30, 3)))
        for data in (source, patched):
            _, calls = self.run_branch(data, 3)
            self.assertNotIn(0x44A840, calls)
            _, calls = self.run_branch(data, 4)
            self.assertEqual(calls.count(0x44A840), calls.count(0x447AF0))
            self.assertEqual(calls.count(0x449AB0), calls.count(0x447AF0))

    def test_only_cadence_byte_changes(self):
        source = SOURCE.read_bytes()
        changed = trial.transform(source)
        self.assertEqual([i for i, (a, b) in enumerate(zip(source, changed)) if a != b], [trial.OFFSET + 1])
        self.assertEqual(changed[trial.BUFFER_OFFSET], 4)
        self.assertEqual(trial.transform(changed), changed)
        self.assertEqual(trial.transform(changed, False), source)
        self.assertEqual(trial.transform(source, False), source)

    def test_unknown_and_nonfour_turn_rejected(self):
        source = bytearray(SOURCE.read_bytes())
        source[trial.BUFFER_OFFSET] = 1
        with self.assertRaises(ValueError):
            trial.transform(bytes(source))
        source[trial.BUFFER_OFFSET] = 4
        source[0x1000] ^= 1
        with self.assertRaises(ValueError):
            trial.transform(bytes(source))


if __name__ == '__main__':
    unittest.main()
