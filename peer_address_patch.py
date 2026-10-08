"""Repair the discarded 0x8813 address announcement for Radmin peers only.

Does not bypass checksums or treat announcements as game data. The original
receive loop validates CRC first; the helper additionally validates length,
type, session, recipient, active sender slot and Radmin source prefix.
"""
import hashlib
import os
from pathlib import Path
import struct
import tempfile

CODE = bytes.fromhex('9c608b75fc8b7e18837f080c75728b570c66813a1388756866837a020a75618b42063b05c412b40075560fb605cc12b4003a4205754a0fb64a0483f908734139c1743d8b1f80fb1a753669c1e011000080b80e797f0020722783b834797f0000741e899834797f0069c984020000895c0e5466c7440e50020066c7440e522bd7619de940eef5ff')
PREFIX = bytes.fromhex('8b4dfc8b51188b420c8b48063b0dc412b400751d8b55fc8b42188b480c0fbe51050fbe05cc12b4003bd07505')
TEXT_HEADER = bytes.fromhex('2e7465787400000012a40e000010000000b00e000010000000000000000000000000000020000060')
SITES = (
    (0x49f88, bytes.fromhex('e95a030000'), b'\xe9' + struct.pack('<i', 0x4eb420 - 0x449f8d)),
    (0xeb420, bytes(256), CODE.ljust(256, b'\x90')),
    # Make the already file-backed .text padding explicitly executable code.
    (0x208, struct.pack('<I', 0xea412), struct.pack('<I', 0xeb000)),
)

def state(data):
    if len(data) != 1069098 or data[:2] != b'MZ':
        raise ValueError('Rhakmu.exe 1.000d 파일이 필요합니다.')
    header = bytearray(data[0x200:0x228])
    header[8:12] = TEXT_HEADER[8:12]
    if bytes(header) != TEXT_HEADER or data[0x49f5c:0x49f88] != PREFIX:
        raise ValueError('지원하지 않는 수신 코드/실행 파일입니다. 변경하지 않았습니다.')
    states = []
    for offset, original, patched in SITES:
        value = data[offset:offset + len(original)]
        if value not in (original, patched):
            raise ValueError(f'패치 영역 충돌: {offset:#x}. 변경하지 않았습니다.')
        states.append(value == patched)
    if len(set(states)) != 1:
        raise ValueError('불완전한 패치 상태입니다. 백업 확인이 필요합니다.')
    return states[0]

def transform(data, enabled):
    state(data)
    result = bytearray(data)
    for offset, original, patched in SITES:
        result[offset:offset + len(original)] = patched if enabled else original
    return bytes(result)

def apply(path, enabled=True):
    path = Path(path)
    data = path.read_bytes()
    if state(data) == enabled:
        return '이미 적용되어 있습니다.' if enabled else '이미 원복되어 있습니다.'
    backup = path.with_name(path.name + '.bak_peeraddr_' + hashlib.sha256(data).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes() != data:
            raise ValueError('백업 파일 충돌')
    else:
        with backup.open('xb') as f:
            f.write(data)
    fd, temp = tempfile.mkstemp(prefix='peeraddr_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(transform(data, enabled))
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != data:
            raise ValueError('다른 작업이 게임 파일을 변경했습니다.')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return '라드민 상대 주소 복구 패치 ' + ('적용' if enabled else '원복') + ' 완료'
