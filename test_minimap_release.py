import unittest
import minimap_patch as release
import minimap_preview_v5 as trial
import viewport_patch
from test_minimap_preview_v2 import SOURCE

class ReleaseTests(unittest.TestCase):
    def test_matches_confirmed_trial_preserves_independent_settings(self):
        for high in (False,True):
            for turns in (1,4):
                base=bytearray(viewport_patch.transform(SOURCE.read_bytes(),high))
                base[0xd7abe]=turns
                base=bytes(base)
                patched=release.transform(base)
                self.assertEqual(patched,trial.build(base))
                self.assertEqual(release.transform(patched),patched)
                self.assertEqual(release.transform(patched,False),base)
                # Resolution change is performed on the verified underlying file.
                switched=release.transform(viewport_patch.transform(release.underlying(patched),not high))
                self.assertEqual(release.transform(switched,False),viewport_patch.transform(base,not high))
    def test_unknown_or_partial_patch_is_rejected(self):
        patched=bytearray(release.transform(SOURCE.read_bytes()))
        for at in (0x1000,0xcaf40,0x106000+0x50):
            bad=bytearray(patched);bad[at]^=1
            with self.assertRaises(ValueError):release.transform(bad)

if __name__=='__main__':unittest.main()
