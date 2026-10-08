"""Versioned installation with frozen-executable preflight and a stable shortcut."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
import urllib.parse

def install(url, size, current, version):
    name = Path(urllib.parse.urlparse(url).path).name
    if not re.fullmatch(r'RhakMuLauncher_v[0-9.]+\.exe', name):
        raise ValueError('Invalid update filename')
    current = Path(current).resolve()
    target = current.parent / name
    if target == current or size <= 0:
        raise ValueError('Invalid update target or size')
    fd, tmp = tempfile.mkstemp(prefix='rhakmu_update_', suffix='.download', dir=current.parent)
    os.close(fd)
    probe = Path(tmp + '.check.json')
    try:
        with urllib.request.urlopen(url, timeout=30) as response, open(tmp, 'wb') as out:
            count = 0
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > size:
                    raise ValueError('Download exceeds expected size')
                out.write(block)
        if count != size or Path(tmp).read_bytes()[:2] != b'MZ':
            raise ValueError('Download size or executable header mismatch')
        # Check the runtime before committing navigation to the new executable.
        if target.exists() and hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(Path(tmp).read_bytes()).digest():
            pass
        else:
            os.replace(tmp, target)
        env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
        result = subprocess.run([str(target), '--update-probe', str(probe)], env=env,
                                timeout=40, creationflags=0x08000000)
        if result.returncode != 0 or not probe.exists():
            raise RuntimeError('New launcher runtime check failed; current launcher preserved')
        data = json.loads(probe.read_text(encoding='utf-8'))
        if data.get('version') != version:
            raise RuntimeError('Downloaded launcher version mismatch')
        subprocess.Popen([str(target)], cwd=current.parent, env=env)
        return target
    finally:
        Path(tmp).unlink(missing_ok=True)
        probe.unlink(missing_ok=True)

def make_shortcut(executable):
    import base64
    exe = str(Path(executable).resolve())
    quote = lambda s: "'" + s.replace("'", "''") + "'"
    link = str(Path(exe).parent / 'RhakMu Launcher.lnk')
    script = ("$ErrorActionPreference='Stop'; $w=New-Object -ComObject WScript.Shell; "
              "$s=$w.CreateShortcut(" + quote(link) + "); $s.TargetPath=" + quote(exe) +
              "; $s.WorkingDirectory=" + quote(str(Path(exe).parent)) + "; $s.Save()")
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', encoded],
                   check=True, timeout=15, creationflags=0x08000000)
