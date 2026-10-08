import os
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_ESP
import peer_address_patch as patch
from build_peer_address_code import assemble

GAME = Path(os.environ.get('RHAKMU_GAME_EXE', r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe'))

def crc(data):
    value = 0
    for byte in data:
        for _ in range(8):
            bit = (value ^ byte) & 1
            value >>= 1
            if bit:
                value ^= 0x8408
            byte >>= 1
    return struct.pack('<H', value)

class PeerAddressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = patch.transform(GAME.read_bytes(), False)

    def machine(self, enabled, source='26.240.153.112', sender=1, recipient=0, session=0, active=0x20, size=10, corrupt=False):
        machine = Uc(UC_ARCH_X86, UC_MODE_32)
        machine.mem_map(0x400000, 0xd00000)
        machine.mem_write(0x400000, patch.transform(self.original, enabled))
        machine.mem_map(0x1800000, 0x10000)
        machine.mem_map(0x2000000, 0x10000)
        machine.reg_write(UC_X86_REG_EBP, 0x2008000)
        machine.reg_write(UC_X86_REG_ESP, 0x2007000)
        machine.mem_write(0x2007ffc, struct.pack('<I', 0x1800000))
        machine.mem_write(0x1800018, struct.pack('<I', 0x1806000))
        payload = struct.pack('<HHBBI', 0x8813, size, sender, recipient, session)
        payload += crc(payload)
        if corrupt:
            payload = payload[:-1] + bytes([payload[-1] ^ 1])
        machine.mem_write(0x1806100, payload)
        machine.mem_write(0x1806000, socket.inet_aton(source) + struct.pack('!H',11223) + b'\0\0' + struct.pack('<II',len(payload),0x1806100))
        machine.mem_write(0xb412cc, b'\x00')
        machine.mem_write(0xb412c4, bytes(4))
        machine.mem_write(0x7f790e+0x11e0, bytes([active]))
        machine.mem_write(0x7f7934+0x11e0, socket.inet_aton('192.168.0.8'))
        machine.mem_write(0x1800050+0x284, b'\x02\x00'+struct.pack('!H',11223)+socket.inet_aton('192.168.0.8'))
        return machine

    def run_to_decision(self, machine, start, stops):
        hit = []
        def stop(uc, address, size, user):
            if address in stops:
                hit.append(address)
                uc.emu_stop()
        hook = machine.hook_add(UC_HOOK_CODE, stop)
        machine.emu_start(start, 0x44a2ef, count=20000)
        machine.hook_del(hook)
        self.assertTrue(hit, 'No receive decision reached')
        return hit[0]

    def test_replay_original_dead_end_then_patched_recovery(self):
        for enabled in (False, True):
            machine = self.machine(enabled)
            # Execute the ORIGINAL checksum implementation and receive dispatcher.
            result = self.run_to_decision(machine, 0x449db2, {0x44a2e7, 0x44a0ac, 0x44a2ed})
            self.assertEqual(result, 0x44a2e7)
            expected = '26.240.153.112' if enabled else '192.168.0.8'
            self.assertEqual(bytes(machine.mem_read(0x7f7934+0x11e0,4)), socket.inet_aton(expected))
            self.assertEqual(bytes(machine.mem_read(0x1800054+0x284,4)), socket.inet_aton(expected))
            # Next packet from this source: original rejects the source; patched
            # game dispatches it to the original known-player handler.
            result = self.run_to_decision(machine, 0x449e0d, {0x449ce0, 0x449f34})
            self.assertEqual(result, 0x449ce0 if enabled else 0x449f34)

    def test_invalid_announcements_do_not_change_address(self):
        cases = [dict(source='25.16.57.186'),dict(source='192.168.0.8'),dict(sender=8),dict(sender=255),dict(sender=0),dict(recipient=2),dict(session=1),dict(active=0),dict(size=9),dict(corrupt=True)]
        for case in cases:
            with self.subTest(case=case):
                machine = self.machine(True, **case)
                self.run_to_decision(machine, 0x449db2, {0x44a2e7,0x44a0ac,0x44a2ed,0x449ce0})
                self.assertEqual(bytes(machine.mem_read(0x7f7934+0x11e0,4)), socket.inet_aton('192.168.0.8'))

    def test_assembler_and_restore(self):
        self.assertEqual(patch.CODE, assemble())
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, 'Rhakmu.exe')
            path.write_bytes(self.original)
            patch.apply(path)
            self.assertTrue(patch.state(path.read_bytes()))
            modified = bytearray(path.read_bytes())
            modified[0x400] ^= 1
            path.write_bytes(modified)
            patch.apply(path, False)
            expected = bytearray(self.original)
            expected[0x400] ^= 1
            self.assertEqual(path.read_bytes(), expected)

    def test_conflicting_code_rejected(self):
        data = bytearray(self.original)
        data[0xeb420] = 1
        with self.assertRaises(ValueError):
            patch.transform(data, True)

if __name__ == '__main__':
    unittest.main()
