"""Start in-game playback from a private game copy; never touches other Rhakmu.exe processes."""
import ctypes, os, pathlib, struct, subprocess, sys, threading, time
REPO = os.path.abspath(sys.argv[1]); sys.path.insert(0, REPO); os.chdir(REPO)
import launcher, minimap_patch, replay_model, replay_record_patch as rrp, replay_memory as rm
# 개인 게임 사본 (설치 폴더를 통째로 복사한 것). 사용자가 쓰는 게임과 따로 돌기 위해 꼭 사본을 쓴다.
G = pathlib.Path(os.environ.get("RK_GAME", pathlib.Path(__file__).resolve().parent / "game"))
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = ctypes.c_void_p


def pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Rhakmu.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"')}


class Play:
    def __init__(self, rkr, sel24=None, rally=None, prepare=None, spawn=None):
        self.rp = rp = replay_model.load(rkr)
        rules = rp.header.get("rules") or {}
        sel24 = rules.get("select_24", False) if sel24 is None else sel24
        rally = rules.get("rally_gold", True) if rally is None else rally
        spawn = rules.get("rally_spawn", False) if spawn is None else spawn
        wide = rules.get("wide_checks", False)              # 런처처럼: 리플레이의 검사 방식대로 설치
        self.d = d = replay_model.ingame_data(rp)
        local = d["start"].get("local", 0)
        name = next((p["name"] for p in rp.players if p["index"] == local), "")
        mp = G / rp.header["map"].replace("\\", "/")
        if rp.map_bytes() and not mp.exists():
            mp.write_bytes(rp.map_bytes())
        (G / "RKREPLAY.RKP").write_bytes(rrp.build_rkp(d["start"], d["records"], name))
        (G / "USERs" / "RKREPLAY").mkdir(parents=True, exist_ok=True)
        (G / "USERs" / "RKREPLAY" / "RKREPLAY.SAV").write_bytes(d["save"])
        (prepare or minimap_patch.prepare)(G / "Rhakmu.exe", True, rally, True, sel24, False, False, True, spawn, wide)
        self.last = max(f for f, p, b in d["records"])
        assert not pids(), "다른 Rhakmu.exe 가 켜져 있음 (사용자 게임일 수 있어 띄우지 않음)"
        before = pids()
        self.proc = subprocess.Popen([str(G / "Launcher.exe")], cwd=str(G))
        threading.Thread(target=launcher.dismiss_version_warning, args=(self.proc,), kwargs={"timeout": 120}, daemon=True).start()
        t0 = time.time(); new = set()
        while not new and time.time() - t0 < 120:
            new = pids() - before; time.sleep(0.5)
        self.pid = new.pop()
        self.mem = rm.ProcessMemory(self.pid)
        self.h = k.OpenProcess(0x1F0FFF, False, self.pid)
        self.sec = None
        while self.sec is None:
            try: self.sec = rrp.find_section(self.mem.read)
            except OSError: time.sleep(0.5)
        while not self.flags()["play"]: time.sleep(0.2)
        self.reader = rm.GameReader(self.mem)

    def flags(self):
        return rrp.read_flags(self.mem.read, self.sec)

    def frame(self):
        for _ in range(100):
            try:
                return struct.unpack("<I", self.mem.read(0xB412B4, 4))[0]
            except OSError:
                time.sleep(0.1)
        raise OSError("game gone")

    def setms(self, v):
        k.WriteProcessMemory(ctypes.c_void_p(self.h), ctypes.c_void_p(0xB412B8), ctypes.byref(ctypes.c_uint32(v)), 4, None)

    def kill(self):
        subprocess.run(["taskkill", "/F", "/PID", str(self.pid)], capture_output=True)
