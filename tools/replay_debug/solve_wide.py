"""solve_wide.py RKR F..: recompute the wide check hash from raw_<F>.bin / pl_<F>.bin dumps, compare with the
recording, and for a mismatch list single terms whose change by a small amount explains the recorded hash."""
import struct, sys
import os
sys.path.insert(0, os.environ.get("RK_REPO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import replay_model as m

M = 1 << 32
rp = m.load(sys.argv[1]); dd = m.ingame_data(rp)
chk = {c[0]: struct.unpack("<IIIII", c[2]) for c in dd["records"] if c[1] == 0xFD}


def terms(f):
    raw = open("raw_%d.bin" % f, "rb").read()
    pl = open("pl_%d.bin" % f, "rb").read()
    t = []  # (label, value)
    for u in range(1, 0x6A6):
        o = u * 0x138
        hp = struct.unpack_from("<h", raw, o + 8)[0]
        if hp > 0:
            x, y = struct.unpack_from("<hh", raw, o + 0x12)
            t += [(f"u{u}.hp", hp), (f"u{u}.pos", (x & 0xFFFF) | (y & 0xFFFF) << 16),
                  (f"u{u}.type", struct.unpack_from("<H", raw, o + 0xE)[0])]
    for u in range(0x6A5, 0, -1):
        o = u * 0x138
        hp = struct.unpack_from("<h", raw, o + 8)[0]
        dth = struct.unpack_from("<I", raw, o + 0x24)[0]
        t.append((f"slot{u}.hp+death(hp={hp},death={dth},type={struct.unpack_from('<h', raw, o + 0xE)[0]},owner={raw[o + 0x10]})",
                  (hp + dth) & 0xFFFFFFFF))
    for p in range(8):
        o = p * 0x11E0
        t.append((f"p{p}.pop(max={struct.unpack_from('<h', pl, o)[0]},cur={struct.unpack_from('<h', pl, o + 2)[0]})",
                  struct.unpack_from("<I", pl, o)[0]))
        res = struct.unpack_from("<4i", pl, o + 0x864)
        t.append((f"p{p}.res{res}", sum(res) & 0xFFFFFFFF))
    return t


def H(t):
    h = 0
    for _, v in t:
        h = (h * 31 + v) & 0xFFFFFFFF
    return h


for f in map(int, sys.argv[2:]):
    t = terms(f)
    h = H(t)
    want = chk[f][3]
    print(f, "calc", hex(h), "recorded", hex(want), "count", sum(1 for l, _ in t if l.endswith(".hp")), chk[f][4])
    if h != want:
        delta = (want - h) % M
        n = len(t)
        for i, (label, v) in enumerate(t):
            c = pow(31, n - 1 - i, M)
            d = delta * pow(c, -1, M) % M
            ds = d if d < 1 << 31 else d - M
            if abs(ds) <= 100000:
                print("   candidate:", label, "differs by", ds)
