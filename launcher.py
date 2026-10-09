"""라크무 서버 런처 — 서버 관리 + 호스트 파일 + 반응속도 패치 + 디스플레이 설정 GUI.

단일 exe로 빌드하면 server.py가 내장된다.
  - 더블클릭: GUI 런처
  - 내부적으로 "서버 시작" 클릭 시 같은 exe를 --server 모드로 재실행
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import ipaddress
import tempfile
import time
import threading
import queue
import tkinter as tk
import sync_port_patch
import peer_address_patch
import panel_guard_patch
import viewport_patch
import command_cadence_trial
import command_cadence_installer
from release_notes import NOTES
from hosts_entries import replace_entries
from display_settings import WindowModeManager, RENDERERS
import launcher_update
from tkinter import ttk, messagebox

# server.py는 런타임 exec로 실행되므로 PyInstaller가 의존성을 자동 감지 못 한다.
# exe 빌드 시 함께 포함되도록 여기서 명시적으로 import 해 둔다.
import asyncio        # noqa: F401
import logging        # noqa: F401
import socket         # noqa: F401
import struct         # noqa: F401
import dataclasses    # noqa: F401
import pathlib        # noqa: F401
import typing         # noqa: F401

APP_VERSION = "0.9028"

# 라크무는 한게임 호스트로 접속한다 (hosts 파일로 우리 서버로 우회)
GAME_HOST = "rhakmugame.hangame.naver.com"
DEFAULT_DOMAINS = [GAME_HOST]
DEFAULT_IP = "127.0.0.1"
SERVER_PORT = 11223   # 서버 실행 여부 확인용 (로비 TCP)
SERVER_LOOPBACK = "127.0.0.1"
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
CONFIG_FILE = "launcher_config.json"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/japanoxx-afk/new-rakum/main/"
GITHUB_RAW_URL = GITHUB_RAW_BASE + "server.py"
VERSION_CHECK_URL = GITHUB_RAW_BASE + "version.json"
SERVER_SCRIPT = "server.py"
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\TriggerSoft\RhakMu"
GAME_EXE = "Launcher.exe"   # 라크무는 Launcher.exe -> Rhakmu.exe 구조
PATCH_EXE = "Rhakmu.exe"    # 레이턴시 패치 대상
DDRAW_INI = "ddraw.ini"
# 게임 버전은 런타임 글로벌로 계산돼 정적으로 못 읽으므로 Rhakmu.exe 크기로 식별
GAME_VERSIONS = {
    1069098: "1.000d",
    1065002: "1.000a",
}
RESOLUTIONS = [
    "0x0", "640x480", "800x600", "1024x768", "1280x720", "1280x960",
    "1600x900", "1920x1080", "2560x1440", "3440x1440", "3840x2160",
]
SHADERS = [
    ("선명하게 (Lanczos)", "Lanczos"),
    ("부드럽게 (Bicubic)", "Bicubic"),
    ("기본 (Bilinear)", "Bilinear"),
    ("도트 그대로 (Nearest)", "Nearest neighbor"),
]
SHADER_VALUES = {label: val for label, val in SHADERS}


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin():
    if is_admin():
        return
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = ""
    else:
        exe = sys.executable
        args = f'"{os.path.abspath(__file__)}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit()


# ── 라드민(26.x) DP8 바인딩 우선순위 자동 적용 ──────────────
# DirectPlay8은 P2P 세션에 "자기 로컬 IP"를 박아 상대에게 알린다. 하마치는 설치 시
# 자기 어댑터 우선순위(interface metric)를 물리 랜보다 높게 잡지만, 라드민은 그렇지
# 않아 DP8이 물리 랜(192.168.x)을 선택 → 상대가 라드민망 밖 IP로 접속 → 동기화 실패.
# 라드민 어댑터의 metric을 1(최우선)로 낮춰 DP8이 26.x를 자기 IP로 쓰게 강제한다.
def _run_ps(script):
    """PowerShell 스크립트를 창 없이 실행하고 (returncode, stdout+stderr) 반환."""
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, creationflags=flags, timeout=20,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def has_radmin_adapter():
    """26.x IPv4를 가진 어댑터가 있으면 그 IP를 반환, 없으면 None."""
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("26."):
                return ip
    except Exception:
        pass
    return None


def fix_radmin_priority():
    """라드민(26.x) 어댑터 metric을 1로 설정. (ok: bool, message: str) 반환.
    26.x 어댑터가 없으면 (True, '') — 조용히 건너뜀(자동 호출용)."""
    ip = has_radmin_adapter()
    if not ip:
        return True, ""
    if not is_admin():
        return False, "라드민 우선순위 적용에는 관리자 권한이 필요합니다."
    script = (
        "$a = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.IPAddress -like '26.*' } | Select-Object -First 1; "
        "if (-not $a) { Write-Output 'NO26'; exit 0 }; "
        "Set-NetIPInterface -InterfaceIndex $a.InterfaceIndex -InterfaceMetric 1; "
        "$n = (Get-NetAdapter -InterfaceIndex $a.InterfaceIndex).Name; "
        "Write-Output ('OK ' + $n + ' ' + $a.IPAddress)"
    )
    rc, out = _run_ps(script)
    out = out.strip()
    if rc == 0 and out.startswith("OK"):
        return True, f"라드민 어댑터 우선순위 적용 완료 ({out[3:].strip()})"
    if "NO26" in out:
        return True, ""
    return False, f"적용 실패: {out}"


def is_server_running(host="127.0.0.1", port=SERVER_PORT, timeout=0.6):
    """로컬에 라크무 서버가 떠 있는지(로비 TCP 포트 응답) 확인."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_game_version(game_dir):
    """Rhakmu.exe 크기로 게임 버전 식별."""
    exe = os.path.join(game_dir, PATCH_EXE)
    try:
        sz = os.path.getsize(exe)
    except OSError:
        return "게임 없음"
    return GAME_VERSIONS.get(sz, f"미확인({sz:,}B)")


def get_server_version():
    """실행할 server.py에서 SERVER_VERSION 을 읽어 표시용으로 반환."""
    for p in (os.path.join(get_resource_dir(), SERVER_SCRIPT),):
        try:
            with open(p, "r", encoding="utf-8") as f:
                m = re.search(r'SERVER_VERSION\s*=\s*"([^"]+)"', f.read())
                if m:
                    return m.group(1)
        except OSError:
            continue
    return "?"


def find_python():
    for candidate in [
        shutil.which("python"),
        shutil.which("python3"),
        r"C:\Users\seo\AppData\Local\Programs\Python\Python314\python.exe",
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def load_config(base_dir):
    # Import legacy settings, but prefer the version/folder-independent copy.
    cfg = {}
    for path in (os.path.join(base_dir, CONFIG_FILE), config_path(base_dir)):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError):
            pass
    return cfg


def config_path(base_dir):
    root = os.environ.get('LOCALAPPDATA')
    return os.path.join(root, 'RhakMu', CONFIG_FILE) if root else os.path.join(base_dir, CONFIG_FILE)


def save_config(base_dir, cfg):
    path = config_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


# ═══════════════════════════════════════════════════════
#  자동 업데이트
# ═══════════════════════════════════════════════════════

