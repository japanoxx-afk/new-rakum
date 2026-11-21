"""watch.py REPO RKR ADDR FROMFRAME [HITS]: run playback to FROMFRAME, then hardware-watch writes to ADDR (2 bytes)
and print EIP + EBP-chain return addresses for each hit."""
import ctypes, struct, sys, time
from ctypes import wintypes as W
from probe_common import Play

addr, start, hits = int(sys.argv[3], 16), int(sys.argv[4]), int(sys.argv[5]) if len(sys.argv) > 5 else 3
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
    c.Dr7 = (1 | (1 << 16) | (1 << 18)) if on else 0      # L0, write, len 2
    c.Dr6 = 0
    k.Wow64SetThreadContext(h, ctypes.byref(c))
    k.CloseHandle(h)


while p.frame() < start - 20:
    p.setms(8); time.sleep(0.05)
p.setms(150)
while p.frame() < start:
    time.sleep(0.01)
print('attach', k.DebugActiveProcess(p.pid), ctypes.get_last_error(), 'frame', p.frame(), flush=True)
k.DebugSetProcessKillOnExit(False)
armed = False
ev = DEBUG_EVENT()
got = 0
t0 = time.time()
while got < hits and time.time() - t0 < 180:
    if not k.WaitForDebugEvent(ctypes.byref(ev), 1000):
        continue
    cont = 0x00010002                                 # DBG_CONTINUE
    if ev.code == 1:                                  # exception
        exc = struct.unpack_from("<I", bytes(ev.u), 0)[0]
        print('exc', hex(exc), 'tid', ev.tid, 'frame', p.frame(), flush=True)
        if exc in (0x80000003, 0x4000001F) and not armed:           # attach breakpoint
            for t in threads(p.pid): setdr(t, True)
            print('armed', threads(p.pid), flush=True)
            armed = True
        elif exc in (0x80000004, 0x4000001E):         # single step (wow64)
            h = k.OpenThread(0x1FFFFF, False, ev.tid)
            c = CONTEXT(); c.ContextFlags = CONTEXT_FULL | CONTEXT_DEBUG
            k.Wow64GetThreadContext(h, ctypes.byref(c))
            chain, ebp = [], c.Ebp
            for _ in range(8):
                try:
                    nxt, ret = struct.unpack("<II", p.mem.read(ebp, 8))
                except OSError:
                    break
                chain.append(hex(ret)); ebp = nxt
            val = struct.unpack("<h", p.mem.read(addr, 2))[0]
            u0 = (addr - 0x775A38) // 0x138 * 0x138 + 0x775A38
            ur = p.mem.read(u0, 0x40)
            val = (val, "hp", struct.unpack_from("<h", ur, 8)[0], "order", hex(struct.unpack_from("<H", ur, 6)[0]), "death", struct.unpack_from("<I", ur, 0x24)[0])
            print("frame", p.frame(), "eip", hex(c.Eip), "val", val, "esi", hex(c.Esi), "chain", chain, flush=True)
            c.Dr6 = 0
            k.Wow64SetThreadContext(h, ctypes.byref(c))
            k.CloseHandle(h)
            got += 1
        else:
            cont = 0x80010001                         # DBG_EXCEPTION_NOT_HANDLED
    k.ContinueDebugEvent(ev.pid, ev.tid, cont)
for t in threads(p.pid): setdr(t, False)
k.DebugActiveProcessStop(p.pid)
p.kill()
