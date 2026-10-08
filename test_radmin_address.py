"""Execute the actual generated x86 in Unicorn, not a Python approximation."""
import base64
import pathlib
import struct
import subprocess
import unittest

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP

ROOT = pathlib.Path(__file__).resolve().parent

def generate(ip):
    script = f". './radmin_address.ps1'; [Convert]::ToBase64String((New-RadminAddressCode '{ip}'))"
    return base64.b64decode(subprocess.check_output(['powershell', '-NoProfile', '-Command', script], cwd=ROOT).strip())

class AddressCodeTests(unittest.TestCase):
    def run_code(self, ip, capacity=128, null=False):
        code = generate(ip)
        self.assertEqual(len(code), 80)
        machine = Uc(UC_ARCH_X86, UC_MODE_32)
        for address in (0x1000, 0x2000, 0x3000):
            machine.mem_map(address, 0x1000)
        machine.mem_write(0x1000, code)
        machine.mem_write(0x3000, b'X' * 128)
        machine.mem_write(0x2800, struct.pack('<III', 0x1100, 0 if null else 0x3000, capacity))
        machine.reg_write(UC_X86_REG_ESP, 0x2800)
        regs = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)
        for reg in regs:
            machine.reg_write(reg, 0x12345678)
        machine.emu_start(0x1000, 0x1100, count=100)
        self.assertEqual(machine.reg_read(UC_X86_REG_ESP), 0x2804)
        for reg in regs:
            self.assertEqual(machine.reg_read(reg), 0x12345678)
        return machine.reg_read(UC_X86_REG_EAX), bytes(machine.mem_read(0x3000, 128))

    def test_addresses_and_buffer_boundary(self):
        for ip in ('26.1.2.3', '26.157.67.215', '26.240.153.112', '26.255.255.255'):
            result, data = self.run_code(ip, 16)
            self.assertEqual(result, 1)
            self.assertEqual(data[:16], ip.encode().ljust(16, b'\0'))
            self.assertEqual(data[16:], b'X' * 112)

    def test_small_buffer_and_null(self):
        for capacity, null in ((0, False), (15, False), (128, True)):
            result, data = self.run_code('26.1.2.3', capacity, null)
            self.assertEqual(result, 0)
            self.assertEqual(data, b'X' * 128)

if __name__ == '__main__':
    unittest.main()
