"""Developer-only generator for selection_patch.SITES / STUBS (needs capstone + keystone).

Reads the original Rhakmu.exe 1.000d (game_backup/Rhakmu.exe), finds every instruction that
touches the 12-slot unit lists and prints the site table that selection_patch.py embeds.

    python build_selection_patch.py            # print table (paste into selection_patch.py)
    python build_selection_patch.py --check    # verify selection_patch.py matches
"""
from __future__ import annotations

import bisect
import re
import struct
import sys
from pathlib import Path

import capstone
from capstone import x86 as X

import selection_patch as sp

HERE = Path(__file__).resolve().parent
EXE = HERE / 'game_backup' / 'Rhakmu.exe'
BASE, TEXT_VA, TEXT_OFF = 0x400000, 0x401000, 0x1000

# old address -> new address (selection 12 -> 24)
RELOC = {
    0x80083E: sp.LSEL, 0x800840: sp.LSEL + 2, 0x800854: sp.LSEL + 2 * (sp.N - 1),
    0x7668F8: sp.TSEL, 0x7668FA: sp.TSEL + 2, 0x76690E: sp.TSEL + 2 * (sp.N - 1),
    0x7F793E: sp.PSEL,
    0x106A6C0: sp.GROUPS,
}
GROUP_FUNCS = (0x4DC640, 0x4DC6A0, 0x4DC7F0, 0x4DC940)
# UI: the info panel has 12 portrait slots (position table 0x4FF5B0 + layout*0x30, 12 entries)
UI_CLAMP = {0x45422C: 'eax', 0x454254: 'ecx', 0x45430A: 'eax', 0x4582F0: 'eax'}
FORMATION = 0x47C550           # stack arrays [ebp-0x18] (12 words) / [ebp-0x24] (12 bytes)
NOT_ARRAY_BOUND = {0x453C28, 0x460789}   # cmp ..., 0xb that are UI state / command ids


def load():
    data = EXE.read_bytes()
    text = data[TEXT_OFF:TEXT_OFF + 0xEA412]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    ins, o = [], 0
    while o < len(text):
        for i in md.disasm(text[o:], TEXT_VA + o):
            ins.append(i)
            o = i.address - TEXT_VA + i.size
        else:
            o += 1
    starts = sorted(TEXT_VA + m.start() for m in re.finditer(rb'\x55\x8b\xec', text)
                    if m.start() and (text[m.start() - 1] in (0xCC, 0xC3, 0x90) or text[m.start() - 3] == 0xC2))
    return data, ins, starts


def touched(i):
    for op in i.operands:
        v = op.mem.disp & 0xFFFFFFFF if op.type == X.X86_OP_MEM else op.imm & 0xFFFFFFFF if op.type == X.X86_OP_IMM else None
        if v is not None and (v in RELOC or v in (0x80083C, 0x766910, 0x7F793C)):
            return True
    return False


def imm_at(i, value, size):
    """Offset of the last occurrence of `value` (little endian, size bytes) in the instruction."""
    b = bytes(i.bytes)
    k = b.rfind(value.to_bytes(size, 'little', signed=value < 0))
    assert k >= 0 and k + size == len(b) or size == 4, (hex(i.address), i.mnemonic, i.op_str)
    return k


