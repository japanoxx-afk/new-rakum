"""방 생성 알림: 서버의 방 목록(HTTP 11225 /rooms, server.py 0.9023~)을 지켜보다가 다른 사람이 방을 만들면
런처의 작업 표시줄 단추를 깜빡이게 한다.

내가 만든 방은 알리지 않는다: 방장 이름이 이 PC의 게임 계정(레지스트리 LastUser — 게임이 로그인할 때 적어 둠)과 같으면 내 방.
계정을 모를 때만 서버의 mine 표시(요청한 PC의 주소 == 방장 주소)를 쓴다 — 같은 공유기를 쓰는 두 PC는 주소가 같아
v0.9105 처럼 mine 만 보면 서로의 방이 모두 '내 방' 이 되어 알림이 오지 않는다.
/rooms 를 모르는 예전 서버는 어떤 경로든 전적 목록(list)을 돌려주므로 그것으로 구분한다.
"""
import json
import urllib.request

PORT = 11225
POLL_SECONDS = 5


REGISTRY_KEY = r"SOFTWARE\TriggerSoft\RhakMu"


def fetch_status(ip, timeout=3.0):
    """(상태, 방 목록). 상태: "ok" | "old" (서버가 /rooms 를 모름 — 0.9023 미만) | "down" (접속 안 됨)."""
    try:
        with urllib.request.urlopen(f"http://{ip}:{PORT}/rooms", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return "down", None
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        return "old", None
    return "ok", [room for room in data["rooms"] if isinstance(room, dict)]


def fetch_rooms(ip, timeout=3.0):
    """방 목록 [{id, title, owner, map, players, max, in_game, mine}]. 서버가 /rooms 를 모르거나 접속이 안 되면 None."""
    return fetch_status(ip, timeout)[1]


def last_user(winreg=None):
    """이 PC에서 마지막으로 로그인한 게임 계정 (게임이 HKLM 32비트 키의 LastUser 에 적어 둠). 모르면 ""."""
    try:
        if winreg is None:
            import winreg
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, access) as key:
            value, _ = winreg.QueryValueEx(key, "LastUser")
    except (ImportError, OSError):
        return ""
    return value.strip() if isinstance(value, str) else ""


class RoomWatcher:
    """방 목록을 받을 때마다 '새로 생긴 남의 방' 만 골라 준다."""

    def __init__(self):
        self._seen = set()

    @staticmethod
    def _key(room):
        return room.get("id"), room.get("title"), room.get("owner")

    @staticmethod
    def _mine(room, account):
        if account:
            return str(room.get("owner") or "").strip().lower() == account.strip().lower()
        return bool(room.get("mine"))

    def update(self, rooms, account=""):
        """rooms: fetch_rooms 결과 (None 이면 아무 일도 없음), account: 이 PC의 게임 계정 (모르면 "").
        처음 보는, 내 것이 아니고 대전 중이 아닌 방 목록을 돌려준다."""
        if rooms is None:
            return []
        fresh = [room for room in rooms
                 if self._key(room) not in self._seen and not self._mine(room, account) and not room.get("in_game")]
        self._seen = {self._key(room) for room in rooms}        # 없어진 방은 잊는다 (같은 이름으로 다시 만들면 또 알림)
        return fresh


def describe(room):
    title = str(room.get("title") or "?")
    owner = str(room.get("owner") or "?")
    count = f" {room.get('players')}/{room.get('max')}" if room.get("players") and room.get("max") else ""
    return f"{title} (방장 {owner}{count})"


def flash_taskbar(window_id, count=8):
    """런처 창의 작업 표시줄 단추를 깜빡인다 (창이 앞으로 올 때까지 강조 유지). Windows 가 아니면 False."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError):
        return False

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    hwnd = user32.GetParent(window_id) or window_id        # tkinter 의 winfo_id 는 안쪽 창 — 바깥(틀) 창이 작업 표시줄 단추의 주인
    FLASHW_ALL, FLASHW_TIMERNOFG = 3, 12
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, count, 0)
    user32.FlashWindowEx(ctypes.byref(info))
    return True


def work_area():
    """작업 표시줄을 뺀 화면 영역 (left, top, right, bottom). 알 수 없으면 None."""
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):    # SPI_GETWORKAREA
            return None
        return rect.left, rect.top, rect.right, rect.bottom
    except (ImportError, AttributeError, OSError):
        return None


def toast_position(width, height, area, screen, margin=16):
    """알림 창을 화면 오른쪽 아래(작업 표시줄 위)에 둘 왼쪽 위 좌표. area: work_area() 결과 또는 None, screen: (너비, 높이)."""
    left, top, right, bottom = area if area else (0, 0, screen[0], screen[1] - 48)
    return max(left, right - width - margin), max(top, bottom - height - margin)


def keep_inactive(window_id):
    """알림 창이 뜰 때 입력 초점을 가져가지 않게 한다 (게임·다른 창에서 하던 일이 끊기지 않게). Windows 가 아니면 False."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError):
        return False
    GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
    for hwnd in (window_id, user32.GetParent(window_id)):
        if hwnd:
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    return True
