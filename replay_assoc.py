"""리플레이 파일(.rkr)을 탐색기에서 더블클릭하면 런처가 게임 화면으로 재생하도록 연결.

- register(exe): 현재 사용자(HKCU\\Software\\Classes)에 .rkr -> "<런처>" "%1" 을 등록 (관리자 권한 불필요).
  런처 파일 이름에 버전이 들어 있어 업데이트 뒤 경로가 바뀌므로 런처를 켤 때마다 다시 쓴다.
- 런처가 이미 켜져 있으면 새로 띄우지 않고 요청 파일(%LOCALAPPDATA%\\RhakMu\\open_replay.txt)에 경로를 적어 넘긴다.
  켜져 있는 런처가 1초마다 읽어 재생한다. 켜져 있는지는 이름 있는 뮤텍스로 안다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

EXT = ".rkr"
PROG_ID = "RhakMu.Replay"
MUTEX_NAME = "Local\\RhakMuLauncherRunning"
REQUEST_FILE = "open_replay.txt"
_mutex = None


def find_replay_arg(args) -> str | None:
    """명령줄 인자 가운데 실제로 있는 .rkr 파일 (없으면 None)."""
    for a in args:
        if a.lower().endswith(EXT) and os.path.isfile(a):
            return os.path.abspath(a)
    return None


def open_command(exe) -> str:
    return f'"{exe}" "%1"'


def request_path() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "RhakMu" / REQUEST_FILE


def write_request(path, request=None):
    request = Path(request or request_path())
    request.parent.mkdir(parents=True, exist_ok=True)
    tmp = request.with_name(request.name + ".tmp")
    tmp.write_text(str(path), encoding="utf-8")
    os.replace(tmp, request)


def take_request(request=None) -> str | None:
    """넘겨받은 리플레이 경로를 읽고 요청 파일을 지운다 (없으면 None)."""
    request = Path(request or request_path())
    try:
        text = request.read_text(encoding="utf-8").strip()
        request.unlink()
    except OSError:
        return None
    return text if text.lower().endswith(EXT) and os.path.isfile(text) else None


def register(exe) -> bool:
    """.rkr 더블클릭 -> 이 런처. 바뀐 것이 있으면 True."""
    if os.name != "nt":
        return False
    import winreg
    exe = str(Path(exe).resolve())
    wanted = (
        (rf"Software\Classes\{EXT}", "", PROG_ID),
        (rf"Software\Classes\{PROG_ID}", "", "라크무 리플레이"),
        (rf"Software\Classes\{PROG_ID}\DefaultIcon", "", f'"{exe}",0'),
        (rf"Software\Classes\{PROG_ID}\shell\open\command", "", open_command(exe)),
    )
    changed = False
    for key, name, value in wanted:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            try:
                current = winreg.QueryValueEx(k, name)[0]
            except OSError:
                current = None
            if current != value:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
                changed = True
    if changed:
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
        except Exception:
            pass
    return changed


def mark_running() -> None:
    """켜져 있는 런처 표시 (프로세스가 끝나면 사라짐)."""
    global _mutex
    if os.name != "nt" or _mutex:
        return
    import ctypes
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)


def launcher_running() -> bool:
    """다른 런처가 켜져 있는지. 관리자 권한 런처의 뮤텍스는 일반 권한에서 열 수 없을 수 있다 (접근 거부 = 있음)."""
    if os.name != "nt":
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.OpenMutexW(0x00100000, False, MUTEX_NAME)             # SYNCHRONIZE
    if handle:
        k32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == 5                                 # ERROR_ACCESS_DENIED


def hand_over(path) -> bool:
    """런처가 이미 켜져 있으면 경로를 넘기고 True (호출한 쪽은 바로 끝낸다)."""
    if not launcher_running():
        return False
    try:
        write_request(path)
    except OSError:
        return False
    return True
