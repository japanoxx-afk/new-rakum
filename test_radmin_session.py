import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

class SessionTests(unittest.TestCase):
    def test_stale_session_recovers_before_next_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            (folder/'adapters.json').write_text('[]',encoding='utf-8')
            script="""
            function Get-Process { param($Name,$ErrorAction) }
            function Get-NetAdapter { }
            & 'SCRIPT' -GameDir 'STATE' -StateDir 'STATE'
            """.replace('SCRIPT',str(Path('radmin_session.ps1').resolve()).replace("'","''")).replace('STATE',root.replace("'","''"))
            encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
            result=subprocess.run(['powershell','-NoProfile','-EncodedCommand',encoded],capture_output=True)
            self.assertNotEqual(result.returncode,0) # Deliberately no test Radmin adapter.
            status=(folder/'status.txt').read_text(encoding='utf-8-sig')
            self.assertFalse((folder/'adapters.json').exists(),status)
            self.assertIn('Connected Radmin adapter not found',status)

if __name__=='__main__':unittest.main()
