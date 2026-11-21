"""cmp_res.py REPO RKR START END: at each recorded scene frame, compare resources and list reserved slots."""
import struct, sys, time
from probe_common import Play
import replay_memory as rm
rkr, A, B = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
import os, noreveal_prep
p = Play(rkr, prepare=noreveal_prep.prepare if os.environ.get("NOREVEAL2") == "1" else None)
rp = p.rp
active = [pl["index"] for pl in rp.players]
scenes = [(i, fr) for i, fr in enumerate(rp.frames) if fr.get("f") and A <= fr["f"] <= B]
try:
    for i, fr in scenes:
        f = fr["f"]
        while True:
            cur = p.frame()
            p.setms(250 if cur >= f - 3 else 8)
            if cur >= f: break
            time.sleep(0.01)
        p.setms(10 ** 8); time.sleep(0.05)
        players = p.reader.players()
        mine = [players[k].resources + list(players[k].pop) for k in active]
        raw = p.mem.read(rm.UNITS, rm.UNIT_SIZE * rm.UNIT_COUNT)
        reserved = [u for u in range(1, 80) if struct.unpack_from("<h", raw, u * rm.UNIT_SIZE + 8)[0] > 0
                    and struct.unpack_from("<h", raw, u * rm.UNIT_SIZE + 0xE)[0] == 0]
        rec = rp.last_value(i, "p")
        diff = "" if rec == mine else f" REC {rec} PLAY {mine}"
        print(f, p.frame(), "reserved", reserved, diff, flush=True)
finally:
    p.setms(33); p.kill()