def build():
    data, ins, starts = load()
    func_of = lambda a: starts[bisect.bisect_right(starts, a) - 1]
    funcs = sorted({func_of(i.address) for i in ins if touched(i)})
    by_func = {}
    for i in ins:
        f = func_of(i.address)
        if f in funcs:
            by_func.setdefault(f, []).append(i)
    edits = {}                    # va -> (before, after)

    def put(i, k, size, value):
        va = i.address + k
        old = data[va - BASE: va - BASE + size]
        new = value.to_bytes(size, 'little')
        assert va not in edits, hex(va)
        edits[va] = (old, new)

    for f in funcs:
        body = by_func[f]
        for n, i in enumerate(body):
            b = bytes(i.bytes)
            # 1) relocate array addresses (disp32 / imm32)
            for old, new in RELOC.items():
                k = b.find(struct.pack('<I', old))
                if k >= 0:
                    assert b.count(struct.pack('<I', old)) == 1
                    put(i, k, 4, new)
            if i.address in UI_CLAMP or f == FORMATION:
                continue
            nxt = body[n + 1] if n + 1 < len(body) else None
            # 2) loop bounds / capacity checks: cmp X, 12  (and 11 for shift-down loops)
            if i.mnemonic == 'cmp' and i.op_str.endswith(', 0xc') and nxt and nxt.mnemonic.startswith('j'):
                put(i, len(b) - 1, 1, sp.N)
            elif (i.mnemonic == 'cmp' and i.op_str.endswith(', 0xb') and i.address not in NOT_ARRAY_BOUND):
                put(i, len(b) - 1, 1, sp.N - 1)
            # 3) memset / memcpy sizes of the lists
            elif i.mnemonic == 'push' and i.op_str in ('0x18', '0x1a') and nxt and nxt.mnemonic == 'push':
                after = body[n + 1:n + 3]
                if any(touched(a) for a in after) or any('0x7f793e' in a.op_str for a in body[n + 1:n + 6]):
                    put(i, 1, 1, 2 * sp.N)
            # 4) per-player command loops: mov word ptr [ebp - 8], 0xc
            elif i.mnemonic == 'mov' and i.op_str == 'word ptr [ebp - 8], 0xc':
                put(i, len(b) - 2, 2, sp.N)
            # 5) control-group layout
            if f in GROUP_FUNCS:
                if i.mnemonic == 'imul' and i.op_str.endswith(', 0x1a'):
                    put(i, len(b) - 1, 1, sp.GROUP_STRIDE)
                elif i.mnemonic == 'imul' and i.op_str.endswith(', 0xd0'):
                    put(i, len(b) - 4, 4, sp.PLAYER_GROUPS)
                elif i.mnemonic == 'push' and i.op_str == '0xd0':
                    put(i, 1, 4, sp.PLAYER_GROUPS)
                elif i.mnemonic == 'cmp' and i.op_str == 'ecx, 8':
                    put(i, len(b) - 1, 1, sp.GROUP_COUNT)

    # UI: portrait count capped at 12 -> call clamp stub
    for va, reg in UI_CLAMP.items():
        old = data[va - BASE: va - BASE + 7]
        assert old == bytes.fromhex('0fbf05' if reg == 'eax' else '0fbf0d') + struct.pack('<I', 0x80083C), hex(va)
        target = sp.SECTION_VA + sp.STUB_OFFSET[reg]
        edits[va] = (old, b'\xe8' + struct.pack('<i', target - (va + 5)) + b'\x90\x90')

    # formation (move-in-group spacing): grow the two stack arrays inside the existing frame
    for i in by_func[FORMATION]:
        b, s = bytes(i.bytes), i.op_str
        if re.search(r'\[ebp \+ e[a-d]x\*2 - 0x18\]', s) or s.endswith('[ebp - 0x18]'):
            assert b[-1] == 0xE8, hex(i.address)            # disp8 is the last byte
            put(i, len(b) - 1, 1, 0x100 - 0x78)             # words -> [ebp-0x78] (24 words)
        elif re.search(r'\[ebp \+ e[a-d]x - 0x24\]', s) or s.endswith('[ebp - 0x24]'):
            assert b[-1] == 0xDC, hex(i.address)
            put(i, len(b) - 1, 1, 0x100 - 0x18)             # bytes -> [ebp-0x18] (24 bytes)
        elif i.mnemonic == 'push' and s in ('0x18', '0xc') and b[0] == 0x6A:
            put(i, 1, 1, 2 * sp.N if s == '0x18' else sp.N)
        elif i.mnemonic == 'cmp' and s.endswith(', 0xc'):
            put(i, len(b) - 1, 1, sp.N)
    return sorted((va - BASE, old, new) for va, (old, new) in edits.items())


def table(sites):
    return '\n'.join(f'    ({off:#07x}, "{old.hex()}", "{new.hex()}"),' for off, old, new in sites)


if __name__ == '__main__':
    sites = build()
    if '--check' in sys.argv:
        ok = tuple((o, bytes.fromhex(a), bytes.fromhex(b)) for o, a, b in sp.SITES_HEX) == tuple(sites)
        print('OK' if ok else 'MISMATCH', len(sites))
        sys.exit(0 if ok else 1)
    print(table(sites))
    print(len(sites), 'sites', file=sys.stderr)
