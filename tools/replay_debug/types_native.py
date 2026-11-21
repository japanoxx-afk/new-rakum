"""types_native.py REPO OUT: start the private game copy normally (no replay), read the unit type table the game
loads from its data files at startup (full structs), save {type: hex(0x100 bytes)} to OUT, then kill that game."""
import json, os, struct, subprocess, sys, threading, time
REPO = os.path.abspath(sys.argv[1]); sys.path.insert(0, REPO); os.chdir(REPO)
import launcher, minimap_patch, replay_memory as rm
from probe_common import G, pids

out = os.path.abspath(sys.argv[2])
assert not pids(), "다른 Rhakmu.exe 가 켜져 있음"
minimap_patch.prepare(G / "Rhakmu.exe", True, True, True, False, False, False, False, True)   # 재생 아님
proc = subprocess.Popen([str(G / "Launcher.exe")], cwd=str(G))
threading.Thread(target=launcher.dismiss_version_warning, args=(proc,), kwargs={"timeout": 120}, daemon=True).start()
t0 = time.time(); new = set()
while not new and time.time() - t0 < 120:
    new = pids(); time.sleep(0.5)
pid = new.pop()
mem = rm.ProcessMemory(pid)
res = {}
try:
    t0 = time.time()
    while time.time() - t0 < 90:
        try:
            tbl = mem.read(0x4FCD88, 0x1C * 0xD2)
        except OSError:
            time.sleep(0.5); continue
        ptrs = [struct.unpack_from("<I", tbl, t * 0x1C)[0] for t in range(0xD2)]
        if sum(1 for p in ptrs if p) > 50:
            time.sleep(2)
            tbl = mem.read(0x4FCD88, 0x1C * 0xD2)
            for t in range(0xD2):
                p = struct.unpack_from("<I", tbl, t * 0x1C)[0]
                if p:
                    res[t] = mem.read(p, 0x100).hex()
            break
        time.sleep(0.5)
finally:
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
json.dump(res, open(out, "w"))
print("types", len(res))
