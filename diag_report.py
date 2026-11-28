"""진단 리포트 — 문제가 생기면 '진단 리포트 만들기' 한 번으로 원인 파악에 필요한 정보를 모은다.

런처 오류(게임 실행 중단 등)는 launcher-errors.log 에 쌓이고, 리포트에 그 최근 내용이 들어간다.
리포트에는 설치 폴더·PC 사양·게임 파일 상태·설정이 들어간다. 계정 비밀번호·토큰 같은 값은 넣지 않는다.
"""
from __future__ import annotations

import ctypes
import datetime
import hashlib
import os
import platform
import subprocess
import traceback
from pathlib import Path

ERROR_LOG = "launcher-errors.log"
SECRET_WORDS = ("pass", "token", "secret", "key")
MAX_ERROR_TAIL = 20000


def log_error(base_dir, where: str, exc: BaseException | None = None) -> None:
    """런처 오류를 launcher-errors.log 에 덧붙인다 (실패해도 게임 진행엔 영향 없음)."""
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else ""
        with open(Path(base_dir) / ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {where}\n{text}\n")
    except OSError:
        pass


def _read_text(path, limit=MAX_ERROR_TAIL, head=False) -> str:
    """파일의 끝(기본) 또는 앞부분 limit 바이트를 읽는다. 없으면 '(없음)'."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return "(없음)"
    part = data[:limit] if head else data[-limit:]
    return part.decode("utf-8", errors="replace")


def _user_registry_value(subkey: str, name: str) -> str:
    """HKCU 값 한 개 (없으면 '(없음)'). 게임 실행 설정처럼 사용자별 값을 본다."""
    if os.name != "nt":
        return "?"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return "(없음)"


def _memory_mb() -> str:
    if os.name != "nt":
        return "?"

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return f"전체 {m.ullTotalPhys // (1024 * 1024)} MB / 사용 중 {m.dwMemoryLoad}%"


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=10, text=True, encoding="cp949", errors="replace")
        return (out.stdout or out.stderr).strip() or "(출력 없음)"
    except (OSError, subprocess.SubprocessError) as e:
        return f"(실패: {e})"


def _gpu() -> str:
    if os.name != "nt":
        return "?"
    return _run(["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' / 드라이버 ' + $_.DriverVersion }"])


def _registry() -> str:
    if os.name != "nt":
        return "?"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\TriggerSoft\RhakMu",
                             0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
    except OSError as e:
        return f"(없음: {e})"
    rows = []
    i = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
        except OSError:
            break
        rows.append(f"  {name} = {value}")
        i += 1
    winreg.CloseKey(key)
    return "\n".join(rows) or "  (값 없음)"


def _game_section(game_dir) -> list[str]:
    import game_version
    import replay_memory
    lines = []
    g = Path(game_dir)
    lines.append(f"설치 폴더: {g} (존재: {g.is_dir()})")
    exe = g / "Rhakmu.exe"
    if exe.is_file():
        data = exe.read_bytes()
        lines.append(f"Rhakmu.exe: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}")
        try:
            lines.append(f"Rhakmu.exe 1.000d 여부: {game_version.is_1000d(data)}")
        except Exception as e:                       # 리포트는 어떤 상태에서도 만들어져야 한다
            lines.append(f"Rhakmu.exe 1.000d 여부: 확인 실패 ({e})")
        lines.append(f"읽기 전용: {not os.access(exe, os.W_OK)}")
    else:
        lines.append("Rhakmu.exe: 없음")
    try:
        pid = replay_memory.find_game_pid()
        lines.append(f"게임 실행 중: {'예 (pid %s)' % pid if pid else '아니오'}")
    except Exception as e:
        lines.append(f"게임 실행 중: 확인 실패 ({e})")
    try:
        entries = sorted(g.iterdir(), key=lambda p: p.name.lower())
        lines.append("설치 폴더 파일:")
        for p in entries[:200]:
            size = p.stat().st_size if p.is_file() else "<폴더>"
            lines.append(f"  {p.name}  {size}")
    except OSError as e:
        lines.append(f"설치 폴더 파일 목록 실패: {e}")
    ddraw_dll = g / "ddraw.dll"
    if ddraw_dll.is_file():
        digest = hashlib.sha256(ddraw_dll.read_bytes()).hexdigest()
        lines.append(f"ddraw.dll (cnc-ddraw): {ddraw_dll.stat().st_size} bytes, sha256 {digest[:16]}")
    # 앞부분 = 화면 설정 (renderer, windowed, vsync, maxfps, shader ...)
    ddraw_ini = g / "ddraw.ini"
    lines.append("ddraw.ini (앞 6000바이트):")
    lines.append(_read_text(ddraw_ini, 6000, head=True) if ddraw_ini.is_file() else "  (없음)")
    for name in ("RhakMU.ERR", "Launcher.LOG", "rkp2p.log"):
        lines.append(f"{name} (끝 3000바이트):")
        lines.append(_read_text(g / name, 3000))
    return lines


def build_report(base_dir, game_dir, version: str, cfg: dict | None = None, now=None) -> str:
    now = now or datetime.datetime.now()
    out = [f"라크무 진단 리포트 — 런처 {version}", f"작성: {now:%Y-%m-%d %H:%M:%S}", ""]
    out.append("[PC]")
    out.append(f"OS: {platform.platform()}")
    out.append(f"CPU: {platform.processor()} / 논리 코어 {os.cpu_count()}")
    out.append(f"메모리: {_memory_mb()}")
    out.append(f"그래픽: {_gpu()}")
    out.append(f"전원 설정: {_run(['powercfg', '/getactivescheme'])}" if os.name == "nt" else "전원 설정: ?")
    out.append("GPU 기본 설정 (이 게임 exe 별 지정): " + _user_registry_value(
        r"Software\Microsoft\DirectX\UserGpuPreferences", str(Path(game_dir) / "Rhakmu.exe")))
    out.append("Windows 게임 모드: " + _user_registry_value(r"Software\Microsoft\GameBar", "AutoGameModeEnabled"))
    out.append("")
    out.append("[게임]")
    try:
        out += _game_section(game_dir)
    except Exception as e:
        out.append(f"게임 폴더 확인 실패: {e}")
    out.append("")
    out.append("[레지스트리 HKLM\\SOFTWARE\\TriggerSoft\\RhakMu]")
    out.append(_registry())
    out.append("")
    out.append("[런처 설정 (비밀 값 제외)]")
    for k, v in sorted((cfg or {}).items()):
        if any(w in k.lower() for w in SECRET_WORDS):
            continue
        out.append(f"  {k} = {v}")
    out.append("")
    out.append("[최근 런처 오류 (launcher-errors.log)]")
    out.append(_read_text(Path(base_dir) / ERROR_LOG))
    return "\n".join(out) + "\n"


def write_report(base_dir, game_dir, version: str, cfg: dict | None = None, out_dir=None) -> Path:
    """리포트를 바탕화면(없으면 런처 폴더)에 저장하고 경로를 돌려준다."""
    now = datetime.datetime.now()
    text = build_report(base_dir, game_dir, version, cfg, now)
    folder = Path(out_dir) if out_dir else Path(os.path.join(os.path.expanduser("~"), "Desktop"))
    if not folder.is_dir():
        folder = Path(base_dir)
    path = folder / f"rhakmu-report-{now:%Y%m%d-%H%M%S}.txt"
    path.write_text(text, encoding="utf-8")
    return path
