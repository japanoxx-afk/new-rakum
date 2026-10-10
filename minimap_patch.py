"""Verified release patch; rendering-only fog/resource preview, atomic backup."""
import base64,hashlib,json,os,sys,tempfile,zlib
import subprocess
from pathlib import Path

def manifest():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    return json.loads((root/'minimap_release.json').read_text(encoding='utf-8'))

def ensure_closed(path):
    folder=str(Path(path).resolve().parent).replace("'","''")
    script=f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -in @('Rhakmu.exe','Launcher.exe') -and (-not $_.ExecutablePath -or (Split-Path -LiteralPath $_.ExecutablePath -Parent) -eq '{folder}') }} | Select-Object -ExpandProperty ProcessId"
    result=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,creationflags=0x08000000)
    if result.returncode or result.stdout.strip():raise RuntimeError('해당 설치 폴더의 게임을 완전히 종료한 뒤 적용하세요.')

def underlying(data):
    spec=manifest()
    if len(data)==spec['source_size']:return bytes(data)
    if len(data)!=spec['patched_size']:raise ValueError('미니맵: 지원하지 않는 게임 파일 크기')
    for variant in spec['variants']:
        if data[spec['source_size']:]!=zlib.decompress(base64.b64decode(variant['tail'])):continue
        if not all(data[e['offset']:e['offset']+len(bytes.fromhex(e['after']))]==bytes.fromhex(e['after']) for e in variant['edits']):continue
        result=bytearray(data[:spec['source_size']])
        for e in variant['edits']:
            at=e['offset'];before=bytes.fromhex(e['before']);result[at:at+len(before)]=before
        return bytes(result)
    raise ValueError('미니맵 패치가 불완전하거나 알 수 없는 변경이 있습니다.')

def transform(data,enabled=True):
    import viewport_patch
    source=underlying(data)
    # Validate every underlying byte, preserving all known independent settings.
    viewport_patch.transform(source,False)
    if not enabled:return source
    high=source[0xca690]==0xe9
    variant=next(v for v in manifest()['variants'] if v['highres']==high)
    result=bytearray(source)
    for e in variant['edits']:
        at=e['offset'];before=bytes.fromhex(e['before']);after=bytes.fromhex(e['after'])
        if result[at:at+len(before)]!=before:raise ValueError('지원하지 않는 미니맵 실행 경로')
        result[at:at+len(after)]=after
    return bytes(result)+zlib.decompress(base64.b64decode(variant['tail']))

def replace(path,original,changed):
    path=Path(path).resolve()
    if path.name.lower()!='rhakmu.exe':raise ValueError('Rhakmu.exe를 선택하세요.')
    if original==changed:return
    ensure_closed(path)
    backup=path.with_name(path.name+'.bak_minimap_'+hashlib.sha256(original).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes()!=original:raise ValueError('미니맵 백업 충돌')
    else:
        with backup.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:f.write(changed);f.flush();os.fsync(f.fileno())
        ensure_closed(path)
        if path.read_bytes()!=original:raise ValueError('게임 파일이 변경되어 적용을 중단합니다.')
        os.replace(temp,path)
        if path.read_bytes()!=changed:raise ValueError('교체 후 검증 실패; 백업 보존')
    finally:
        if os.path.exists(temp):os.unlink(temp)

def apply(path,enabled=True):
    path=Path(path);data=path.read_bytes();replace(path,data,transform(data,enabled))

def prepare(path,highres):
    import viewport_patch,peer_address_patch,sync_port_patch,panel_guard_patch
    path=Path(path);original=path.read_bytes();data=underlying(original)
    peer_address_patch.state(data);sync_port_patch.state(data);panel_guard_patch.state(data)
    result=bytearray(data)
    result[sync_port_patch.OFFSET:sync_port_patch.OFFSET+len(sync_port_patch.PATCHED)]=sync_port_patch.PATCHED
    data=peer_address_patch.transform(bytes(result),True)
    result=bytearray(data)
    for at,before,after in panel_guard_patch.SITES:result[at:at+len(after)]=after
    if result[0xd7b97]==3:result[0xd7abe]=4
    result[0xd7b97]=5
    if highres:
        for name,digest in viewport_patch.manifest()['dll_hashes'].items():
            if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=digest:raise ValueError(f'지원하지 않는 {name}')
        if not (path.parent/'ddraw.dll').is_file():raise ValueError('ddraw.dll이 필요합니다.')
    data=viewport_patch.transform(bytes(result),highres)
    data=transform(data)
    replace(path,original,data)
