"""trace_slot.py REPO RKR SLOT A B : print changes of slot fields (order, hp, deathframe) between frames A..B"""
import struct, sys, time
from probe_common import Play
rkr, slot, A, B = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
p = Play(rkr)
prev = None
try:
    while True:
        fr = p.frame()
        p.setms(8 if fr < A else 30)
        raw = p.mem.read(0x775A38 + slot * 0x138, 0x40)
        cur = struct.unpack_from("<HHhH", raw, 6)[:2] + (struct.unpack_from("<I", raw, 0x24)[0], struct.unpack_from("<h", raw, 0xE)[0])
        if fr >= A and cur != prev:
            print(fr, "order=%#x hp=%d death=%d type=%d" % (cur[0], struct.unpack_from('<h', raw, 8)[0], cur[2], cur[3]), flush=True)
            prev = cur
        if fr > B: break
        time.sleep(0.003)
    print("flags", p.flags())
finally:
    p.kill()
