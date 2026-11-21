"""diverge.py REPO RKR [MS]: play the replay in the private game copy at MS ms/frame and report the first divergence."""
import json, sys, time
from probe_common import Play

ms = int(sys.argv[3]) if len(sys.argv) > 3 else 8
import os
if os.environ.get("NOREVEAL2") == "1":
    import noreveal_prep
    p = Play(sys.argv[2], prepare=noreveal_prep.prepare)
else:
    p = Play(sys.argv[2])
import ctypes, os
NOREVEAL = os.environ.get("NOREVEAL") == "1"
k32 = ctypes.WinDLL("kernel32")
def clear_reveal():
    import struct as st
    v = st.unpack("<H", p.mem.read(0xB412C8, 2))[0]
    if v & 1:
        k32.WriteProcessMemory(ctypes.c_void_p(p.h), ctypes.c_void_p(0xB412C8), ctypes.byref(ctypes.c_uint16(v & ~1)), 2, None)
        print("cleared reveal at frame", p.frame(), flush=True)
res = {}
t0 = time.time()
try:
    while time.time() - t0 < 1500:
        try:
            fr = p.frame()
        except OSError:
            res["gone"] = True; break
        if NOREVEAL:
            clear_reveal()
        if fr > 20:
            p.setms(ms)
        f = p.flags()
        res = {"frame": fr, **f}
        if int(time.time() - t0) % 5 == 0: print("t", int(time.time() - t0), fr, f["diverged"], f["fed"], flush=True)
        if f["diverged"] or fr >= p.last:
            break
        time.sleep(0.5)
    if res.get("diverged"):
        # 어긋난 검사값과 기록된 값 비교
        want = [c for c in p.d["records"] if c[1] == 0xFD and c[0] == res["diverged"]]
        res["want"] = [w[2].hex() for w in want]
finally:
    p.kill()
res["last"] = p.last
res["rules"] = p.rp.header.get("rules")
print(json.dumps(res, default=str))
