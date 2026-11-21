"""hashbp.py REPO RKR F1 F2..: execution breakpoint on the replay hash routine; dumps the unit table exactly when the check runs at frames F.
(from watch.py) REPO RKR ADDR FROMFRAME [HITS]: run playback to FROMFRAME, then hardware-watch writes to ADDR (2 bytes)
and print EIP + EBP-chain return addresses for each hit."""
import ctypes, struct, sys, time
from ctypes import wintypes as W
from probe_common import Play

targets = [int(a) for a in sys.argv[3:]]
start = min(targets) - 10
import os
if os.environ.get("NOREVEAL2") == "1":
    import noreveal_prep
    p = Play(sys.argv[2], prepare=noreveal_prep.prepare)
else:
    p = Play(sys.argv[2])
k = ctypes.WinDLL("kernel32", use_last_error=True)


class CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags", W.DWORD), ("Dr0", W.DWORD), ("Dr1", W.DWORD), ("Dr2", W.DWORD), ("Dr3", W.DWORD),
                ("Dr6", W.DWORD), ("Dr7", W.DWORD), ("FloatSave", ctypes.c_byte * 112), ("SegGs", W.DWORD),
                ("SegFs", W.DWORD), ("SegEs", W.DWORD), ("SegDs", W.DWORD), ("Edi", W.DWORD), ("Esi", W.DWORD),
                ("Ebx", W.DWORD), ("Edx", W.DWORD), ("Ecx", W.DWORD), ("Eax", W.DWORD), ("Ebp", W.DWORD),
                ("Eip", W.DWORD), ("SegCs", W.DWORD), ("EFlags", W.DWORD), ("Esp", W.DWORD), ("SegSs", W.DWORD),
                ("ExtendedRegisters", ctypes.c_byte * 512)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [("code", W.DWORD), ("pid", W.DWORD), ("tid", W.DWORD), ("pad", W.DWORD), ("u", ctypes.c_byte * 160)]


CONTEXT_DEBUG = 0x00010010
CONTEXT_FULL = 0x0001000B
k.OpenThread.restype = W.HANDLE
k.Wow64GetThreadContext.argtypes = (W.HANDLE, ctypes.POINTER(CONTEXT))
k.Wow64SetThreadContext.argtypes = (W.HANDLE, ctypes.POINTER(CONTEXT))


def threads(pid):
    class TE(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("tid", W.DWORD), ("pid", W.DWORD),
                    ("base", W.LONG), ("delta", W.LONG), ("flags", W.DWORD)]
    k.CreateToolhelp32Snapshot.restype = W.HANDLE
    snap = k.CreateToolhelp32Snapshot(4, 0)
    te = TE(); te.dwSize = ctypes.sizeof(TE); out = []
    ok = k.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.pid == pid: out.append(te.tid)
        ok = k.Thread32Next(snap, ctypes.byref(te))
    k.CloseHandle(snap)
    return out


def setdr(tid, on):
    h = k.OpenThread(0x1FFFFF, False, tid)
    c = CONTEXT(); c.ContextFlags = CONTEXT_DEBUG
    k.Wow64GetThreadContext(h, ctypes.byref(c))
    c.Dr0 = addr if on else 0
    c.Dr7 = 1 if on else 0                                   # L0, execute
    c.Dr6 = 0
    k.Wow64SetThreadContext(h, ctypes.byref(c))
    k.CloseHandle(h)



import json
import replay_memory as rm
OUT = os.path.dirname(os.path.abspath(__file__))
addr = p.sec + 0x380
while p.frame() < start - 30:
    p.setms(8); time.sleep(0.05)
p.setms(60)
while p.frame() < start:
    time.sleep(0.01)
print('attach', k.DebugActiveProcess(p.pid), ctypes.get_last_error(), 'frame', p.frame(), flush=True)
k.DebugSetProcessKillOnExit(False)
armed = False
ev = DEBUG_EVENT()
out = {}
t0 = time.time()
while len(out) < len(targets) and time.time() - t0 < 120:
    if not k.WaitForDebugEvent(ctypes.byref(ev), 1000):
        continue
    cont = 0x00010002
    if ev.code == 1:
        exc = struct.unpack_from("<I", bytes(ev.u), 0)[0]
        if exc in (0x80000003, 0x4000001F) and not armed:
            for t in threads(p.pid): setdr(t, True)
            armed = True
        elif exc in (0x80000004, 0x4000001E):
            h = k.OpenThread(0x1FFFFF, False, ev.tid)
            c = CONTEXT(); c.ContextFlags = CONTEXT_FULL | CONTEXT_DEBUG
            k.Wow64GetThreadContext(h, ctypes.byref(c))
            fr = struct.unpack("<I", p.mem.read(0xB412B4, 4))[0]
            if fr in targets and fr not in out:
                raw = p.mem.read(rm.UNITS, rm.UNIT_SIZE * rm.UNIT_COUNT)
                us = {}
                for u in range(1, rm.UNIT_COUNT):
                    o = u * rm.UNIT_SIZE
                    hp = struct.unpack_from("<h", raw, o + 8)[0]
                    if hp > 0:
                        us[u] = dict(type=struct.unpack_from("<H", raw, o + 0xE)[0], owner=raw[o + 0x10],
                                     x=struct.unpack_from("<h", raw, o + 0x12)[0], y=struct.unpack_from("<h", raw, o + 0x14)[0],
                                     hp=hp, order=struct.unpack_from("<h", raw, o + 6)[0])
                out[fr] = us
                open(os.path.join(OUT, "raw_%d.bin" % fr), "wb").write(raw)
                print("dump", fr, len(us), flush=True)
            c.EFlags |= 0x10000                       # RF: resume past the execute breakpoint
            c.Dr6 = 0
            k.Wow64SetThreadContext(h, ctypes.byref(c))
            k.CloseHandle(h)
        else:
            cont = 0x80010001
    k.ContinueDebugEvent(ev.pid, ev.tid, cont)
for t in threads(p.pid): setdr(t, False)
k.DebugActiveProcessStop(p.pid)
p.kill()
json.dump({str(f): v for f, v in out.items()}, open(os.path.join(OUT, "hashdump.json"), "w"))
print("done", sorted(out))
