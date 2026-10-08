"""Guarded RhakMu 1.000d sync fallback destination-port patch.

VA 0x44A13D pushes 6112 before htons. The sockaddr is passed to
0x448EB0 for the 0x8813 sync packet. UDP socket creation uses 11223.
Only this immediate is changed; restore preserves all other patches.
"""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

OFFSET = 0x4A137
ORIGINAL = bytes.fromhex('66c745d0020068e0170000e827330900668945d2')
PATCHED = bytes.fromhex('66c745d0020068d72b0000e827330900668945d2')

def state(data):
    if len(data) != 1069098 or data[:2] != b'MZ':
        raise ValueError('지원하지 않는 게임 파일입니다. Rhakmu.exe 1.000d가 필요합니다.')
    site = data[OFFSET:OFFSET + len(ORIGINAL)]
    if site == ORIGINAL:
        return False
    if site == PATCHED:
        return True
    raise ValueError('패치 위치의 코드가 예상과 다릅니다. 파일을 변경하지 않았습니다.')

def apply(path, enabled=True):
    path = Path(path)
    data = path.read_bytes()
    if state(data) == enabled:
        return '이미 적용된 상태입니다.' if enabled else '이미 원본 포트 상태입니다.'
    digest = hashlib.sha256(data).hexdigest()
    backup = path.with_name(path.name + '.bak_syncport_' + digest[:16])
    if backup.exists():
        if backup.read_bytes() != data:
            raise ValueError('백업 파일 충돌: 기존 백업을 확인하세요.')
    else:
        with backup.open('xb') as f:
            f.write(data)
    result = data[:OFFSET] + (PATCHED if enabled else ORIGINAL) + data[OFFSET + len(ORIGINAL):]
    fd, temp = tempfile.mkstemp(prefix='syncport_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(result)
            f.flush()
            os.fsync(f.fileno())
        shutil.copymode(path, temp)
        if path.read_bytes() != data:
            raise ValueError('게임 파일이 다른 작업에 의해 변경됐습니다. 다시 시도하세요.')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return ('동기화 포트를 11223으로 변경했습니다.' if enabled else '동기화 포트를 원래 6112로 복구했습니다.') + '\n백업: ' + str(backup)
