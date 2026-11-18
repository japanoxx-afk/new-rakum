"""v0.9031.1: undo changes made by v0.9034+ launchers so this launcher's checks pass.

Newer launchers (v0.9034+) write a larger Rhakmu.exe (minimap build) and may add the
rally-gold patch, a newer 0x8813 helper and a pinned TG_Net.dll address. v0.9031 only
understands Rhakmu.exe 1.000d (1,069,098 bytes) and stops with
"Rhakmu.exe 1.000d 파일이 필요합니다." This converts the files back, keeping every other
patch byte, with a backup and atomic replacement.
"""
import base64
import hashlib
import json
import os
import sys
import tempfile
import zlib
from pathlib import Path

import rally_gold_patch
import game_address_patch

SOURCE_SIZE = 1069098
PEER_AT = 0xEB420
# v0.9016 helper (what v0.9031 writes) and the v0.9042 helper (25.x + 26.x)
PEER_9016 = bytes.fromhex('9c608b75fc8b7e18837f080c0f85810000008b570c66813a1388757766837a020a75708b42063b05c412b40075650fb605cc12b4003a420575590fb64a0483f908735039c1744c8b1f80fb1a754569c1e011000080b80e797f0020723683b834797f0000742d899834797f0089cf69c984020000895c0e5466c7440e50020066c7440e522bd757681488000089f1e82dd9f5ff619de92deef5ff')
PEER_9042 = bytes.fromhex('9c608b75fc8b7e18837f080c0f85840000008b570c66813a1388757a66837a020a75738b42063b05c412b40075680fb605cc12b4003a4205755c0fb64a0483f908735339c1744f8b1f8d53e780fa01774569c1e011000080b80e797f0020723683b834797f0000742d899834797f0089cf69c984020000895c0e5466c7440e50020066c7440e522bd757681488000089f1e82ad9f5ff619de92aeef5ff')


def _manifest():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return json.loads((root / 'minimap_release.json').read_text(encoding='utf-8'))


def underlying(data):
    spec = _manifest()
    if len(data) == spec['source_size']:
        return bytes(data)
    if len(data) != spec['patched_size']:
        raise ValueError(f'지원하지 않는 Rhakmu.exe 크기입니다 ({len(data):,}B).')
    for variant in spec['variants']:
        if data[spec['source_size']:] != zlib.decompress(base64.b64decode(variant['tail'])):
            continue
        if not all(data[e['offset']:e['offset'] + len(bytes.fromhex(e['after']))] == bytes.fromhex(e['after'])
                   for e in variant['edits']):
            continue
        result = bytearray(data[:spec['source_size']])
        for e in variant['edits']:
            before = bytes.fromhex(e['before'])
            result[e['offset']:e['offset'] + len(before)] = before
        return bytes(result)
    raise ValueError('최신 런처의 미니맵 패치 상태를 알 수 없습니다. 게임 파일을 다시 설치하세요.')


def to_legacy(data):
    """Rhakmu.exe bytes as v0.9031 expects them (unchanged when already compatible)."""
    out = bytearray(rally_gold_patch.strip(underlying(data)))
    if bytes(out[PEER_AT:PEER_AT + 256]) == PEER_9042.ljust(256, b'\x90'):
        out[PEER_AT:PEER_AT + 256] = PEER_9016.ljust(256, b'\x90')
    return bytes(out)


def convert_exe(path):
    """Rewrite Rhakmu.exe for v0.9031. Returns True when the file changed."""
    path = Path(path)
    data = path.read_bytes()
    result = to_legacy(data)
    if result == data:
        return False
    backup = path.with_name(path.name + '.bak_newlauncher_' + hashlib.sha256(data).hexdigest()[:16])
    if not backup.exists():
        backup.write_bytes(data)
    fd, temp = tempfile.mkstemp(prefix='.legacy-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(result)
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != data:
            raise ValueError('게임 파일이 변경되어 변환을 중단했습니다.')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def restore_tgnet(game_dir, session_dir=None):
    """Undo a TG_Net.dll address pin left by v0.9041+ (not one owned by a radmin session)."""
    if session_dir and os.path.exists(os.path.join(session_dir, 'address.json')):
        return False
    try:
        if game_address_patch.state(game_dir) is None:
            return False
        return game_address_patch.apply(game_dir, None)
    except (OSError, ValueError):
        return False


def prepare(game_dir, session_dir=None):
    """Convert files left by newer launchers. Returns a short status message ('' = nothing)."""
    notes = []
    if convert_exe(os.path.join(game_dir, 'Rhakmu.exe')):
        notes.append('Rhakmu.exe 를 1.000d 형식으로 변환')
    if restore_tgnet(game_dir, session_dir):
        notes.append('TG_Net.dll 주소 고정 해제')
    return ', '.join(notes)