def check_for_update():
    import urllib.request
    try:
        req = urllib.request.Request(VERSION_CHECK_URL + '?check=' + str(__import__('time').time_ns()), headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        latest = data.get("launcher_version", APP_VERSION)
        url = data.get("launcher_url", "")
        size = int(data.get("launcher_size", 0))
        if launcher_update.version_key(latest) > launcher_update.version_key(APP_VERSION):
            return latest, url, size
    except Exception:
        pass
    return None, None, 0


def do_self_update(download_url, expected_size=0):
    if not getattr(sys, 'frozen', False):
        return False, '개발 모드에서는 자동 업데이트를 사용할 수 없습니다.'
    try:
        match = re.search(r'RhakMuLauncher_v([0-9.]+)\.exe$', download_url)
        if not match:
            raise ValueError('올바르지 않은 업데이트 주소입니다.')
        launcher_update.install(download_url, expected_size, sys.executable, match.group(1))
        return True, ''
    except Exception as e:
        return False, f'업데이트 실패: {e}\n현재 런처는 유지됩니다.'




# ═══════════════════════════════════════════════════════
#  서버 모드 (--server)
# ═══════════════════════════════════════════════════════

def run_server_mode():
    base = get_base_dir()
    os.chdir(base)
    # Windowed PyInstaller executables have no standard streams.
    sys.stdout = open(os.path.join(base, 'server-console.log'), 'a', encoding='utf-8', buffering=1)
    sys.stderr = sys.stdout
    sys.stdin = open(os.devnull, 'r')

    # A release carries its server; stale external scripts must not override it.
    script = os.path.join(get_resource_dir(), SERVER_SCRIPT)

    if not os.path.isfile(script):
        print(f"오류: {SERVER_SCRIPT}를 찾을 수 없습니다.")
        raise FileNotFoundError(script)

    with open(script, "r", encoding="utf-8") as f:
        code = f.read()

    exec(compile(code, script, "exec"), {
        "__name__": "__main__",
        "__file__": os.path.join(base, SERVER_SCRIPT),
    })


# ═══════════════════════════════════════════════════════
#  반응속도(레이턴시) 패치  —  Rhakmu.exe 1바이트
# ═══════════════════════════════════════════════════════

class LatencyPatch:
    """lockstep 명령 지연(Game_Multi)을 줄여 클릭 반응을 빠르게 한다.
    바이트 시그니처 66 C7 40 48 ?? 00 E8 (mov word [eax+0x48], imm ; call) 3곳 중
    가운데(Game_Multi)의 imm 1바이트만 바꾼다. 빌드 무관, 백업 자동."""

    def __init__(self, game_dir):
        self.exe = os.path.join(game_dir, PATCH_EXE)

    @property
    def available(self):
        return os.path.isfile(self.exe)

    def _sites(self, data):
        sites = []
        n = len(data)
        i = 0
        while i < n - 7:
            if (data[i] == 0x66 and data[i+1] == 0xC7 and data[i+2] == 0x40
                    and data[i+3] == 0x48 and data[i+5] == 0x00 and data[i+6] == 0xE8):
                sites.append(i)
            i += 1
        return sorted(sites)

    def current(self):
        """현재 Game_Multi 지연 턴 수 (없으면 None)."""
        if not self.available:
            return None
        data = open(self.exe, "rb").read()
        sites = self._sites(data)
        if len(sites) != 3:
            return None
        return data[sites[1] + 4]

    def apply(self, value):
        if not self.available:
            return False, f"{PATCH_EXE}를 찾을 수 없습니다."
        if not (1 <= value <= 4):
            return False, "지연값은 1~4 사이여야 합니다."
        data = bytearray(open(self.exe, "rb").read())
        sites = self._sites(data)
        if len(sites) != 3:
            return False, ("지연값 코드를 찾지 못했습니다 (3곳 기대).\n"
                           "클라이언트 버전이 다를 수 있습니다.")
        off = sites[1] + 4
        cur = data[off]
        if cur == value:
            return True, f"이미 적용됨: 지연 {value}턴."
        import time
        bak = self.exe + ".bak_latency_" + time.strftime("%Y%m%d_%H%M%S")
        try:
            with open(bak, "wb") as f:
                f.write(data)
            data[off] = value
            with open(self.exe, "wb") as f:
                f.write(data)
        except PermissionError:
            return False, "관리자 권한이 필요합니다. 런처를 관리자로 실행하세요."
        except OSError as e:
            return False, str(e)
        return True, f"적용 완료: 대전 지연 {cur} → {value}턴."


# ═══════════════════════════════════════════════════════
#  서버 / 호스트 / 디스플레이 매니저
# ═══════════════════════════════════════════════════════

class ServerManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.proc = None

    def start(self):
        if self.proc and self.proc.poll() is None:
            return False, "서버가 이미 실행 중입니다."
        if is_server_running():
            return False, "다른 서버가 이미 실행 중입니다. 기존 서버를 종료한 뒤 시작하세요."

        args = [sys.executable, '--server'] if getattr(sys, 'frozen', False) else [sys.executable, os.path.abspath(__file__), '--server']
        try:
            self.proc = subprocess.Popen(
                args, cwd=self.base_dir,
                creationflags=0x08000000 if os.name == 'nt' else 0,
                env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            return False, f'서버 시작 실패: {e}'
        return True, "서버 시작 중 — 런처에서 상태와 로그를 확인하세요."

    def stop(self):
        if not self.proc or self.proc.poll() is not None:
            return self.stop_previous()
        # One-file PyInstaller has a bootloader parent and a worker child.
        # Terminate only our process tree, not unrelated Python/game servers.
        if os.name == 'nt':
            result = subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=0x08000000, timeout=10)
            if result.returncode and self.proc.poll() is None:
                return False, '서버 종료 실패: ' + result.stdout.decode(errors='replace')
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return False, "서버 종료가 지연되고 있습니다. 잠시 후 다시 종료하세요."
        self.proc = None
        return True, "서버를 종료했습니다."

    def restart(self):
        if self.running or is_server_running():
            ok, msg = self.stop()
            if not ok:
                return False, msg
        return self.start()

    def stop_previous(self):
        # Recover servers left by an earlier launcher in this same folder.
        # Do not terminate an arbitrary listener or unrelated Python process.
        folder = str(pathlib.Path(self.base_dir).resolve()).replace("'", "''")
        source = os.path.abspath(__file__).replace("'", "''")
        script = """
        $ErrorActionPreference='Stop'
        $owned=@(Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -match '(?:^|\\s)--server(?:\\s|$)' -and (
                ($_.Name -match '^RhakMuLauncher(?:_v[0-9.]+)?\\.exe$' -and
                 [IO.Path]::GetDirectoryName($_.ExecutablePath) -eq 'FOLDER') -or
                ($_.Name -match '^python(?:w)?\\.exe$' -and $_.CommandLine.Contains('SOURCE')))
        })
        if (-not $owned.Count) { throw '이 런처가 관리하는 서버를 찾지 못했습니다. 다른 서버 프로그램을 확인하세요.' }
        $ids=@($owned.ProcessId)
        foreach($p in $owned) {
            if ($p.ParentProcessId -notin $ids) {
                & taskkill.exe /PID $p.ProcessId /T /F | Out-Null
                if ($LASTEXITCODE -ne 0) { throw '이전 서버 종료 실패' }
            }
        }
        """.replace('FOLDER', folder).replace('SOURCE', source)
        rc, out = _run_ps(script)
        if rc:
            return False, out.strip()
        self.proc = None
        return True, '이전 런처 서버를 종료했습니다.'

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None


class HostsManager:
    @staticmethod
    def read_current_ip(domains):
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    for d in domains:
                        if d in line:
                            return line.split()[0]
        except OSError:
            pass
        return DEFAULT_IP

    @staticmethod
    def apply_ip(ip, domains):
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = ""
        content = replace_entries(content, ip, domains)

        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def has_domain(domain):
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("#") or not s:
                        continue
                    if domain in s.split()[1:]:
                        return True
        except OSError:
            pass
        return False

    @staticmethod
    def ensure_domains(ip, domains):
        """hosts에 없는 도메인만 ip로 추가한다. 이미 있는 항목(사용자가 지정한 IP)은 건드리지 않음.
        실제로 추가한 도메인 목록을 반환."""
        missing = [d for d in domains if not HostsManager.has_domain(d)]
        if not missing:
            return []
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = ""
        content = content.rstrip("\n") + "\n"
        for d in missing:
            content += f"{ip} {d}\n"
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return missing

    @staticmethod
    def set_game_host(ip):
        """rhakmugame.hangame.naver.com 한 줄만 ip로 설정/추가. 다른 줄은 절대 건드리지 않음."""
        HostsManager.apply_ip(ip, [GAME_HOST])

    @staticmethod
    def read_raw():
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            return f"(hosts 파일을 읽을 수 없습니다: {e})"

    @staticmethod
    def open_hosts_file():
        subprocess.Popen(["notepad.exe", HOSTS_PATH])


# ═══════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"라크무 런처 v{APP_VERSION}")
        self.geometry("720x820")
        self.resizable(True, True)
        self.minsize(620, 680)

        self.base_dir = get_base_dir()
        self.server = ServerManager(self.base_dir)
        self.cfg = load_config(self.base_dir)
        self.radmin_session = None
        self.domains = list(self.cfg.get("domains", DEFAULT_DOMAINS))

        game_dir = self.cfg.get("game_dir", DEFAULT_GAME_DIR)
        self.winmode = WindowModeManager(game_dir)
        self.latency = LatencyPatch(game_dir)
        self.gamedir_var = tk.StringVar(value=game_dir)
        launch_path = ttk.LabelFrame(self, text='게임 실행 경로 (설치 폴더 또는 Launcher.exe)', padding=6)
        launch_path.pack(fill='x', padx=8, pady=4)
        ttk.Entry(launch_path, textvariable=self.gamedir_var).pack(side='left', fill='x', expand=True)
        ttk.Button(launch_path, text='찾기', command=self._on_browse_game).pack(side='left', padx=4)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self._build_server_tab(notebook)
        self._build_client_tab(notebook)
        self._build_history_tab(notebook)
        self._build_settings_tab(notebook)
        self._build_capture_tab(notebook)
        self.protocol("WM_DELETE_WINDOW", self._close_launcher)

        self.info_var = tk.StringVar()
        ttk.Label(self, textvariable=self.info_var, anchor="center",
                  font=("맑은 고딕", 9, "bold")).pack(fill="x", padx=8, pady=(0, 2))

        launch_frame = ttk.Frame(self)
        launch_frame.pack(fill="x", padx=8, pady=(0, 10))
        ttk.Button(
            launch_frame, text="🎮 싱글플레이", command=self._on_single_play, width=18,
        ).pack(side="left", expand=True, padx=4)
        ttk.Button(
            launch_frame, text="🌐 멀티플레이", command=self._on_multi_play, width=18,
        ).pack(side="left", expand=True, padx=4)

        self._refresh_info_bar()

        self._refresh_patch_status()
        self._update_status()

    def _build_capture_tab(self, notebook):
        self.capture_process = None
        self.capture_dir = None
        frame = ttk.Frame(notebook, padding=16)
        notebook.add(frame, text="통신 진단")
        ttk.Label(frame, text="게임 시작 동기화 기록", font=("맑은 고딕", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="양쪽 PC에서 기록 시작 → 기록 중 표시 확인 → 게임 시작\n"
                  "로비로 돌아오면 기록 종료를 누르세요. 120초 후 자동 종료됩니다.\n"
                  "하마치 성공 기록도 같은 방법으로 남겨 비교할 수 있습니다.",
                  wraplength=420).pack(anchor="w", pady=10)
        self.capture_label = tk.StringVar(value="Radmin 실패")
        ttk.Combobox(frame, textvariable=self.capture_label, state="readonly",
                     values=("Radmin 실패", "Hamachi 성공", "기타"), width=22).pack(anchor="w")
        ttk.Label(frame, text="상대 VPN IP (선택)").pack(anchor="w", pady=(10, 2))
        self.capture_peer = tk.StringVar()
        ttk.Entry(frame, textvariable=self.capture_peer).pack(anchor="w")
        ttk.Label(frame, text="브로드캐스트를 포함해 모든 어댑터의 패킷 앞 256바이트를 기록합니다.\n"
                  "다른 앱의 통신·IP·로그인 정보가 포함될 수 있습니다. 파일은 PC에만 저장됩니다.",
                  wraplength=420).pack(anchor="w", pady=10)
        self.capture_start = ttk.Button(frame, text="기록 시작 (120초)", command=self._start_capture)
        self.capture_start.pack(anchor="w", pady=4)
        self.capture_stop = ttk.Button(frame, text="기록 종료 및 저장", command=self._stop_capture, state="disabled")
        self.capture_stop.pack(anchor="w", pady=4)
        ttk.Button(frame, text="저장 폴더 열기", command=self._open_capture).pack(anchor="w", pady=4)
        self.capture_status = tk.StringVar(value="대기 중 — 관리자 권한이 필요합니다.")
        ttk.Label(frame, textvariable=self.capture_status, wraplength=420).pack(anchor="w", pady=10)
        ttk.Label(frame, text="동기화 포트 수정 (1.000d, 대전 검증 전)\n"
                  "게임 종료 후 양쪽 PC에 적용하세요. 문제가 생기면 원복할 수 있습니다.",
                  wraplength=420).pack(anchor="w", pady=4)
        row = ttk.Frame(frame)
        row.pack(anchor="w")
        ttk.Button(row, text="포트 수정 적용", command=lambda: self._sync_port_patch(True)).pack(side="left")
        ttk.Button(row, text="포트 수정 원복", command=lambda: self._sync_port_patch(False)).pack(side="left", padx=6)
        ttk.Button(frame, text='왕건 방식 주소 응답 패치 적용', command=lambda: self._restore_peer_address(True)).pack(anchor='w', pady=4)
        ttk.Button(frame, text='상대 주소 복구 패치 원복', command=self._restore_peer_address).pack(anchor='w', pady=4)

    def _restore_peer_address(self, enabled=False):
        rc, out = _run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
        if rc != 0 or 'RUNNING' in out:
            messagebox.showwarning('상대 주소 패치', '게임을 완전히 종료한 후 원복하세요.')
            return
        try:
            path = os.path.join(self.cfg.get('game_dir', DEFAULT_GAME_DIR), PATCH_EXE)
            if enabled:
                peer_address_patch.state(pathlib.Path(path).read_bytes())
                sync_port_patch.apply(path, True)
            else:
                panel_guard_patch.apply(path, False)
            result = peer_address_patch.apply(path, enabled)
            verified = peer_address_patch.state(pathlib.Path(path).read_bytes())
            if verified != enabled:
                raise RuntimeError('패치 적용 확인 실패')
            messagebox.showinfo('상대 주소 패치', result + '\n파일 재검증 완료: ' + path)
        except Exception as e:
            messagebox.showerror('상대 주소 패치', str(e))

    def _sync_port_patch(self, enabled):
        rc, out = _run_ps("if (Get-Process Rhakmu -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
        if rc != 0 or 'RUNNING' in out:
            messagebox.showwarning("동기화 포트", "게임을 완전히 종료한 후 다시 적용하세요.")
            return
        try:
            result = sync_port_patch.apply(os.path.join(self.cfg.get('game_dir', DEFAULT_GAME_DIR), PATCH_EXE), enabled)
            messagebox.showinfo("동기화 포트", result)
        except Exception as e:
            messagebox.showerror("동기화 포트", str(e))

    def _start_capture(self):
        if self.capture_process is not None:
            return
        if not is_admin():
            messagebox.showwarning("통신 진단", "런처를 관리자 권한으로 실행해 주세요.")
            return
        import datetime
        import tempfile
        root = os.path.join(os.environ.get("LOCALAPPDATA", self.base_dir), "RhakMu", "diagnostics")
        try:
            os.makedirs(root, exist_ok=True)
            self.capture_dir = tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=root)
            with open(os.path.join(self.capture_dir, "session.json"), "w", encoding="utf-8") as f:
                json.dump({"launcher_version": APP_VERSION, "case": self.capture_label.get(),
                           "peer_ip": self.capture_peer.get().strip(), "started": datetime.datetime.now().isoformat(),
                           "lobby_ip": HostsManager.read_current_ip([GAME_HOST])}, f, ensure_ascii=False, indent=2)
            try:
                game_data = pathlib.Path(self.cfg.get('game_dir', DEFAULT_GAME_DIR), PATCH_EXE).read_bytes()
                patch_status = {'peer_address': peer_address_patch.state(game_data), 'sync_port': sync_port_patch.state(game_data),
                                'peer_reply_8814': game_data[0xeb420:0xeb420+len(peer_address_patch.CODE)] == peer_address_patch.CODE,
                                'game_path': str(pathlib.Path(self.cfg.get('game_dir', DEFAULT_GAME_DIR), PATCH_EXE)),
                                'radmin_mode_selected': self.radmin_only.get()}
            except (ValueError, OSError) as e:
                patch_status = {'error': str(e)}
            pathlib.Path(self.capture_dir, 'game-patches.json').write_text(json.dumps(patch_status), encoding='utf-8')
            self.capture_process = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 os.path.join(get_resource_dir(), "launcher_capture.ps1"),
                 "-OutputDir", self.capture_dir, "-ServerDir", self.base_dir],
                creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror("통신 진단", str(e))
            return
        self.capture_start.config(state="disabled")
        self.capture_stop.config(state="normal")
        self.capture_status.set("기록 준비 중…")
        self.after(500, self._poll_capture)

    def _stop_capture(self):
        if self.capture_process is not None:
            pathlib.Path(self.capture_dir, "stop").touch()
            self.capture_stop.config(state="disabled")
            self.capture_status.set("기록 종료 및 저장 중…")

    def _poll_capture(self):
        try:
            status = pathlib.Path(self.capture_dir, "status.txt").read_text(encoding="utf-8-sig").strip()
            if status.startswith("CAPTURING:"):
                self.capture_status.set("기록 중 — 지금 게임을 시작하세요. " + status.split(":", 1)[1])
            elif status.startswith("Saving"):
                self.capture_status.set("패킷 파일 변환·저장 중…")
        except OSError:
            pass
        code = self.capture_process.poll()
        if code is None:
            self.after(500, self._poll_capture)
            return
        self.capture_process = None
        self.capture_start.config(state="normal")
        self.capture_stop.config(state="disabled")
        self.capture_status.set(("저장 완료: " if code == 0 else "기록 오류 — error.txt / capture.log 확인: ") + self.capture_dir)

    def _open_capture(self):
        if self.capture_dir:
            os.startfile(self.capture_dir)
        else:
            messagebox.showinfo("통신 진단", "먼저 기록을 시작해 주세요.")

    def _close_launcher(self):
        if self.capture_process is not None:
            self._stop_capture()
            messagebox.showinfo("통신 진단", "기록 저장 중입니다. 저장이 끝난 뒤 런처를 닫아 주세요.")
            return
        if self.server.running:
            if not messagebox.askyesno('서버 종료', '런처를 닫으면 실행 중인 서버도 종료됩니다. 닫으시겠습니까?'):
                return
            ok, msg = self.server.stop()
            if not ok:
                messagebox.showerror('서버', msg)
                return
        self.destroy()

    # ── 서버 탭 ──
    def _build_server_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="  호스트 · 접속  ")
        canvas = tk.Canvas(tab, highlightthickness=0)
        scroll = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        frame = ttk.Frame(canvas, padding=12)
        window = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        self.connection_parent = frame

        ttk.Label(frame, text="라크무 서버 관리", font=("맑은 고딕", 12, "bold")).pack(
            anchor="w", pady=(0, 4)
        )
        ttk.Label(frame, text=f"런처 v{APP_VERSION}   |   서버 v{get_server_version()}",
                  foreground="gray").pack(anchor="w", pady=(0, 10))

        self.status_var = tk.StringVar(value="서버 상태: 꺼짐")
        ttk.Label(frame, textvariable=self.status_var, font=("맑은 고딕", 10)).pack(
            anchor="w", pady=(0, 12)
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")
        self.btn_start = ttk.Button(btn_frame, text="서버 시작", command=self._on_start, width=14)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_restart = ttk.Button(btn_frame, text="서버 재시작", command=self._on_restart, width=14)
        self.btn_restart.pack(side="left", padx=(0, 8))
        self.btn_stop = ttk.Button(btn_frame, text="서버 종료", command=self._on_stop, width=14)
        self.btn_stop.pack(side="left")
        ttk.Label(frame, text='별도 창 없이 실행됩니다. 런처를 닫으면 서버도 종료됩니다.', foreground='gray').pack(anchor='w', pady=6)
        self.server_log = tk.Text(frame, height=4, wrap='word', state='disabled')
        self.server_log.pack(fill='both', expand=True)

        update_frame = ttk.Frame(frame)
        update_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(update_frame, text="통합 업데이트 (런처·서버)", command=self._on_check_launcher_update, width=25).pack(side="left")
        ttk.Button(update_frame, text="패치노트", command=self._show_patch_notes, width=10).pack(side="left", padx=6)
        self.update_status_var = tk.StringVar()
        ttk.Label(update_frame, textvariable=self.update_status_var, foreground="gray").pack(side="left", padx=(8, 0))

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=16)

        if getattr(sys, "frozen", False):
            ttk.Label(frame, text="서버 내장 모드 (단일 exe)", foreground="green").pack(anchor="w")
        else:
            script = os.path.join(self.base_dir, SERVER_SCRIPT)
            if os.path.isfile(script):
                ttk.Label(frame, text=f"{SERVER_SCRIPT} 감지됨", foreground="green").pack(anchor="w")
            else:
                ttk.Label(frame, text=f"※ {SERVER_SCRIPT}를 같은 폴더에 넣어주세요.", foreground="gray").pack(anchor="w")

    def _on_start(self):
        ok, msg = self.server.start()
        self._update_status()
        if not ok:
            messagebox.showwarning("서버", msg)

    def _on_stop(self):
        ok, msg = self.server.stop()
        self._update_status()
        if not ok:
            messagebox.showinfo("서버", msg)

    def _on_restart(self):
        ok, msg = self.server.restart()
        self._update_status()
        if not ok:
            messagebox.showwarning("서버", msg)

    def _on_update(self):
        return self._on_check_launcher_update()

    def _show_patch_notes(self):
        dlg = tk.Toplevel(self)
        dlg.title('패치노트')
        dlg.geometry('620x520')
        from tkinter.scrolledtext import ScrolledText
        text = ScrolledText(dlg, wrap='word', padx=12, pady=12)
        text.pack(fill='both', expand=True)
        text.insert('1.0', NOTES)
        text.configure(state='disabled')

    def _on_check_launcher_update(self):
        if getattr(self, '_update_pending', False):
            return
        import urllib.request
        self.update_status_var.set("버전 확인 중...")
        self.update()
        try:
            with urllib.request.urlopen(VERSION_CHECK_URL + '?check=' + str(__import__('time').time_ns()), timeout=6) as r:
                data = json.loads(r.read())
        except Exception as e:
            self.update_status_var.set("확인 실패")
            messagebox.showerror("런처 업데이트", f"버전 정보를 가져오지 못했습니다.\n{e}")
            return
        latest = str(data.get("launcher_version", ""))
        url = data.get("launcher_url", "")
        size = int(data.get("launcher_size", 0))
        self.update_status_var.set("")
        if not latest:
            messagebox.showinfo("런처 업데이트", "버전 정보를 읽을 수 없습니다.")
            return
        if launcher_update.version_key(latest) <= launcher_update.version_key(APP_VERSION):
            messagebox.showinfo("런처 업데이트", f"이미 최신 버전입니다.\n현재 v{APP_VERSION}")
            return
        if not messagebox.askyesno("새 버전 있음",
                f"새 런처 버전이 있습니다.\n\n현재  v{APP_VERSION}\n최신  v{latest}\n\n관리 서버를 종료하고 업데이트하시겠습니까?"):
            return
        rc, out = _run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { 'RUNNING' }")
        if rc or 'RUNNING' in out:
            messagebox.showinfo('런처 업데이트', '게임을 종료한 뒤 업데이트하세요. 게임 중에는 서버를 종료하지 않습니다.')
            return
        if self.server.running or is_server_running():
            ok, err = self.server.stop()
            if not ok:
                messagebox.showerror('서버 종료 실패', err)
                return
        self.update_status_var.set('다운로드 및 새 런처 실행 검사 중…')
        self._update_pending = True
        results = queue.Queue()
        threading.Thread(target=lambda: results.put(do_self_update(url, size)), daemon=True).start()
        def finish():
            try:
                ok, err = results.get_nowait()
            except queue.Empty:
                self.after(200, finish)
                return
            self.update_status_var.set('')
            self._update_pending = False
            if ok:
                self.destroy()
            else:
                messagebox.showerror('런처 업데이트 실패', err)
        self.after(200, finish)

    def _update_status(self):
        if self.server.running:
            ready = is_server_running(timeout=0.05)
            self.status_var.set("서버 상태: 실행 중 ●" if ready else "서버 상태: 시작 중…")
            self.btn_start.state(["disabled"])
        else:
            code = self.server.proc.poll() if self.server.proc else None
            self.status_var.set(f"서버 종료 (코드 {code}) — 아래 로그 확인" if code is not None else "서버 상태: 꺼짐 ○")
            self.btn_start.state(["!disabled"])
        self.btn_stop.state(['!disabled' if self.server.running else 'disabled'])
        self.btn_restart.state(['!disabled' if self.server.running else 'disabled'])
        try:
            with open(os.path.join(self.base_dir, 'server-console.log'), 'rb') as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 16000))
                text = f.read().decode('utf-8', errors='replace')
            if text != getattr(self, '_last_server_log', None):
                self._last_server_log = text
                self.server_log.config(state='normal')
                self.server_log.delete('1.0', tk.END)
                self.server_log.insert('1.0', text)
                self.server_log.see(tk.END)
                self.server_log.config(state='disabled')
        except OSError:
            pass
        if getattr(self, '_status_timer', None):
            self.after_cancel(self._status_timer)
        self._status_timer = self.after(2000, self._update_status)

    # ── 클라 탭 ──
    def _build_client_tab(self, notebook):
        frame = ttk.LabelFrame(self.connection_parent, text='서버 접속 설정', padding=8)
        frame.pack(fill='x', pady=8)

        ttk.Label(frame, text="접속 정보 (hosts)", font=("맑은 고딕", 12, "bold")).pack(anchor="w", pady=(0, 4))
        self.cur_ip_var = tk.StringVar()
        ip_row = ttk.Frame(frame)
        ip_row.pack(fill='x', pady=6)
        ttk.Label(ip_row, text='서버 VPN IP: ').pack(side='left')
        self.saved_ip_var = tk.StringVar(value=self.cfg.get('last_server_ip', ''))
        ip_entry = ttk.Entry(ip_row, textvariable=self.saved_ip_var, width=20)
        ip_entry.pack(side='left')
        ip_entry.bind('<Return>', lambda e: self._save_server_ip())
        ip_entry.bind('<FocusOut>', self._commit_ip_input)
        ttk.Button(ip_row, text='저장·적용', command=self._save_server_ip).pack(side='left', padx=6)
        ttk.Label(frame, text='IP 입력 후 Enter 또는 다른 항목 클릭 시 hosts에 반영됩니다.', foreground='gray').pack(anchor='w')
        self.radmin_only = tk.BooleanVar(value=self.cfg.get('radmin_only', True))
        ttk.Checkbutton(frame, text="라드민 전용 모드 (게임 IP 고정 + 하마치 일시 중지)",
                        variable=self.radmin_only).pack(anchor="w")
        ttk.Label(frame, text="양쪽 PC에서 사용하세요. 게임 종료 후 하마치를 복구합니다.").pack(anchor="w")
        ttk.Button(frame, text="게임 IP / 하마치 상태 복구", command=lambda: self._radmin_session_start(restore=True)).pack(anchor="w")
        self.radmin_status = tk.StringVar(value="라드민 전용 모드 대기")
        ttk.Label(frame, textvariable=self.radmin_status, wraplength=420).pack(anchor="w")
        ttk.Label(frame, textvariable=self.cur_ip_var, foreground="gray").pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="새로고침", command=self._refresh_hosts_view, width=10).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="hosts 폴더 열기", command=self._on_open_hosts).pack(side="left")
        ttk.Label(frame,
                  text="※ 접속 주소는 아래 '싱글/멀티플레이' 버튼이 자동 설정합니다.\n"
                       "   rhakmugame.hangame.naver.com 줄만 바뀌고 나머지는 보존됩니다.",
                  foreground="gray").pack(anchor="w", pady=(8, 0))

        self._refresh_hosts_view()

    def _refresh_hosts_view(self):
        if not hasattr(self, "cur_ip_var"):
            return
        ip = HostsManager.read_current_ip([GAME_HOST])
        self.cur_ip_var.set(f"{GAME_HOST}  →  {ip}")

    def _on_open_hosts(self):
        os.startfile(os.path.dirname(HOSTS_PATH))

    def _commit_ip_input(self, event=None):
        value = self.saved_ip_var.get().strip()
        if not value or value == getattr(self, '_last_applied_ip', None):
            return
        self._save_server_ip(notify=False)

    def _radmin_session_start(self, restore=False):
        if self.radmin_session is not None and self.radmin_session.poll() is None:
            messagebox.showinfo("라드민 전용", "게임 세션이 진행 중입니다. 게임 종료 후 자동 복구됩니다.")
            return
        if not is_admin():
            messagebox.showwarning("라드민 전용", "관리자 권한으로 런처를 실행하세요.")
            return
        root = os.path.join(os.environ.get('LOCALAPPDATA', self.base_dir), 'RhakMu', 'radmin-session')
        try:
            os.makedirs(root, exist_ok=True)
            if not restore:
                rc, out = _run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
                if rc != 0 or 'RUNNING' in out:
                    raise RuntimeError('게임을 완전히 종료한 뒤 다시 실행하세요.')
                game_exe = os.path.join(self.cfg.get('game_dir', DEFAULT_GAME_DIR), PATCH_EXE)
                # Validate both sites before changing either; preserve user patches.
                game_data = pathlib.Path(game_exe).read_bytes()
                peer_address_patch.state(game_data)
                sync_port_patch.state(game_data)
                sync_port_patch.apply(game_exe, True)
                peer_address_patch.apply(game_exe, True)
            helper = os.path.join(root, 'radmin_session.ps1')
            shutil.copyfile(os.path.join(get_resource_dir(), 'radmin_session.ps1'), helper)
            shutil.copyfile(os.path.join(get_resource_dir(), 'radmin_address.ps1'), os.path.join(root, 'radmin_address.ps1'))
            args = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', helper,
                    '-StateDir', root, '-GameDir', self.cfg.get('game_dir', DEFAULT_GAME_DIR)]
            if restore:
                args.append('-Restore')
            self.radmin_session = subprocess.Popen(args, creationflags=0x08000000)
            self.radmin_status.set('네트워크 상태 확인 중…')
            self.after(1000, lambda: self._poll_radmin_session(root))
        except Exception as e:
            messagebox.showerror('라드민 전용', str(e))

    def _poll_radmin_session(self, root):
        try:
            text = pathlib.Path(root, 'status.txt').read_text(encoding='utf-8-sig').strip()
            self.radmin_status.set({'STARTING':'게임 IP를 라드민으로 고정 — 게임 시작 중',
                                   'PLAYING':'라드민 전용 게임 실행 중',
                                   'RESTORED':'게임 IP / 하마치 원래 상태 복구 완료'}.get(text, text))
        except OSError:
            pass
        if self.radmin_session.poll() is None:
            self.after(1000, lambda: self._poll_radmin_session(root))
        elif self.radmin_session.returncode:
            messagebox.showerror('라드민 전용', self.radmin_status.get())

    def _set_host_and_launch(self, ip, multiplayer=False):
        """rhakmugame 호스트를 ip로 설정(다른 줄 보존) 후 게임 실행."""
        try:
            self._prepare_game_launch()
        except Exception as e:
            messagebox.showerror('게임 실행 중단', str(e))
            return
        if getattr(self, '_launch_pending', False):
            return
        if multiplayer and self.radmin_only.get() and not ip.startswith('26.'):
            messagebox.showwarning('라드민 전용', '서버의 라드민 26.x 주소를 입력하세요.')
            return
        ok, msg = self.server.restart()
        if not ok:
            messagebox.showerror('서버 준비 실패', msg)
            return
        self._launch_pending = True
        self.info_var.set('서버 시작 완료를 기다리고 있습니다…')
        deadline = time.monotonic() + 20
        def ready():
            if is_server_running(timeout=0.05):
                self._launch_pending = False
                self._launch_prepared_game(ip, multiplayer)
            elif not self.server.running or time.monotonic() >= deadline:
                self._launch_pending = False
                messagebox.showerror('서버 준비 실패', '서버가 준비되지 않아 게임 실행을 중단했습니다. 서버 로그를 확인하세요.')
            else:
                self.after(200, ready)
        self.after(200, ready)

    def _launch_prepared_game(self, ip, multiplayer=False):
        game_dir = self.cfg.get("game_dir", DEFAULT_GAME_DIR)
        exe = os.path.join(game_dir, GAME_EXE)
        if not os.path.isfile(exe):
            messagebox.showerror("오류",
                f"{GAME_EXE}를 찾을 수 없습니다.\n({exe})\n\n설정 탭에서 게임 경로를 확인하세요.")
            return
        try:
            HostsManager.set_game_host(ip)
        except PermissionError:
            messagebox.showwarning("권한 오류",
                "hosts 파일 수정에 관리자 권한이 필요합니다.\n런처를 관리자 권한으로 실행해 주세요.")
            return
        except OSError as e:
            messagebox.showerror("오류", str(e))
            return
        if hasattr(self, "cur_ip_var"):
            self._refresh_hosts_view()
        try:
            if multiplayer and self.radmin_only.get():
                if ip != '127.0.0.1' and not ip.startswith('26.'):
                    messagebox.showwarning('라드민 전용', '서버의 라드민 26.x 주소를 입력하세요.')
                    return
                self.cfg['radmin_only'] = True
                save_config(self.base_dir, self.cfg)
                self._radmin_session_start()
                return
            subprocess.Popen([exe], cwd=game_dir)
        except OSError as e:
            messagebox.showerror("실행 오류", str(e))

    def _prepare_game_launch(self):
        path = pathlib.Path(self.gamedir_var.get().strip().strip('"')).expanduser()
        if path.is_file():
            if path.name.lower() != GAME_EXE.lower():
                raise ValueError('게임 설치 폴더 또는 Launcher.exe를 선택하세요.')
            path = path.parent
        path = path.resolve()
        if not (path / GAME_EXE).is_file() or not (path / PATCH_EXE).is_file():
            raise ValueError('해당 경로에 Launcher.exe와 Rhakmu.exe가 있어야 합니다.')
        rc, out = _run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
        if rc != 0 or 'RUNNING' in out:
            raise RuntimeError('게임을 완전히 종료한 뒤 실행하세요. 실행 중에는 패치하지 않습니다.')
        exe = path / PATCH_EXE
        data = exe.read_bytes()
        peer_address_patch.state(data)
        sync_port_patch.state(data)
        panel_guard_patch.state(data)
        sync_port_patch.apply(exe, True)
        peer_address_patch.apply(exe, True)
        panel_guard_patch.apply(exe, True)
        viewport_patch.apply(exe, self.cfg.get('viewport_1280', True))
        cadence_enabled = self.cfg.get('command_cadence_99ms', exe.read_bytes()[0xd7b97] == 3)
        if cadence_enabled:
            ok, msg = LatencyPatch(str(path)).apply(4)
            if not ok: raise RuntimeError(msg)
        command_cadence_installer.apply(exe, cadence_enabled)
        self.cfg['command_cadence_99ms'] = bool(cadence_enabled)
        verified = exe.read_bytes()
        if not panel_guard_patch.state(verified) or not sync_port_patch.state(verified) or verified[0xeb420:0xeb420+len(peer_address_patch.CODE)] != peer_address_patch.CODE:
            raise RuntimeError('왕건 방식 주소 응답 패치 검증 실패. 게임을 실행하지 않았습니다.')
        cfg = {**self.cfg, 'game_dir': str(path)}
        save_config(self.base_dir, cfg)
        self.cfg = cfg
        self.gamedir_var.set(str(path))
        self.winmode.game_dir = str(path)
        self.latency = LatencyPatch(str(path))
        mode='1280×720' if self.cfg.get('viewport_1280',True) else '원본'
        self.info_var.set(f'주소 응답·패널 보호 확인 완료 / 내부 해상도 {mode} — 게임 실행')

    def _on_viewport_apply(self):
        old=dict(self.cfg)
        self.cfg['viewport_1280']=bool(self.viewport_var.get())
        try:
            self._prepare_game_launch()
        except Exception as exc:
            self.cfg=old
            messagebox.showerror('내부 해상도 적용 실패',str(exc));return
        messagebox.showinfo('내부 해상도',
            '1280×720 적용 완료. 다음 전투 진입 시 자동 전환됩니다.' if self.cfg['viewport_1280'] else
            '원본 내부 해상도로 복원했습니다. 다음 게임 실행부터 적용됩니다.')

    def _on_game_play(self):
        # Use the saved multiplayer destination when available; otherwise local.
        if self.saved_ip_var.get().strip() or is_server_running():
            self._on_multi_play()
        else:
            self._on_single_play()

    def _on_cadence_apply(self):
        enabled = bool(self.cadence_var.get())
        if enabled and not messagebox.askyesno('명령 응답 개선',
                '멀티플레이 안정성은 검증 중입니다. 상대방도 같은 설정이 필요합니다.\n'
                '4턴을 유지하고 전송 간격을 약 99ms로 변경할까요?'):
            self.cadence_var.set(self.cfg.get('command_cadence_99ms', False)); return
        old = dict(self.cfg)
        self.cfg['command_cadence_99ms'] = enabled
        try:
            self._prepare_game_launch()
        except Exception as error:
            self.cfg = old
            messagebox.showerror('명령 응답 개선', str(error)); return
        messagebox.showinfo('명령 응답 개선', '적용 완료. 멀티플레이는 양쪽 모두 같은 설정을 사용하세요.')

    def _on_single_play(self):
        self._set_host_and_launch("127.0.0.1")

    def _on_multi_play(self):
        # 라드민(26.x)이 있으면 DP8이 26.x로 바인딩하도록 어댑터 우선순위를 먼저 적용.
        ok, msg = fix_radmin_priority()
        if not ok:
            messagebox.showwarning("라드민 우선순위",
                msg + "\n\n런처를 관리자 권한으로 다시 실행하면 자동 적용됩니다.\n"
                "(이대로 진행해도 대전은 시도됩니다.)")
        elif msg:
            self._set_status(msg) if hasattr(self, "_set_status") else None
        # A running local server must NEVER override the selected VPN address.
        # Reuse the saved address without another dialog.
        if self.saved_ip_var.get().strip():
            if self._save_server_ip(notify=False):
                self._set_host_and_launch(self.cfg['last_server_ip'], multiplayer=True)
        else:
            self._ask_server_ip_and_launch()

    def _save_server_ip(self, notify=True):
        try:
            ip = str(ipaddress.IPv4Address(self.saved_ip_var.get().strip()))
            if ipaddress.IPv4Address(ip).is_unspecified or ipaddress.IPv4Address(ip).is_multicast:
                raise ValueError('접속 가능한 서버 IPv4 주소를 입력하세요.')
            updated = {**self.cfg, 'last_server_ip': ip, 'radmin_only': self.radmin_only.get()}
            HostsManager.set_game_host(ip)
            save_config(self.base_dir, updated)
            self.cfg = updated
            self.saved_ip_var.set(ip)
            self._last_applied_ip = ip
            self._refresh_hosts_view()
        except (ValueError, OSError) as e:
            messagebox.showerror('IP 저장 실패', str(e))
            return False
        if notify:
            messagebox.showinfo('IP 저장', 'IP를 저장하고 hosts의 게임 접속 주소에 반영했습니다.')
        return True

    def _ask_server_ip_and_launch(self):
        dlg = tk.Toplevel(self)
        dlg.title("멀티플레이 접속")
        dlg.resizable(False, False)
        dlg.transient(self)
        # 런처 창 근처(중앙)에 띄운다
        self.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw = self.winfo_width()
        dlg.geometry(f"360x140+{px + max(0,(pw-360)//2)}+{py + 100}")
        dlg.grab_set()
        ttk.Label(dlg, text="접속할 서버(호스트) IP를 입력하세요:").pack(anchor="w", padx=14, pady=(14, 4))
        last = self.cfg.get("last_server_ip", HostsManager.read_current_ip([GAME_HOST]))
        if last == "127.0.0.1":
            last = ""
        var = tk.StringVar(value=last)
        entry = ttk.Entry(dlg, textvariable=var, width=30)
        entry.pack(padx=14)
        entry.focus_set()

        def go(event=None):
            ip = var.get().strip()
            if not ip:
                messagebox.showwarning("입력 오류", "서버 IP를 입력하세요.", parent=dlg)
                return
            self.saved_ip_var.set(ip)
            if not self._save_server_ip(notify=False):
                return
            dlg.destroy()
            self._set_host_and_launch(ip, multiplayer=True)

        entry.bind("<Return>", go)
        ttk.Button(dlg, text="실행", command=go, width=12).pack(pady=12)

    # ── 전적 탭 ──
    def _build_history_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="  전적  ")

        ttk.Label(frame, text="대전 기록", font=("맑은 고딕", 12, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(frame, text="서버가 게임 시작 시 자동 기록합니다 (서버를 켜둔 PC 기준).",
                  foreground="gray").pack(anchor="w", pady=(0, 8))

        cols = ("time", "map", "players", "result")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        tree.heading("time", text="시간")
        tree.heading("map", text="맵")
        tree.heading("players", text="플레이어")
        tree.heading("result", text="결과")
        tree.column("time", width=130, anchor="w")
        tree.column("map", width=120, anchor="w")
        tree.column("players", width=140, anchor="w")
        tree.column("result", width=110, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.history_tree = tree

        btnbar = ttk.Frame(frame)
        btnbar.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(btnbar, text="새로고침", command=self._refresh_history, width=10).pack(pady=(0, 4))
        ttk.Button(btnbar, text="랭킹 보기", command=self._show_ranking, width=10).pack(pady=(0, 4))

        self._refresh_history()

    def _server_ip(self):
        # 전적/랭킹 조회용 서버 IP = 현재 hosts의 게임 호스트 IP (없으면 마지막 입력/기본)
        return (HostsManager.read_current_ip([GAME_HOST])
                or self.cfg.get("last_server_ip", "") or DEFAULT_IP)

    def _fetch_json(self, path):
        """서버 HTTP(11225)에서 전적/랭킹을 받아온다. 실패 시 로컬 파일 폴백."""
        import urllib.request
        ip = self._server_ip()
        try:
            with urllib.request.urlopen(f"http://{ip}:11225{path}", timeout=3) as r:
                return json.loads(r.read())
        except Exception:
            # 로컬 폴백 (이 PC가 서버인 경우)
            if path.startswith("/ranking"):
                return None
            try:
                with open(os.path.join(self.base_dir, "matches.json"), "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return []

    @staticmethod
    def _wl_text(results):
        if not results:
            return "-"
        out = []
        for a, v in results.items():
            if isinstance(v, dict):
                wl = v.get("wl")
                mark = {"win": "승", "lose": "패", "draw": "무"}.get(wl, "?")
            else:
                mark = "승" if str(v).startswith("win") else "패"
            out.append(f"{a}:{mark}")
        return ", ".join(out)

    def _refresh_history(self):
        tree = getattr(self, "history_tree", None)
        if tree is None:
            return
        for it in tree.get_children():
            tree.delete(it)
        matches = self._fetch_json("/matches.json") or []
        for rec in reversed(matches):  # 최신순
            players = ", ".join(rec.get("players", []))
            mp = rec.get("map", "").replace("Data\\Maps\\", "").replace(".rkm", "")
            tree.insert("", "end", values=(rec.get("time", ""), mp, players,
                                           self._wl_text(rec.get("results", {}))))

    def _show_ranking(self):
        rank = self._fetch_json("/ranking")
        if rank is None:
            messagebox.showinfo("랭킹", "서버에 연결할 수 없습니다.\n(서버가 켜져 있고 IP가 맞는지 확인)")
            return
        if not rank:
            messagebox.showinfo("랭킹", "아직 집계된 전적이 없습니다.")
            return
        rows = sorted(rank.items(), key=lambda kv: (-kv[1].get("win", 0), kv[1].get("lose", 0)))
        lines = [f"{a:12} {v.get('win',0)}승 {v.get('lose',0)}패 {v.get('draw',0)}무" for a, v in rows]
        messagebox.showinfo("랭킹 (승순)", "\n".join(lines))

    # ── 설정 탭 ──
    def _build_settings_tab(self, notebook):
        page = ttk.Frame(notebook)
        notebook.add(page, text="  설정  ")
        canvas = tk.Canvas(page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(canvas, padding=16)
        item = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))

        # ── 게임 경로 ──
        path_frame = ttk.LabelFrame(frame, text="게임 설치 경로", padding=10)
        path_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(path_frame, textvariable=self.gamedir_var, width=44).pack(side="left", padx=(0, 6))
        ttk.Button(path_frame, text="찾기", command=self._on_browse_game, width=6).pack(side="left")

        # ── 반응속도 (레이턴시) ──
        lat_frame = ttk.LabelFrame(frame, text="명령 지연 (멀티플레이 권장: 4턴)", padding=12)
        lat_frame.pack(fill="x", pady=(0, 10))
        cur = self.latency.current()
        cur_txt = f"현재 지연: {cur}턴" if cur is not None else "현재 지연: (확인 불가)"
        self.lat_status_var = tk.StringVar(value=cur_txt)
        ttk.Label(lat_frame, textvariable=self.lat_status_var).pack(anchor="w", pady=(0, 6))
        lat_btns = ttk.Frame(lat_frame)
        lat_btns.pack(fill="x")
        ttk.Button(lat_btns, text="빠르게 (1턴)", command=lambda: self._on_latency(1), width=11).pack(side="left", padx=(0, 4))
        ttk.Button(lat_btns, text="균형 (2턴)", command=lambda: self._on_latency(2), width=11).pack(side="left", padx=(0, 4))
        ttk.Button(lat_btns, text="안정 (3턴)", command=lambda: self._on_latency(3), width=11).pack(side="left", padx=(0, 4))
        ttk.Button(lat_btns, text="원래대로 (4턴)", command=lambda: self._on_latency(4), width=13).pack(side="left")
        ttk.Label(lat_frame,
                  text="멀티플레이는 안정성이 확인된 4턴 권장. 1~3턴은 실험값이며 정지가 늘 수 있습니다.\n"
                       "멀티는 함께하는 모든 PC가 같은 값이어야 합니다.  ※ 게임을 끈 상태에서 적용.",
                  foreground="gray").pack(anchor="w", pady=(6, 0))

        # ── 라드민 네트워크 최적화 ──
        try:
            cadence_current = pathlib.Path(self.latency.exe).read_bytes()[0xd7b97] == 3
        except OSError:
            cadence_current = False
        self.cadence_var = tk.BooleanVar(value=self.cfg.get('command_cadence_99ms', cadence_current))
        ttk.Checkbutton(lat_frame, text='명령 응답 개선: 약 99ms 전송 / 4턴 유지 (멀티 검증 중)',
                        variable=self.cadence_var).pack(anchor='w', pady=(8, 0))
        ttk.Button(lat_frame, text='전송 간격 적용 / 원복', command=self._on_cadence_apply).pack(anchor='w', pady=4)
        ttk.Label(lat_frame, text='상대방도 같은 설정 필수. 끄고 적용하면 기존 간격으로 복원됩니다.',
                  foreground='gray').pack(anchor='w')
        radmin_ip = has_radmin_adapter()
        rad_frame = ttk.LabelFrame(frame, text="라드민 멀티 최적화 (동기화 실패 해결)", padding=12)
        rad_frame.pack(fill="x", pady=(0, 10))
        if radmin_ip:
            rad_txt = f"라드민 어댑터 감지됨 ({radmin_ip}). 멀티플레이 시 자동 적용됩니다."
        else:
            rad_txt = "라드민(26.x) 어댑터가 감지되지 않았습니다. 라드민 VPN을 켜세요."
        self.rad_status_var = tk.StringVar(value=rad_txt)
        ttk.Label(rad_frame, textvariable=self.rad_status_var, foreground="gray").pack(anchor="w", pady=(0, 6))
        ttk.Button(rad_frame, text="지금 적용", command=self._on_fix_radmin, width=14).pack(anchor="w")
        ttk.Label(rad_frame,
                  text="라드민일 때 게임(DP8)이 잘못된 랜카드 IP로 접속해 동기화가 실패합니다.\n"
                       "라드민 어댑터를 최우선으로 지정해 해결합니다.  ※ 대전하는 두 PC 모두 적용.",
                  foreground="gray").pack(anchor="w", pady=(6, 0))

        # ── 창모드 ──
        mode_frame = ttk.LabelFrame(frame, text="디스플레이 모드", padding=12)
        mode_frame.pack(fill="x", pady=(0, 10))
        self.viewport_var=tk.BooleanVar(value=self.cfg.get('viewport_1280',True))
        ttk.Checkbutton(mode_frame,text='내부 해상도 1280×720 (전투 시야 확장)',
                        variable=self.viewport_var).pack(anchor='w')
        ttk.Button(mode_frame,text='내부 해상도 적용 / 해제',command=self._on_viewport_apply).pack(anchor='w',pady=4)
        ttk.Label(mode_frame,text='기본 켜짐 · 게임 실행 전 자동 적용 · 해제 시 원본 복원\n'
                  '메뉴·로비는 1024×768 유지. 장시간/멀티플레이 안정성은 추가 검증 중입니다.',
                  foreground='gray',wraplength=510).pack(anchor='w',pady=4)
        try:
            settings = self.winmode.read_settings()
        except (OSError, UnicodeError) as exc:
            settings = WindowModeManager('').read_settings()
            ttk.Label(mode_frame, text=f'설정 읽기 실패: {exc}', foreground='red', wraplength=500).pack()
        self.windowed_var = tk.BooleanVar(value=settings["windowed"])
        ttk.Checkbutton(mode_frame, text="창모드로 실행 (Alt+Enter 토글)",
                        variable=self.windowed_var).pack(anchor="w", pady=(0, 6))
        self.maintas_var = tk.BooleanVar(value=settings.get("maintas", False))
        ttk.Checkbutton(mode_frame, text="원본 비율 유지 (해제하면 화면 채우기)",
                        variable=self.maintas_var).pack(anchor="w", pady=(0, 10))
        res_row = ttk.Frame(mode_frame)
        res_row.pack(fill="x", pady=(0, 4))
        ttk.Label(res_row, text="출력 크기:").pack(side="left")
        current_res = f"{settings['width']}x{settings['height']}"
        self.res_var = tk.StringVar(value=current_res)
        ttk.Combobox(res_row, textvariable=self.res_var, values=RESOLUTIONS, width=14).pack(side="left", padx=(6, 0))
        ttk.Label(mode_frame, text='0x0 = 게임이 요청한 원본 크기. 위 값은 화면 확대 크기입니다.\n'
                  '실제 지도 시야는 위 내부 해상도 옵션으로 변경합니다. 1920×1080 내부 해상도는 미지원입니다.',
                  foreground='gray', wraplength=510).pack(anchor='w', pady=4)
        render_row = ttk.Frame(mode_frame)
        render_row.pack(fill='x')
        ttk.Label(render_row, text='렌더러:').pack(side='left')
        self.renderer_var = tk.StringVar(value=settings.get('renderer', 'auto'))
        ttk.Combobox(render_row, textvariable=self.renderer_var, values=RENDERERS,
                     state='readonly', width=14).pack(side='left', padx=6)
        self.confine_var = tk.BooleanVar(value=settings.get('confine', True))
        ttk.Checkbutton(mode_frame, text='마우스 가두기 (cnc-ddraw 설정)',
                        variable=self.confine_var).pack(anchor='w')

        shader_frame = ttk.LabelFrame(frame, text="업스케일 셰이더 (화질)", padding=12)
        shader_frame.pack(fill="x", pady=(0, 10))
        current_shader = settings.get("shader", "")
        shader_label = current_shader
        for label, val in SHADERS:
            if val == current_shader:
                shader_label = label
                break
        self.shader_var = tk.StringVar(value=shader_label)
        ttk.Combobox(shader_frame, textvariable=self.shader_var,
                     values=[label for label, _ in SHADERS], width=30,
                     state="readonly").pack(anchor="w", pady=(0, 6))

        ttk.Button(frame, text="디스플레이 설정 적용", command=self._on_apply_winmode, width=20).pack(anchor="w", pady=(4, 0))
        ttk.Button(frame, text="표시 지연 완화 (4턴 유지)", command=self._on_response_profile).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, text="수직동기화 끄기 + 모니터 주사율 + Bilinear 필터. 화질/화면 찢어짐 차이가 있을 수 있습니다.\n"
                  "명령 턴·게임 속도·네트워크 프로토콜은 변경하지 않습니다. 효과는 PC에 따라 다릅니다.",
                  foreground='gray').pack(anchor='w')

        if not self.winmode.available:
            ttk.Label(frame, text="※ ddraw.ini를 찾을 수 없습니다. 게임 경로를 확인하세요.",
                      foreground="red").pack(anchor="w", pady=(8, 0))

    def _on_fix_radmin(self):
        ip = has_radmin_adapter()
        if not ip:
            messagebox.showinfo("라드민 최적화",
                "라드민(26.x) 어댑터가 감지되지 않았습니다.\n라드민 VPN을 먼저 실행하세요.")
            return
        if not is_admin():
            if messagebox.askyesno("관리자 권한 필요",
                    "라드민 우선순위 적용에는 관리자 권한이 필요합니다.\n"
                    "관리자 권한으로 런처를 다시 실행할까요?"):
                run_as_admin()
            return
        ok, msg = fix_radmin_priority()
        if ok and msg:
            self.rad_status_var.set(msg)
            messagebox.showinfo("라드민 최적화", msg + "\n\n라드민과 게임을 재시작한 뒤 대전하세요.")
        elif ok:
            messagebox.showinfo("라드민 최적화", "라드민 어댑터가 없어 건너뛰었습니다.")
        else:
            messagebox.showwarning("라드민 최적화", msg)

    def _refresh_patch_status(self):
        cur = self.latency.current()
        self.lat_status_var.set(f"현재 지연: {cur}턴" if cur is not None else "현재 지연: (확인 불가)")
        self._refresh_info_bar()

    def _refresh_info_bar(self):
        if not hasattr(self, "info_var"):
            return
        game_dir = self.cfg.get("game_dir", DEFAULT_GAME_DIR)
        gv = get_game_version(game_dir)
        lat = self.latency.current()
        latmap = {1: "매우 빠름", 2: "빠름", 3: "보통", 4: "기본"}
        latstr = f"{lat}턴 · {latmap.get(lat, '?')}" if lat is not None else "확인 불가"
        self.info_var.set(f"게임 버전: {gv}     |     반응속도: {latstr}")

    def _on_browse_game(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="라크무 설치 폴더 선택", initialdir=self.gamedir_var.get())
        if d:
            self.gamedir_var.set(d)
            self.winmode.game_dir = d
            self.latency = LatencyPatch(d)
            self.cfg["game_dir"] = d
            save_config(self.base_dir, self.cfg)
            self._refresh_patch_status()

    def _on_latency(self, value):
        if value != 4 and self.cfg.get('command_cadence_99ms', self.cadence_var.get()):
            messagebox.showwarning('명령 지연', '99ms 명령 응답 개선은 4턴 전용입니다. 먼저 전송 간격을 원복하세요.'); return
        if self.latency.current() is None and not self.latency.available:
            messagebox.showerror("오류", f"{PATCH_EXE}를 찾을 수 없습니다.\n설정 탭에서 게임 경로를 확인하세요.")
            return
        ok, msg = self.latency.apply(value)
        if ok:
            self._refresh_patch_status()
            messagebox.showinfo("반응속도", msg + "\n\n게임을 실행해 확인하세요.")
        else:
            messagebox.showerror("반응속도", msg)

    def _on_response_profile(self):
        rc,out=_run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
        if rc!=0 or 'RUNNING' in out:
            messagebox.showwarning('게임 실행 중','게임을 종료한 뒤 적용하세요.')
            return
        game_dir=self.gamedir_var.get().strip().strip('"')
        if os.path.isfile(game_dir):game_dir=os.path.dirname(game_dir)
        if LatencyPatch(game_dir).current()!=4:
            messagebox.showwarning('4턴 확인','먼저 명령 지연을 원래대로 (4턴) 적용하세요. 표시 설정은 변경하지 않았습니다.')
            return
        manager=WindowModeManager(game_dir)
        settings=manager.read_settings()
        ok,msg=manager.apply_settings(settings['windowed'],settings['width'],settings['height'],
            shader='Bilinear',maintas=settings['maintas'],renderer='direct3d9',
            confine=settings['confine'],low_latency=True)
        if ok:
            self.shader_var.set('기본 (Bilinear)')
            self.renderer_var.set('direct3d9')
            messagebox.showinfo('표시 지연 완화',msg+'\n4턴 명령 지연은 유지됩니다. 실제 응답 개선량은 아직 미측정입니다.')
        else:messagebox.showerror('설정 실패',msg)

    def _on_apply_winmode(self):
        rc, out = _run_ps("if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { Write-Output 'RUNNING' }")
        if rc != 0 or 'RUNNING' in out:
            messagebox.showwarning('게임 실행 중', '게임을 종료한 뒤 출력 설정을 변경하세요.')
            return
        game_dir = self.gamedir_var.get().strip()
        if os.path.isfile(game_dir) and os.path.basename(game_dir).lower() == GAME_EXE.lower():
            game_dir = os.path.dirname(game_dir)
        if game_dir != self.winmode.game_dir:
            self.winmode.game_dir = game_dir
            self.cfg["game_dir"] = game_dir
            save_config(self.base_dir, self.cfg)

        res = self.res_var.get().strip()
        try:
            w, h = res.split("x")
            width, height = int(w), int(h)
        except (ValueError, AttributeError):
            messagebox.showwarning("입력 오류", "해상도 형식: 800x600")
            return

        shader_label = self.shader_var.get()
        shader_val = SHADER_VALUES.get(shader_label, shader_label)
        ok, msg = self.winmode.apply_settings(
            self.windowed_var.get(), width, height,
            shader=shader_val, maintas=self.maintas_var.get(),
            renderer=self.renderer_var.get(), confine=self.confine_var.get(),
        )
        if ok:
            messagebox.showinfo("설정", msg)
        else:
            messagebox.showerror("오류", msg)


# ═══════════════════════════════════════════════════════
#  엔트리포인트
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    if '--update-probe' in sys.argv:
        if viewport_patch.manifest().get('version')!=10:
            raise RuntimeError('고해상도 패치 데이터 누락')
        result_path = sys.argv[sys.argv.index('--update-probe') + 1]
        probe_app = App()
        probe_app.withdraw()
        probe_app.update_idletasks()
        probe_app.destroy()
        pathlib.Path(result_path).write_text(json.dumps({'version': APP_VERSION}), encoding='utf-8')
        sys.exit(0)
    if "--server" in sys.argv:
        run_server_mode()
    else:
        run_as_admin()

        latest, url, size = check_for_update()
        if latest and url:
            _root = tk.Tk()
            _root.withdraw()
            do_update = messagebox.askyesno("업데이트 알림",
                f"새 버전이 있습니다!\n\n현재: v{APP_VERSION}  →  최신: v{latest}\n\n지금 업데이트하시겠습니까?")
            _root.destroy()
            if do_update:
                ok, err = do_self_update(url, size)
                if ok:
                    sys.exit()
                else:
                    _r = tk.Tk(); _r.withdraw()
                    messagebox.showerror("업데이트 실패", err)
                    _r.destroy()

        app = App()
        if getattr(sys, 'frozen', False):
            try:
                launcher_update.make_shortcut(sys.executable)
            except Exception as e:
                messagebox.showwarning('바로가기', f'고정 바로가기를 만들지 못했습니다: {e}')
        app.mainloop()
