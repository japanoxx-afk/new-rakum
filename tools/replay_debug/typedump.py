"""types.py REPO RKR OUT: dump unit-type table entries (0x4FCD88 + t*0x1C -> ptr, 0xA0 bytes) during playback."""
import json, os, struct, sys, time
from probe_common import Play

out = os.path.abspath(sys.argv[3])
p = Play(sys.argv[2])
try:
    while p.frame() < 60:
        time.sleep(0.1)
    res = {}
    tbl = p.mem.read(0x4FCD88, 0x1C * 200)
    for t in range(200):
        ent = tbl[t * 0x1C:(t + 1) * 0x1C]
        ptr = struct.unpack_from("<I", ent, 0)[0]
        if not ptr:
            continue
        try:
            res[t] = {"ent": ent.hex(), "data": p.mem.read(ptr, 0xA0).hex()}
        except OSError:
            res[t] = {"ent": ent.hex(), "data": None}
    json.dump(res, open(out, "w"))
    print("types", len(res))
finally:
    p.kill()
