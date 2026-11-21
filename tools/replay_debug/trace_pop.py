"""trace_pop.py REPO RKR SLOT A B: per frame, player-1 pop and slot raw (first 0x40 bytes) changes."""
import struct, sys, time
from probe_common import Play
rkr, slot, A, B = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
p = Play(rkr)
prev = None
try:
    while True:
        fr = p.frame()
        p.setms(8 if fr < A - 5 else 120)
        if fr >= A:
            pl = p.mem.read(0x7F7908 + 0x11E0, 4)
            raw = p.mem.read(0x775A38 + slot * 0x138, 0x60)
            cur = (pl, raw)
            if cur != prev:
                print(fr, "pop1", struct.unpack("<hh", pl), "slot", raw[:0x60].hex(), flush=True)
                prev = cur
        if fr > B: break
        time.sleep(0.01)
finally:
    p.setms(33); p.kill()
