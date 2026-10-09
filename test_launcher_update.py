import io
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import unittest
import launcher_update as update

class UpdateTests(unittest.TestCase):
    def test_download_cache_buster_preflight_and_new_process(self):
        with tempfile.TemporaryDirectory() as root:
            current=Path(root,'RhakMuLauncher_v0.9020.exe');current.write_bytes(b'OLD')
            def probe(args,**kwargs):
                Path(args[2]).write_text(json.dumps({'version':'0.9024'}))
                self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
                return Mock(returncode=0)
            with patch.object(update.urllib.request,'urlopen',return_value=io.BytesIO(b'MZNEW')) as download, \
                 patch.object(update.subprocess,'run',side_effect=probe), \
                 patch.object(update.subprocess,'Popen') as spawn:
                target=update.install('https://example.test/RhakMuLauncher_v0.9024.exe',5,current,'0.9024')
            self.assertIn('?download=',download.call_args.args[0])
            self.assertEqual(target.read_bytes(),b'MZNEW');self.assertEqual(current.read_bytes(),b'OLD')
            spawn.assert_called_once();self.assertEqual(list(Path(root).glob('*.download')),[])

    def test_bad_size_and_failed_probe_do_not_start_new_launcher(self):
        for size,probe_ok in ((10,True),(5,False)):
            with tempfile.TemporaryDirectory() as root:
                current=Path(root,'old.exe');current.write_bytes(b'OLD')
                with patch.object(update.urllib.request,'urlopen',return_value=io.BytesIO(b'MZNEW')), \
                     patch.object(update.subprocess,'run',return_value=Mock(returncode=1)), \
                     patch.object(update.subprocess,'Popen') as spawn:
                    with self.assertRaises((ValueError,RuntimeError)):
                        update.install('https://example.test/RhakMuLauncher_v0.9024.exe',size,current,'0.9024')
                spawn.assert_not_called();self.assertEqual(current.read_bytes(),b'OLD')

if __name__=='__main__':unittest.main()
