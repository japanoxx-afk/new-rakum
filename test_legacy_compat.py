import os
import pathlib
import tempfile
import unittest

import legacy_compat
import game_address_patch as gap

NEW = os.environ.get('RHAKMU_NEW_EXE')


class CompatTests(unittest.TestCase):
    def test_peer_codes_differ_only_in_prefix_check(self):
        self.assertEqual(len(legacy_compat.PEER_9016), 154)
        self.assertEqual(len(legacy_compat.PEER_9042), 157)

    @unittest.skipUnless(NEW and os.path.exists(NEW), 'needs a v0.9041 Rhakmu.exe')
    def test_new_launcher_exe_converts(self):
        import peer_address_patch, sync_port_patch, panel_guard_patch
        data = pathlib.Path(NEW).read_bytes()
        out = legacy_compat.to_legacy(data)
        self.assertEqual(len(out), 1069098)
        self.assertTrue(peer_address_patch.state(out) and sync_port_patch.state(out) and panel_guard_patch.state(out))
        self.assertEqual(out[0xeb420:0xeb420 + len(peer_address_patch.CODE)], peer_address_patch.CODE)
        # v0.9042 helper is turned back into the v0.9016 helper
        mod = bytearray(out)
        mod[0xeb420:0xeb520] = legacy_compat.PEER_9042.ljust(256, b'\x90')
        self.assertEqual(legacy_compat.to_legacy(bytes(mod)), out)
        self.assertEqual(legacy_compat.to_legacy(out), out)

    def test_tgnet_pin_removed_unless_session_owns_it(self):
        d = tempfile.mkdtemp()
        data = bytearray(os.urandom(gap.DLL_SIZE))
        data[gap.OFFSET:gap.OFFSET + 80] = gap.code_for('26.1.2.3')
        open(os.path.join(d, gap.DLL_NAME), 'wb').write(data)
        s = tempfile.mkdtemp()
        open(os.path.join(s, 'address.json'), 'w').write('{}')
        self.assertFalse(legacy_compat.restore_tgnet(d, s))
        self.assertTrue(legacy_compat.restore_tgnet(d, tempfile.mkdtemp()))
        self.assertIsNone(gap.state(d))


if __name__ == '__main__':
    unittest.main()
