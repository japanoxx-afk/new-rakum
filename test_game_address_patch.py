"""TG_Net self-address pin: run the generated x86 in Unicorn and check file handling."""
import os
import struct
import tempfile
import unittest
from unittest import mock

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EBX,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)

import game_address_patch as gap


def run(code, capacity=128, null=False):
    m = Uc(UC_ARCH_X86, UC_MODE_32)
    for a in (0x1000, 0x2000, 0x3000):
        m.mem_map(a, 0x1000)
    m.mem_write(0x1000, code)
    m.mem_write(0x3000, b'X' * 128)
    m.mem_write(0x2800, struct.pack('<III', 0x1100, 0 if null else 0x3000, capacity))
    m.reg_write(UC_X86_REG_ESP, 0x2800)
    regs = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)
    for r in regs:
        m.reg_write(r, 0x12345678)
    m.emu_start(0x1000, 0x1100, count=100)
    assert m.reg_read(UC_X86_REG_ESP) == 0x2804
    for r in regs:
        assert m.reg_read(r) == 0x12345678
    return m.reg_read(UC_X86_REG_EAX), bytes(m.mem_read(0x3000, 128))


class CodeTests(unittest.TestCase):
    def test_any_ipv4(self):
        for ip in ('26.1.2.3', '25.10.200.7', '192.168.0.10', '255.255.255.255'):
            code = gap.code_for(ip)
            self.assertEqual(len(code), 80)
            rc, data = run(code, 16)
            self.assertEqual(rc, 1)
            self.assertEqual(data[:16], ip.encode().ljust(16, b'\0'))
            self.assertEqual(data[16:], b'X' * 112)
            self.assertEqual(gap.pinned_ip(code), ip)

    def test_rejects_small_or_null_buffer(self):
        for cap, null in ((0, False), (15, False), (128, True)):
            rc, data = run(gap.code_for('26.1.2.3'), cap, null)
            self.assertEqual((rc, data), (0, b'X' * 128))

    def test_unknown_bytes_rejected(self):
        self.assertIsNone(gap.pinned_ip(gap.ORIGINAL))
        with self.assertRaises(ValueError):
            gap.pinned_ip(b'\xcc' * 80)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        data = bytearray(os.urandom(gap.DLL_SIZE))
        data[gap.OFFSET:gap.OFFSET + 80] = gap.ORIGINAL
        self.orig = bytes(data)
        open(os.path.join(self.dir, gap.DLL_NAME), 'wb').write(data)

    def read(self):
        return open(os.path.join(self.dir, gap.DLL_NAME), 'rb').read()

    def test_pin_switch_restore(self):
        self.assertTrue(gap.apply(self.dir, '26.5.6.7'))
        self.assertEqual(gap.state(self.dir), '26.5.6.7')
        self.assertFalse(gap.apply(self.dir, '26.5.6.7'))
        gap.apply(self.dir, '25.1.1.1')
        d = self.read()
        self.assertEqual(d[:gap.OFFSET] + d[gap.OFFSET + 80:], self.orig[:gap.OFFSET] + self.orig[gap.OFFSET + 80:])
        gap.apply(self.dir, None)
        self.assertEqual(self.read(), self.orig)
        self.assertEqual(open(os.path.join(self.dir, gap.DLL_NAME + '.orig'), 'rb').read(), self.orig)

    def test_wrong_size_untouched(self):
        open(os.path.join(self.dir, gap.DLL_NAME), 'ab').write(b'x')
        with self.assertRaises(ValueError):
            gap.apply(self.dir, '26.1.1.1')


class RouteTests(unittest.TestCase):
    def test_loopback_prefers_single_radmin(self):
        with mock.patch.object(gap, '_local_ipv4s', return_value=['192.168.0.5', '26.9.9.9', '25.1.2.3']):
            self.assertEqual(gap.local_ip_toward('127.0.0.1', prefer_radmin=True), '26.9.9.9')
            self.assertIsNone(gap.local_ip_toward('127.0.0.1', prefer_radmin=False))
            self.assertEqual(gap.local_ip_toward('26.9.9.9'), '26.9.9.9')

    def test_route_fallback_by_prefix(self):
        with mock.patch.object(gap, '_local_ipv4s', return_value=['192.168.0.5', '26.9.9.9', '25.1.2.3']), \
             mock.patch.object(gap.socket, 'socket', side_effect=OSError):
            self.assertEqual(gap.local_ip_toward('26.200.1.1'), '26.9.9.9')
            self.assertEqual(gap.local_ip_toward('25.7.7.7'), '25.1.2.3')
            self.assertIsNone(gap.local_ip_toward('bad'))


class ChooseTests(unittest.TestCase):
    LOG = (b"2026-11-19 00:22:46 [INFO] Login OK: 26.157.67.215:10792 account='seo'\r\n"
           b"2026-11-19 00:22:53 [INFO] Login OK: 25.14.45.110:2623 account='nyai'\r\n")

    def test_host_follows_remote_players_network(self):
        local = ['192.168.0.5', '26.157.67.215', '25.1.2.3']
        path = os.path.join(tempfile.mkdtemp(), 'server-console.log')
        open(path, 'wb').write(self.LOG)
        with mock.patch.object(gap, '_local_ipv4s', return_value=local), \
             mock.patch.object(gap.socket, 'socket', side_effect=OSError):
            self.assertEqual(gap.recent_remote_player(path), '25.14.45.110')
            self.assertEqual(gap.choose('26.157.67.215', True, path), '25.1.2.3')
            self.assertEqual(gap.choose('26.157.67.215', True, path + 'x'), '26.157.67.215')
            # Joining someone else's server: route toward that server
            self.assertEqual(gap.choose('26.9.9.9', True, path), '26.157.67.215')


if __name__ == '__main__':
    unittest.main()
