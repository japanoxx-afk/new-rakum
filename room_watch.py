"""방 생성 알림: 서버의 방 목록(HTTP 11225 /rooms, server.py 0.9023~)을 지켜보다가 다른 사람이 방을 만들면
런처의 작업 표시줄 단추를 깜빡이게 한다.

서버는 요청한 PC의 주소와 방장 주소가 같으면 그 방에 mine 표시를 한다 (내가 만든 방은 알리지 않음).
/rooms 를 모르는 예전 서버는 어떤 경로든 전적 목록(list)을 돌려주므로 그것으로 구분한다.
"""
import json
import urllib.request

PORT = 11225
POLL_SECONDS = 5


def fetch_rooms(ip, timeout=3.0):
    """방 목록 [{id, title, owner, map, players, max, in_game, mine}]. 서버가 /rooms 를 모르거나 접속이 안 되면 None."""
    try:
        with urllib.request.urlopen(f"http://{ip}:{PORT}/rooms", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        return None
    return [room for room in data["rooms"] if isinstance(room, dict)]


class RoomWatcher:
    """방 목록을 받을 때마다 '새로 생긴 남의 방' 만 골라 준다."""

    def __init__(self):
        self._seen = set()

    @staticmethod
    def _key(room):
        return room.get("id"), room.get("title"), room.get("owner")

    def update(self, rooms):
        """rooms: fetch_rooms 결과 (None 이면 아무 일도 없음). 처음 보는, 내 것이 아니고 대전 중이 아닌 방 목록을 돌려준다."""
        if rooms is None:
            return []
        fresh = [room for room in rooms
                 if self._key(room) not in self._seen and not room.get("mine") and not room.get("in_game")]
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
