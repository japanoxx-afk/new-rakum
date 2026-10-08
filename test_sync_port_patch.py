import pathlib
import tempfile
import unittest
import sync_port_patch as patch

class SyncPortTests(unittest.TestCase):
    def test_round_trip_and_preserve_other_changes(self):
        data = bytearray(1069098)
        data[:2] = b'MZ'
        data[patch.OFFSET:patch.OFFSET+len(patch.ORIGINAL)] = patch.ORIGINAL
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/'Rhakmu.exe'
            p.write_bytes(data)
            patch.apply(p)
            result = p.read_bytes()
            self.assertTrue(patch.state(result))
            self.assertEqual([i for i,(a,b) in enumerate(zip(data,result)) if a!=b], [patch.OFFSET+7,patch.OFFSET+8])
            patch.apply(p)
            changed = bytearray(p.read_bytes()); changed[100] = 77; p.write_bytes(changed)
            patch.apply(p, False)
            data[100] = 77
            self.assertEqual(p.read_bytes(), data)

    def test_reject_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/'Rhakmu.exe'; p.write_bytes(b'MZbad')
            with self.assertRaises(ValueError): patch.apply(p)
            self.assertEqual(p.read_bytes(), b'MZbad')

if __name__ == '__main__': unittest.main()
