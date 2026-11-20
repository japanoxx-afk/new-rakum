"""모든 PC가 같은 Rhakmu.exe 1.000d 를 쓰게 한다.

게임은 방에 들어올 때 방장 쪽에서 상대 게임 버전을 비교하고(0x4452A7), 다르면 입장을 거절한다
(상대는 로비로 튕김). 1.000d 는 버전 1003 (0x4233A9 mov word [ecx+0x9A0], 0x3EB) 이고, 그 이전판은
1000 을 보낸다. 원래는 TriggerSoft 실행기(Launcher.exe)가 업데이트 서버에서 받아 맞췄지만 그 서버가
없어져 PC마다 판이 달라졌다.

확인 방법: 설치된 Rhakmu.exe 를 런처의 패치 과정으로 '패치 없는 상태'로 되돌려 만든 결과가
원본 1.000d 로 만든 결과와 같은지 본다 (런처가 이미 패치한 파일도 1.000d 로 인정).
다르거나 되돌릴 수 없으면 기존 파일을 백업하고 런처에 포함된 원본 1.000d 로 바꾼다.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

ORIGINAL_SHA256 = "1982c777f14ef8b2a422769585f81d04d169bcbeb33f2a2afe67c343e9bcbc9a"
ORIGINAL_SIZE = 1069098
BUNDLED_DIR = "game_1000d"            # PyInstaller datas 안의 폴더 (spec 참고)


def bundled_path() -> Path:
    here = Path(__file__).resolve().parent
    for p in (Path(getattr(sys, "_MEIPASS", here)) / BUNDLED_DIR / "Rhakmu.exe",
              here / "game_backup" / "Rhakmu.exe"):
        if p.is_file():
            return p
    raise FileNotFoundError("런처에 원본 Rhakmu.exe 1.000d 가 들어 있지 않습니다.")


def bundled() -> bytes:
    data = bundled_path().read_bytes()
    if len(data) != ORIGINAL_SIZE or hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("런처에 들어 있는 원본 Rhakmu.exe 가 손상되었습니다.")
    return data


def _normalized(data: bytes) -> bytes:
    import minimap_patch
    return minimap_patch.build(data, False, False, False, False)


def is_1000d(data: bytes) -> bool:
    """원본 1.000d 이거나 이 런처가 패치한 1.000d 이면 True."""
    if hashlib.sha256(data).hexdigest() == ORIGINAL_SHA256:
        return True
    try:
        return _normalized(data) == _normalized(bundled())
    except (ValueError, KeyError, IndexError):
        return False


def ensure(path) -> str:
    """path 의 Rhakmu.exe 가 1.000d 가 아니면 백업 후 원본 1.000d 로 바꾼다. 바꿨으면 안내문, 아니면 ''."""
    path = Path(path)
    current = path.read_bytes()
    if is_1000d(current):
        return ""
    original = bundled()
    backup = path.with_name(path.name + ".bak_not1000d_" + hashlib.sha256(current).hexdigest()[:16])
    if not backup.exists():
        with backup.open("xb") as f:
            f.write(current)
            f.flush()
            os.fsync(f.fileno())
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(original)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    if path.read_bytes() != original:
        raise ValueError("Rhakmu.exe 1.000d 교체 후 검증 실패 (백업: %s)" % backup.name)
    return ("Rhakmu.exe 가 1.000d 가 아니어서 런처에 포함된 1.000d 로 바꿨습니다.\n"
            "(다른 PC와 게임 버전이 달라 방 입장이 거절되는 문제 방지)\n기존 파일 백업: %s" % backup.name)
