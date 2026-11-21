"""cmp_units.py REPO RKR F1 F2 ...: pause playback at each recorded keyframe frame and diff units against the recording.
Also dumps the playback unit table at each extra frame given with a leading '@' (e.g. @8520 @8525)."""
import json, struct, sys, time
from probe_common import Play
import replay_memory as rm

p = Play(sys.argv[2])
rp = p.rp
wants = []
for a in sys.argv[3:]:
    if a.startswith("@"):
        wants.append((int(a[1:]), None))
    else:
        f = int(a)
        e = next(e for e in rp.frames if e.get("f") == f and "k" in e)
        wants.append((f, e["k"]))


def units():
    raw = p.mem.read(rm.UNITS, rm.UNIT_SIZE * rm.UNIT_COUNT)
    out = {}
    for u in range(1, rm.UNIT_COUNT):
        o = u * rm.UNIT_SIZE
        hp = struct.unpack_from("<h", raw, o + 8)[0]
        if hp > 0:
            out[u] = dict(type=struct.unpack_from("<h", raw, o + 0xE)[0], owner=raw[o + 0x10],
                          x=struct.unpack_from("<h", raw, o + 0x12)[0], y=struct.unpack_from("<h", raw, o + 0x14)[0],
                          hp=hp, order=struct.unpack_from("<h", raw, o + 6)[0], cls=struct.unpack_from("<h", raw, o + 2)[0])
    return out


try:
    for f, k in sorted(wants, key=lambda w: w[0]):
        while True:
            cur = p.frame()
            p.setms(300 if cur >= f - 4 else 8)
            if cur >= f:
                break
            time.sleep(0.005)
        p.setms(10 ** 8); time.sleep(0.1)
        got = units()
        print("== frame", f, "actual", p.frame(), "diverged", p.flags()["diverged"], flush=True)
        if k is None:
            print(json.dumps(got), flush=True)
            continue
        rec = {r[0]: dict(type=r[1], owner=r[2], x=r[3], y=r[4], hp=r[5]) for r in k}
        for u in sorted(set(rec) | set(got)):
            a, b = rec.get(u), got.get(u)
            if not a or not b or any(a[x] != b[x] for x in ("type", "owner", "x", "y", "hp")):
                print("  unit", u, "REC", a, "PLAY", b, flush=True)
finally:
    p.kill()
