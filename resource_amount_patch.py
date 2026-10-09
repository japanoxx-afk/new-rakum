"""Optional, reversible patch: normal multiplayer honors map resource amount."""
from pathlib import Path
import hashlib
import os
import tempfile
import subprocess
import csv

SOURCE='ef006b8b3a5319279e4313e6faed873ca655082643cb79535d81f05804306d16'
OFFSET=0xcda4
OLD=bytes.fromhex('8b450833c98a4806f7d91bc981e1d007000081c1b80b000051')
NEW=bytes.fromhex('8b45088b481051').ljust(len(OLD),b'\x90')


def transform(data,enabled=True):
    current=data[OFFSET:OFFSET+len(OLD)]
    if current not in (OLD,NEW):raise ValueError('지원하지 않는 자원 로더입니다.')
    normalized=data[:OFFSET]+OLD+data[OFFSET+len(OLD):]
    if hashlib.sha256(normalized).hexdigest()!=SOURCE:
        raise ValueError('확인된 설치본 1.000d 전용입니다. 고해상도 시험본 등 다른 파일에는 적용하지 않습니다.')
    return data[:OFFSET]+(NEW if enabled else OLD)+data[OFFSET+len(OLD):]


def apply(path,enabled=True):
    path=Path(path).resolve()
    if path.name.lower()!='rhakmu.exe':raise ValueError('Rhakmu.exe를 선택하세요.')
    result=subprocess.run(['tasklist','/FI','IMAGENAME eq Rhakmu.exe','/FO','CSV','/NH'],
        capture_output=True,text=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if any(row and row[0].lower()=='rhakmu.exe' for row in csv.reader(result.stdout.splitlines())):
        raise ValueError('게임을 모두 종료한 뒤 다시 시도하세요.')
    data=path.read_bytes();output=transform(data,enabled)
    if output==data:return
    backup=path.with_name(path.name+'.bak_resource_amount_'+hashlib.sha256(data).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes()!=data:raise ValueError('백업 충돌')
    else:
        with backup.open('xb') as target:target.write(data)
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as target:
            target.write(output);target.flush();os.fsync(target.fileno())
        if path.read_bytes()!=data:raise ValueError('게임 파일이 변경되었습니다.')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
