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
    import hotkey_patch,selection_patch,replay_record_patch,smart_cast_patch
    data=smart_cast_patch.strip(data)   # 맨 뒤 섹션(.scast, 마법 순차 시전)부터 걷어냄
    data=hotkey_patch.strip(data)   # 단축키 섹션은 미니맵 꼬리 뒤에 붙으므로 먼저 걷어냄
    data=replay_record_patch.strip(data)   # 그 아래 리플레이 명령 기록 섹션
    data=selection_patch.strip(data)   # 그 아래 선택 한도 24 섹션과 코드 수정도 걷어냄
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

def _strip_text_patches(data):
    """.text 여유 공간을 쓰는 독립 패치들을 걷어낸 원본 상태 (고해상도 전체 파일 검증 전에 사용)."""
    import rally_gold_patch,menu_free_guard_patch,queue_cancel_patch,rally_construct_patch,rally_spawn_patch,production_split_patch
    data=queue_cancel_patch.transform(menu_free_guard_patch.transform(rally_gold_patch.strip(data),False),False)
    data=rally_spawn_patch.transform(rally_construct_patch.transform(data,False),False)
    import package_mode_patch,turn_length_patch
    data=package_mode_patch.transform(production_split_patch.transform(data,False),False)
    return turn_length_patch.transform(data,turn_length_patch.ORIGINAL)

def transform(data,enabled=True):
    import viewport_patch,rally_gold_patch
    import menu_free_guard_patch,queue_cancel_patch
    source=_strip_text_patches(underlying(data))
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

def prepare(path,highres,rally_gold=True,hotkeys=True,select24=False,record=False,start_save=False,play=False,rally_spawn=False,wide_checks=True,package=False,turn_frames=5):
    import viewport_patch
    path=Path(path);original=path.read_bytes()
    if highres:
        for name,digest in viewport_patch.manifest()['dll_hashes'].items():
            if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=digest:raise ValueError(f'지원하지 않는 {name}')
        if not (path.parent/'ddraw.dll').is_file():raise ValueError('ddraw.dll이 필요합니다.')
    replace(path,original,build(original,highres,rally_gold,hotkeys,select24,record,start_save,play,rally_spawn,wide_checks,package,turn_frames))

def build(original,highres,rally_gold=True,hotkeys=True,select24=False,record=False,start_save=False,play=False,rally_spawn=False,wide_checks=True,package=False,turn_frames=5):
    """설치 파일 바이트 -> 실행용 최종 바이트 (메모리 안에서만; 파일은 건드리지 않음)."""
    import viewport_patch,peer_address_patch,sync_port_patch,panel_guard_patch,rally_gold_patch,hotkey_patch,selection_patch,menu_free_guard_patch,replay_record_patch,queue_cancel_patch
    import rally_construct_patch,rally_spawn_patch,production_split_patch
    data=_strip_text_patches(underlying(original))
    peer_address_patch.state(data);sync_port_patch.state(data);panel_guard_patch.state(data)
    result=bytearray(data)
    result[sync_port_patch.OFFSET:sync_port_patch.OFFSET+len(sync_port_patch.PATCHED)]=sync_port_patch.PATCHED
    data=peer_address_patch.transform(bytes(result),True)
    result=bytearray(data)
    for at,before,after in panel_guard_patch.SITES:result[at:at+len(after)]=after
    if result[0xd7b97]==3:result[0xd7abe]=4
    result[0xd7b97]=5
    data=viewport_patch.transform(bytes(result),highres)
    data=transform(data)
    data=rally_gold_patch.apply(data,rally_gold)   # 다른 패치 검증은 원본 기준
    data=menu_free_guard_patch.transform(data,True)   # 메뉴 해제 크래시 보호 (항상, 고해상도 검증 뒤)
    data=queue_cancel_patch.transform(data,True)   # ESC 는 예약된 대기열부터 취소 (항상)
    data=rally_construct_patch.transform(data,True)   # 건설 중인 건물에도 집결지 지정 (항상, 보내는 쪽만)
    data=rally_spawn_patch.transform(data,rally_spawn)   # 생산 유닛이 집결지 쪽에서 나옴 (대전 규칙)
    data=production_split_patch.transform(data,True)   # 같은 건물 여러 개: 생산·연구를 나눠 맡김 (항상, 보내는 쪽만)
    import package_mode_patch
    data=package_mode_patch.transform(data,package)   # 싱글플레이 실행 때만: CD 키 확인 건너뜀·경기 시계·점수 화면 뒤 종료
    import turn_length_patch
    data=turn_length_patch.transform(data,turn_frames if turn_frames in turn_length_patch.CHOICES else turn_length_patch.ORIGINAL)   # 멀티 턴 길이 (대전 규칙; 재생은 그 리플레이의 값)
    data=selection_patch.apply(data,select24)      # 미니맵 섹션 뒤 .sel24 (선택 한도 24)
    data=replay_record_patch.apply(data,record or play,start_save,play,wide_checks or not play,turn_frames)    # 그 뒤 .rkrec (리플레이 기록/재생; 넓은 검사값은 기록 항상, 재생은 그 리플레이에 맞춤)
    data=hotkey_patch.apply(data,hotkeys)        # 그 뒤에 단축키 섹션 (.sel24 가 있으면 24칸 판)
    import smart_cast_patch
    return smart_cast_patch.apply(data,True)       # 맨 뒤 .scast: 마법 순차 시전 (항상, 보내는 쪽만)
