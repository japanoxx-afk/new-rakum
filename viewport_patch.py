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

def manifest():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return json.loads((root/'viewport_release.json').read_text(encoding='utf-8'))

def transform(data,enabled=True):
    spec=manifest();result=bytearray(data);flags=[]
    if len(data)!=1069098:raise ValueError('고해상도: 지원하지 않는 실행 파일 크기')
    for edit in spec['edits']:
        offset=int(edit['va'],16)-0x400000
        before,after=bytes.fromhex(edit['before']),bytes.fromhex(edit['after'])
        actual=data[offset:offset+len(before)]
        if actual not in (before,after):raise ValueError(f'고해상도 코드 충돌: {offset:#x}')
        flags.append(actual==after)
        result[offset:offset+len(before)]=before
    if len(set(flags))!=1:
        # Accept only complete, recorded prior releases, never arbitrary mixtures.
        accepted=False
        for legacy in spec.get('legacy_edits',[]):
            candidate=bytearray(result)
            for edit in legacy:
                offset=int(edit['va'],16)-0x400000;after=bytes.fromhex(edit['after'])
                candidate[offset:offset+len(after)]=after
            if candidate==data:accepted=True;break
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
    if hashlib.sha256(normalized).hexdigest()!=spec['source_hash']:
        raise ValueError('검증되지 않은 게임 파일입니다. 고해상도 패치를 적용하지 않았습니다.')
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
