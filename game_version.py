"""모든 PC가 같은 Rhakmu.exe 1.000d 를 쓰게 한다.

게임은 방에 들어올 때 방장 쪽에서 상대 게임 버전을 비교하고(0x4452A7), 다르면 입장을 거절한다
(상대는 로비로 튕김). 1.000d 는 버전 1003 (0x4233A9 mov word [ecx+0x9A0], 0x3EB) 이고, 그 이전판은
1000 을 보낸다. 원래는 TriggerSoft 실행기(Launcher.exe)가 업데이트 서버에서 받아 맞췄지만 그 서버가
없어져 PC마다 판이 달라졌다.

확인 방법: 설치된 Rhakmu.exe 를 런처의 패치 과정으로 '패치 없는 상태'로 되돌려 만든 결과가
원본 1.000d 로 만든 결과와 같은지 본다 (런처가 이미 패치한 파일도 1.000d 로 인정).
다르거나 되돌릴 수 없으면 기존 파일을 백업하고 런처에 포함된 원본 1.000d 로 바꾼다.

공식 패치 Patch1003.exe (2003-04-11, 게임을 새로 설치한 뒤 따로 깔아야 했던 것) 가 하는 일은 이것뿐이다
(설치 파일을 풀어 확인 — 'IFFH' 묶음: [dword 원래 크기][dword 압축 크기][crc][시각][ff*8][이름 길이][이름][deflate]):
  1. Rhakmu.exe  -> 1.000d (sha256 1982c777… = 런처에 든 것과 같은 파일)
  2. Rhakmu.000  -> Rhakmu.exe 의 디버그 정보(PDB). 게임 실행·대전과 무관해서 런처는 넣지 않는다.
  3. +패치 내용+.txt (안내문)
  4. 레지스트리 HKLM/SOFTWARE/TriggerSoft/RhakMu 의 GameVer = 1003 (TriggerSoft 실행기의 업데이트 확인용)
그래서 런처가 1 과 4 를 해 주면 Patch1003.exe 를 깔지 않은 새 설치본도 같은 상태가 된다 (apply_official_patch).
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

ORIGINAL_SHA256 = "1982c777f14ef8b2a422769585f81d04d169bcbeb33f2a2afe67c343e9bcbc9a"
ORIGINAL_SIZE = 1069098
OFFICIAL_VERSION = 1003               # Patch1003 = 1.000d
REGISTRY_KEY = r"SOFTWARE\TriggerSoft\RhakMu"
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
        _replace_exe(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    if path.read_bytes() != original:
        raise ValueError("Rhakmu.exe 1.000d 교체 후 검증 실패 (백업: %s)" % backup.name)
    return ("Rhakmu.exe 가 1.000d 가 아니어서 런처에 포함된 1.000d 로 바꿨습니다.\n"
            "(공식 패치 Patch1003.exe 와 같은 파일입니다. 패치를 따로 설치하지 않아도 됩니다.)\n"
            "기존 파일 백업: %s" % backup.name)


def _replace_exe(temp, path) -> None:
    """임시 파일을 Rhakmu.exe 위로 옮긴다. 쓰기 금지 속성이면 풀고 한 번 더 한다.

    실패하면 원인 후보를 알려 준다 (WinError 5 = 게임이 같은 파일을 쓰는 중, 쓰기 금지, 또는 폴더 권한 없음).
    """
    try:
        os.replace(temp, path)
        return
    except PermissionError:
        pass
    try:
        if os.name == "nt" and os.path.exists(path):
            os.chmod(path, 0o666)           # 읽기 전용 속성 해제
        os.replace(temp, path)
    except PermissionError as e:
        raise ValueError(
            "Rhakmu.exe 를 바꾸지 못했습니다 (WinError 5: 액세스 거부).\n"
            "- 라크무 게임 창이 아직 떠 있으면 모두 닫고 다시 누르세요.\n"
            "- 게임 폴더가 Program Files 라서 권한이 없으면 런처를 '관리자 권한으로 실행' 하세요.\n"
            "- 그래도 안 되면 진단 리포트를 만들어 주세요.\n"
            "(%s)" % e) from e


def ensure_registry(winreg=None) -> bool:
    """레지스트리 GameVer 를 Patch1003 과 같이 1003 으로. 바꿨으면 True.
    게임 설치 정보(키·값)가 없으면 만들지 않는다. 값 종류(숫자/문자열)는 설치본이 쓰던 그대로 둔다."""
    if winreg is None:
        try:
            import winreg
        except ImportError:
            return False
    access = winreg.KEY_READ | winreg.KEY_WRITE | getattr(winreg, "KEY_WOW64_32KEY", 0)   # 32비트 게임의 키
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, access) as key:
            try:
                value, kind = winreg.QueryValueEx(key, "GameVer")
            except OSError:
                return False
            if kind == winreg.REG_DWORD:
                want = OFFICIAL_VERSION
            elif kind == winreg.REG_SZ:
                want = str(OFFICIAL_VERSION)
            else:
                return False
            if value == want:
                return False
            winreg.SetValueEx(key, "GameVer", 0, kind, want)
            return True
    except OSError:
        return False


def apply_official_patch(game_dir, winreg=None) -> str:
    """Patch1003.exe 를 깔지 않은 설치본도 같은 상태로: Rhakmu.exe 1.000d + 레지스트리 GameVer.
    Rhakmu.exe 를 바꿨으면 안내문, 아니면 ''. Rhakmu.exe 가 없으면 아무것도 하지 않는다."""
    exe = Path(game_dir) / "Rhakmu.exe"
    if not exe.is_file():
        return ""
    note = ensure(exe)
    ensure_registry(winreg)
    return note
