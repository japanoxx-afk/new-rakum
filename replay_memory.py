"""Rhakmu.exe 1.000d 게임 메모리 배치 (리플레이 기록용, 읽기만 함).

분석 근거 (원본 실행 파일):
  유닛 표   0x775A38 + 번호*0x138 (번호 1..0x6A5)
            +2  건물 분류(0 = 일반 유닛; 게임의 드래그·같은 종류 선택이 0 인 것만 고름)
            +6  현재 명령 (0x1xxx = 죽는 중)     +8  체력 (int16)
            +0xE 종류                          +0x10 소유 플레이어
            +0x12/+0x14 월드 좌표(px, 칸 = 32px)  +0x2B 건물·금광 안
            +0x4C 생산 진행(float)             +0x50 생산 중인 유닛 번호 (건물, 정보 창 0x4558E0)
  플레이어  0x7F7908 + p*0x11E0 (RhakMU.ERR 기록 0x440199)
            +0 인구 최대, +2 인구 현재 (상단 '%d/%d', 0x46444B)
            +5 종족, +6 참가 표시, +8 계정 이름
            +0x864, +0x868, +0x870, +0x86C 상단 자원 4칸 (0x464216 ...; 치트 0x404ACC)
            +0x1F8 / +0x39C 종류별 카운트 210칸, +0x880/+0x890, +0x50/+0x52, +0x540/+0x544 (결과 화면 0x41B499)
  맵 파일   0x6E10F6 (문자열)      경기 시간(초) 0x6E669C
  내 번호   0xB412CC               유닛 이름 0x5038EC + 종류*0x80 (정보 창 0x4587EE)
  종류 정보 [0x4FCD88 + 종류*0x1C] -> +0x40 == 1 이면 일꾼, [0x4FE474 + 종류*0x14] -> +2 최대 체력
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

UNITS, UNIT_SIZE, UNIT_COUNT = 0x775A38, 0x138, 0x6A6
PLAYERS, PLAYER_SIZE, PLAYER_COUNT = 0x7F7908, 0x11E0, 8
MAP_NAME, PLAY_SECONDS, LOCAL_PLAYER = 0x6E10F6, 0x6E669C, 0xB412CC
UNIT_NAMES, NAME_SIZE, TYPE_COUNT = 0x5038EC, 0x80, 0xD2
TYPE_INFO, TYPE_INFO_STRIDE = 0x4FCD88, 0x1C
TYPE_STATS, TYPE_STATS_STRIDE = 0x4FE474, 0x14
RACES = ("무휼", "아렌", "마르두크")
RESOURCE_NAMES = ("금", "물", "자원3", "자원4")   # 상단 표시 순서

F_BUILDING, F_INSIDE, F_IN_PRODUCTION = 1, 2, 4


def cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("cp949", "replace")


@dataclass
class Unit:
    id: int
    type: int
    owner: int
    x: int
    y: int
    hp: int
    flags: int
    order: int
    producing: int = 0          # 건물: 만드는 유닛 번호
    progress: float = 0.0

    def row(self):
        return [self.id, self.type, self.owner, self.x, self.y, self.hp, self.flags]


@dataclass
class Player:
    index: int
    name: str
    race: int
    active: int
    resources: list = field(default_factory=list)     # RESOURCE_NAMES 순서
    pop: tuple = (0, 0)                                # (현재, 최대)
    counters: list = field(default_factory=list)      # 결과 화면 값들 (원본 그대로)


def parse_units(raw: bytes) -> list[Unit]:
    """유닛 표 원본(0x6A6*0x138) -> 살아 있는 유닛."""
    out, producing = [], {}
    for i in range(1, UNIT_COUNT):
        o = i * UNIT_SIZE
        hp = struct.unpack_from("<h", raw, o + 8)[0]
        typ = struct.unpack_from("<h", raw, o + 0xE)[0]
        if hp <= 0 or not 0 < typ < TYPE_COUNT:
            continue
        building = struct.unpack_from("<H", raw, o + 2)[0]
        order = struct.unpack_from("<H", raw, o + 6)[0]
        if not building and order & 0xF000 == 0x1000:          # 죽는 중
            continue
        owner = raw[o + 0x10]
        x, y = struct.unpack_from("<hh", raw, o + 0x12)
        flags = (F_BUILDING if building else 0) | (F_INSIDE if raw[o + 0x2B] else 0)
        u = Unit(i, typ, owner, x, y, hp, flags, order)
        if building:
            prod = struct.unpack_from("<h", raw, o + 0x50)[0]
            if 0 < prod < UNIT_COUNT:
                u.producing = prod
                u.progress = struct.unpack_from("<f", raw, o + 0x4C)[0]
                producing[prod] = i
        out.append(u)
    for u in out:
        if u.id in producing:
            u.flags |= F_IN_PRODUCTION
    return out


def parse_player(index: int, raw: bytes) -> Player:
    w = lambda o: struct.unpack_from("<h", raw, o)[0]
    d = lambda o: struct.unpack_from("<i", raw, o)[0]
    arr = lambda o, n: sum(struct.unpack_from(f"<{n}h", raw, o))
    counters = [arr(0x1F8, 0xD2), arr(0x39C, 0xD2), d(0x880), d(0x890), w(0x50), w(0x52), w(0x540), arr(0x544, 0xC8)]
    return Player(index, cstr(raw[8:40]), raw[5], raw[6],
                  [d(0x864), d(0x868), d(0x870), d(0x86C)], (w(2), w(0)), counters)


class ProcessMemory:
    """실행 중인 Rhakmu.exe 의 메모리를 읽는다 (Windows)."""

    def __init__(self, pid: int):
        import ctypes
        from ctypes import wintypes
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k.OpenProcess.restype = wintypes.HANDLE
        self._k.ReadProcessMemory.argtypes = (wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
                                              ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
        self._ct = ctypes
        self.pid = pid
        self.handle = self._k.OpenProcess(0x0410, False, pid)      # VM_READ | QUERY_INFORMATION
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess 실패")

    def read(self, addr: int, size: int) -> bytes:
        buf = self._ct.create_string_buffer(size)
        got = self._ct.c_size_t()
        if not self._k.ReadProcessMemory(self.handle, self._ct.c_void_p(addr), buf, size, self._ct.byref(got)) or got.value != size:
            raise OSError(self._ct.get_last_error(), f"ReadProcessMemory {addr:#x}")
        return buf.raw

    def alive(self) -> bool:
        code = self._ct.c_ulong()
        return bool(self._k.GetExitCodeProcess(self.handle, self._ct.byref(code))) and code.value == 259

    def close(self):
        if self.handle:
            self._k.CloseHandle(self.handle)
            self.handle = None


def find_game_pid(name: str = "rhakmu.exe") -> int | None:
    import ctypes
    from ctypes import wintypes

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k.CreateToolhelp32Snapshot(2, 0)
    if snap in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        e = PE32(); e.dwSize = ctypes.sizeof(PE32)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == name:
                return e.th32ProcessID
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return None


class GameReader:
    """메모리 원본 -> 한 순간의 경기 상태."""

    def __init__(self, mem):
        self.mem = mem
        self._names = None

    def u32(self, a):
        return struct.unpack("<I", self.mem.read(a, 4))[0]

    def play_seconds(self) -> int:
        return self.u32(PLAY_SECONDS)

    def map_name(self) -> str:
        return cstr(self.mem.read(MAP_NAME, 260))

    def players(self) -> list[Player]:
        raw = self.mem.read(PLAYERS, PLAYER_SIZE * PLAYER_COUNT)
        return [parse_player(p, raw[p * PLAYER_SIZE:(p + 1) * PLAYER_SIZE]) for p in range(PLAYER_COUNT)]

    def units(self) -> list[Unit]:
        return parse_units(self.mem.read(UNITS, UNIT_SIZE * UNIT_COUNT))

    def local_player(self) -> int:
        return self.mem.read(LOCAL_PLAYER, 1)[0]

    def type_table(self) -> dict:
        """종류 번호 -> {name, worker, max_hp} (경기 중 한 번 읽음)."""
        if self._names is None:
            raw = self.mem.read(UNIT_NAMES, NAME_SIZE * TYPE_COUNT)
            info = self.mem.read(TYPE_INFO, TYPE_INFO_STRIDE * TYPE_COUNT)
            stats = self.mem.read(TYPE_STATS, TYPE_STATS_STRIDE * TYPE_COUNT)
            out = {}
            for t in range(1, TYPE_COUNT):
                name = cstr(raw[t * NAME_SIZE:(t + 1) * NAME_SIZE]).strip()
                worker, max_hp = False, 0
                try:
                    p = struct.unpack_from("<I", info, t * TYPE_INFO_STRIDE)[0]
                    if p:
                        worker = struct.unpack("<h", self.mem.read(p + 0x40, 2))[0] == 1
                    q = struct.unpack_from("<I", stats, t * TYPE_STATS_STRIDE)[0]
                    if q:
                        max_hp = struct.unpack("<h", self.mem.read(q + 2, 2))[0]
                except OSError:
                    pass
                if name:
                    out[t] = {"name": name, "worker": worker, "max_hp": max_hp}
            self._names = out
        return self._names
