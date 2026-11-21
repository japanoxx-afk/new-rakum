"""전체화면 마우스 가두기.

cnc-ddraw 의 마우스 가두기는 창모드에서는 잘 되지만 전체화면(특히 듀얼 모니터)에서는 커서가
옆 화면으로 빠져나간다. 런처가 게임 창을 지켜보다가 게임이 앞에 있고 창이 모니터 하나를 꽉 채우면
(= 전체화면, Alt+Enter 로 바꾼 경우 포함) 커서를 그 모니터 안으로 가둔다.
게임이 뒤로 가면(Alt+Tab) 바로 풀어 준다. 창모드는 cnc-ddraw 에 맡긴다(Ctrl+Tab 해제가 그대로 동작).
"""
import os
import threading

GAME_EXE = "rhakmu.exe"


def is_fullscreen(window_rect, monitor_rect) -> bool:
    """창이 모니터를 다 덮으면 전체화면 (테두리 없는 창 포함)."""
    wl, wt, wr, wb = window_rect
    ml, mt, mr, mb = monitor_rect
    return wl <= ml and wt <= mt and wr >= mr and wb >= mb


def decide(enabled, foreground_is_game, window_rect, monitor_rect):
    """가둘 사각형(left, top, right, bottom) 또는 None(풀기)."""
    if not (enabled and foreground_is_game and window_rect and monitor_rect):
        return None
    if not is_fullscreen(window_rect, monitor_rect):
        return None
    return tuple(monitor_rect)


class _Win32:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.u.GetForegroundWindow.restype = wintypes.HWND
        self.u.MonitorFromWindow.restype = wintypes.HANDLE
        self.u.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        self.u.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        self.u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.u.ClipCursor.argtypes = (ctypes.POINTER(wintypes.RECT),)
        self.k.OpenProcess.restype = wintypes.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                      ctypes.POINTER(wintypes.DWORD))

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        self.MONITORINFO = MONITORINFO
        self._names = {}

    def foreground(self):
        """(창, 게임인가, 창 사각형, 모니터 사각형)."""
        hwnd = self.u.GetForegroundWindow()
        if not hwnd:
            return None, False, None, None
        pid = self.wt.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, self.ct.byref(pid))
        if self._exe(pid.value) != GAME_EXE:
            return hwnd, False, None, None
        r = self.wt.RECT()
        if not self.u.GetWindowRect(hwnd, self.ct.byref(r)):
            return hwnd, True, None, None
        mi = self.MONITORINFO()
        mi.cbSize = self.ct.sizeof(mi)
        mon = self.u.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
        if not mon or not self.u.GetMonitorInfoW(mon, self.ct.byref(mi)):
            return hwnd, True, None, None
        m = mi.rcMonitor
        return hwnd, True, (r.left, r.top, r.right, r.bottom), (m.left, m.top, m.right, m.bottom)

    def _exe(self, pid):
        if pid in self._names:
            return self._names[pid]
        name = ""
        h = self.k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                buf = self.ct.create_unicode_buffer(520)
                n = self.wt.DWORD(520)
                if self.k.QueryFullProcessImageNameW(h, 0, buf, self.ct.byref(n)):
                    name = os.path.basename(buf.value).lower()
            finally:
                self.k.CloseHandle(h)
        if len(self._names) > 256:
            self._names.clear()
        self._names[pid] = name
        return name

    def clip(self, rect):
        if rect is None:
            self.u.ClipCursor(None)
        else:
            r = self.wt.RECT(*rect)
            self.u.ClipCursor(self.ct.byref(r))

    def current_clip(self):
        r = self.wt.RECT()
        self.u.GetClipCursor(self.ct.byref(r))
        return (r.left, r.top, r.right, r.bottom)


class CursorGuard:
    """0.25초마다 확인. enabled 는 '마우스 가두기' 설정."""

    def __init__(self, enabled=True, win=None, interval=0.25):
        self.enabled = enabled
        self.interval = interval
        self.win = win
        self.clipped = None
        self._stop = threading.Event()
        self.thread = None

    def step(self):
        _, is_game, wrect, mrect = self.win.foreground()
        want = decide(self.enabled, is_game, wrect, mrect)
        if want is not None:
            # 다른 프로그램(또는 Windows 가 창 전환 때) 풀었으면 다시 건다
            if want != self.clipped or self.win.current_clip() != want:
                self.win.clip(want)
                self.clipped = want
        elif self.clipped is not None:
            self.win.clip(None)
            self.clipped = None

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.step()
            except Exception:
                pass

    def start(self):
        if os.name != "nt" or self.thread:
            return
        if self.win is None:
            self.win = _Win32()
        self.thread = threading.Thread(target=self._run, name="cursor-guard", daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        if self.clipped is not None and self.win:
            try:
                self.win.clip(None)
            except Exception:
                pass
            self.clipped = None
