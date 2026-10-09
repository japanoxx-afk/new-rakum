from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import viewport_patch as vp
import viewport_probe
import panel_guard_patch
import resource_amount_patch as amount

SOURCE=Path(__file__).parent/'research/runtime/viewport-1280-ui-v5/Rhakmu.exe.original'

class ViewportReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=vp.transform(SOURCE.read_bytes(),False)

    def test_preserves_supported_command_cadence(self):
        candidate=bytearray(self.source)
        candidate[0xd7b97]=3
        output=vp.transform(candidate)
        self.assertEqual(output[0xd7b97],3)
        self.assertEqual(vp.transform(output,False),candidate)
        candidate[0xd7b97]=2
        with self.assertRaises(ValueError):vp.transform(candidate)

    def test_bpc_deleting_destructor_variant_is_preserved(self):
        for cadence in (3,5):
            candidate=bytearray(self.source)
            candidate[0xd7b97]=cadence
            for offset,original in vp.LEGACY_DELETE_SITES:
                candidate[offset:offset+len(original)]=b'\x90'*len(original)
            output=vp.transform(candidate)
            self.assertEqual(vp.transform(output,False),candidate)
            for offset,original in vp.LEGACY_DELETE_SITES:
                self.assertEqual(output[offset:offset+len(original)],b'\x90'*len(original))
        candidate[vp.LEGACY_DELETE_SITES[0][0]]=0xcc
        with self.assertRaises(ValueError):vp.transform(candidate)

    def test_partial_deleting_destructor_variant_rejected(self):
        candidate=bytearray(self.source)
        at,original=vp.LEGACY_DELETE_SITES[0]
        candidate[at:at+len(original)]=b'\x90'*len(original)
        with self.assertRaises(ValueError):vp.transform(candidate)

    def test_complete_previous_release_migrates(self):
        for recipe in vp.manifest()['legacy_edits']:
            with self.subTest(sites=len(recipe)):
                old=bytearray(self.source)
                for edit in recipe:
                    at=int(edit['va'],16)-0x400000;code=bytes.fromhex(edit['after'])
                    old[at:at+len(code)]=code
                self.assertEqual(vp.transform(old),vp.transform(self.source))
                self.assertEqual(vp.transform(old,False),self.source)
                old[0x1000]^=1
                with self.assertRaises(ValueError):vp.transform(old)

    def test_manifest_matches_builder_and_reversible(self):
        output=vp.transform(self.source)
        self.assertEqual(output,viewport_probe.transform(self.source)[0])
        self.assertEqual(vp.transform(output),output)
        self.assertEqual(vp.transform(output,False),self.source)
        self.assertEqual(output[0xeb420:0xeb520],self.source[0xeb420:0xeb520])
        self.assertEqual(output[0xeb600:0xeb700],self.source[0xeb600:0xeb700])

    def test_preserves_latency_quantity_and_panel_options(self):
        for turns in range(1,5):
            for quantity in (amount.OLD,amount.NEW):
                data=bytearray(self.source);data[0xd7abe]=turns
                data[amount.OFFSET:amount.OFFSET+len(quantity)]=quantity
                for enabled in (True,False):
                    candidate=bytearray(data)
                    for offset,before,after in panel_guard_patch.SITES:
                        candidate[offset:offset+len(before)]=after if enabled else before
                    self.assertEqual(vp.transform(vp.transform(candidate),False),candidate)

    def test_unknown_and_partial_rejected(self):
        for at in (0x1000,0x237f8,0xeb700):
            bad=bytearray(self.source);bad[at]^=1
            with self.assertRaises(ValueError):vp.transform(bad)
        bad=bytearray(vp.transform(self.source))
        bad[0x62d9a:0x62da0]=self.source[0x62d9a:0x62da0]
        with self.assertRaises(ValueError):vp.transform(bad)

    def test_atomic_apply_backup_restore_and_running_block(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);exe=root/'Rhakmu.exe';exe.write_bytes(self.source)
            for name in ('iCARUS.dll','GameCtrl.dll','ddraw.dll'):
                (root/name).write_bytes((SOURCE.parent/name).read_bytes())
            with patch.object(vp,'ensure_closed',side_effect=RuntimeError('running')):
                with self.assertRaises(RuntimeError):vp.apply(exe)
            self.assertEqual(exe.read_bytes(),self.source)
            with patch.object(vp,'ensure_closed'):
                vp.apply(exe);vp.apply(exe);vp.apply(exe,False)
            self.assertEqual(exe.read_bytes(),self.source)
            self.assertTrue(any(p.read_bytes()==self.source for p in root.glob('*.bak_viewport_*')))

if __name__=='__main__':unittest.main()
