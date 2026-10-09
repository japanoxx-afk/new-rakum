"""Reversible allowlisted viewport patch; no assembler dependency at runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import panel_guard_patch
import resource_amount_patch

# Exact compatibility variant supplied by B PC (SHA256 8ad112d1...daa95).
# Preserve its three deleting-destructor guards; normalize validation copy only.
# This does not establish that the old guards fix the original heap corruption.
LEGACY_DELETE_SITES = (
    (0x1e94e, bytes.fromhex('8b4dfc51e829eb0b0083c404')),
    (0x1f6ce, bytes.fromhex('8b4dfc51e8a9dd0b0083c404')),
    (0x2234e, bytes.fromhex('8b4dfc51e829b10b0083c404')),
)

def manifest():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return json.loads((root/'viewport_release.json').read_text(encoding='utf-8'))

def transform(data,enabled=True):
    spec=manifest();result=bytearray(data)
    if len(data)!=1069098:raise ValueError('고해상도: 지원하지 않는 실행 파일 크기')
    def matches(blob, edits, key):
        return all(blob[int(e['va'],16)-0x400000:int(e['va'],16)-0x400000+len(bytes.fromhex(e[key]))]
                   ==bytes.fromhex(e[key]) for e in edits)
    if not matches(data,spec['edits'],'before'):
        accepted=False
        for layout in [spec['edits'],*spec.get('legacy_edits',[])]:
            if not matches(data,layout,'after'):continue
            candidate=bytearray(data)
            for edit in layout:
                offset=int(edit['va'],16)-0x400000;before=bytes.fromhex(edit['before'])
                candidate[offset:offset+len(before)]=before
            if matches(candidate,spec['edits'],'before'):
                result=candidate;accepted=True;break
        if not accepted:raise ValueError('불완전한 고해상도 패치입니다. 원본 백업을 사용하세요.')
    normalized=bytearray(result)
    panel_guard_patch.state(normalized)
    for offset,before,_ in panel_guard_patch.SITES:normalized[offset:offset+len(before)]=before
    # Preserve independent quantity/latency settings; normalize validation copy only.
    at=resource_amount_patch.OFFSET
    amount=normalized[at:at+len(resource_amount_patch.OLD)]
    if amount not in (resource_amount_patch.OLD,resource_amount_patch.NEW):raise ValueError('알 수 없는 자원량 패치')
    normalized[at:at+len(amount)]=resource_amount_patch.OLD
    if normalized[0xd7abe] not in (1,2,3,4):raise ValueError('알 수 없는 명령 지연 설정')
    normalized[0xd7abe]=4
    if normalized[0xd7b96:0xd7b9b] not in (bytes.fromhex('b905000000'),bytes.fromhex('b903000000')):
        raise ValueError('알 수 없는 명령 전송 간격')
    normalized[0xd7b97]=5
    delete_states=[]
    for offset,original in LEGACY_DELETE_SITES:
        value=normalized[offset:offset+len(original)]
        if value not in (original,b'\x90'*len(original)):
            raise ValueError('알 수 없는 객체 해제 패치')
        delete_states.append(value!=original)
        normalized[offset:offset+len(original)]=original
    if len(set(delete_states))!=1:
        raise ValueError('불완전한 객체 해제 호환 패치')
    if hashlib.sha256(normalized).hexdigest()!=spec['source_hash']:
        raise ValueError('검증되지 않은 게임 파일입니다. 고해상도 패치를 적용하지 않았습니다.\n'
                         '파일 SHA256: '+hashlib.sha256(data).hexdigest()+'\n'
                         '검증 기준 SHA256: '+hashlib.sha256(normalized).hexdigest()+'\n'
                         '임의 패치는 적용하지 않습니다. 설치된 Rhakmu.exe를 ZIP으로 보내 주세요.')
    if enabled:
        for edit in spec['edits']:
            offset=int(edit['va'],16)-0x400000;after=bytes.fromhex(edit['after'])
            result[offset:offset+len(after)]=after
    return bytes(result)

def ensure_closed():
    for name in ('Rhakmu.exe','Launcher.exe'):
        result=subprocess.run(['tasklist','/FI',f'IMAGENAME eq {name}','/FO','CSV','/NH'],
            capture_output=True,text=True,check=True,creationflags=0x08000000)
        if name.lower() in result.stdout.lower():raise RuntimeError('게임을 종료한 뒤 해상도를 적용하세요.')

def apply(path,enabled=True):
    path=Path(path).resolve()
    if path.name.lower()!='rhakmu.exe':raise ValueError('Rhakmu.exe를 선택하세요.')
    ensure_closed()
    if enabled:
        for name,digest in manifest()['dll_hashes'].items():
            if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=digest:
                raise ValueError(f'고해상도: 지원하지 않는 {name}')
        if not (path.parent/'ddraw.dll').is_file():raise ValueError('호환 출력 모듈 ddraw.dll이 필요합니다.')
    data=path.read_bytes();changed=transform(data,enabled)
    if data==changed:return
    backup=path.with_name(path.name+'.bak_viewport_'+hashlib.sha256(data).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes()!=data:raise ValueError('고해상도 백업 충돌')
    else:
        with backup.open('xb') as stream:stream.write(data)
    fd,temp=tempfile.mkstemp(prefix='.viewport-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(changed);stream.flush();os.fsync(stream.fileno())
        ensure_closed()
        if path.read_bytes()!=data:raise ValueError('게임 파일이 변경되어 적용을 중단했습니다.')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
