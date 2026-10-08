"""Defensive guard for the 1.000d ProcessMenu null-call crash; not heap repair."""
from pathlib import Path
import hashlib
import os
import struct
import tempfile

CODE = bytes.fromhex('8b108955e085d274626a0452ff15a0c24e0085c075558b4de08b1185d2744c8955a06a3452ff15a0c24e0085c0753c8b55a08b423085c074328945a050ff15a4c24e0085c075248b4de0ff55a085c0741d8945a46a0450ff15a0c24e0085c0750d8b45a48b008945f8eb0383c408e9a47ef7ff')
ORIGINAL = bytes.fromhex('8b108955e08b45e08b108b4de0ff52308b008945f8')
JUMP = (b'\xe9' + struct.pack('<i',0x4eb600-0x463507)).ljust(len(ORIGINAL), b'\x90')
SITES = ((0x63502, ORIGINAL, JUMP), (0xeb600, bytes(256), CODE.ljust(256,b'\x90')))

def state(data):
    if len(data)!=1069098 or data[:2]!=b'MZ':
        raise ValueError('패널 보호 패치: 지원하지 않는 게임 버전')
    flags=[]
    for offset, original, patched in SITES:
        value=data[offset:offset+len(original)]
        if value not in (original,patched):
            raise ValueError(f'패널 보호 코드 충돌: {offset:#x}')
        flags.append(value==patched)
    if len(set(flags))!=1:
        raise ValueError('불완전한 패널 보호 패치')
    return flags[0]

def apply(path, enabled=True):
    path=Path(path)
    data=path.read_bytes()
    if state(data)==enabled:
        return
    # .text padding must already be mapped by the peer-address patch.
    if enabled and struct.unpack_from('<I',data,0x208)[0]!=0xeb000:
        raise ValueError('주소 응답 패치를 먼저 적용하세요.')
    backup=path.with_name(path.name+'.bak_panelguard_'+hashlib.sha256(data).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes()!=data:
            raise ValueError('백업 충돌')
    else:
        with backup.open('xb') as f:
            f.write(data)
    result=bytearray(data)
    for offset,original,patched in SITES:
        result[offset:offset+len(original)]=patched if enabled else original
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(result)
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes()!=data:
            raise ValueError('게임 파일이 변경됐습니다.')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
