import sys, pefile, struct
from capstone import *
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_32); md.skipdata = True
text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
code = text.get_data(); tva = base + text.VirtualAddress
ins = list(md.disasm(code, tva))
idx = {x.address: i for i, x in enumerate(ins)}
def strva(off):
    return base + pe.get_rva_from_offset(off)
mode = sys.argv[2]
if mode == "xref":
    for a in sys.argv[3:]:
        v = strva(int(a, 16)) if a.startswith("f") is False else None
        v = strva(int(a, 16))
        for i, x in enumerate(ins):
            if f"{v:#x}" in x.op_str:
                print("== ref", hex(v), "at", hex(x.address))
elif mode == "dis":
    a, n = int(sys.argv[3], 16), int(sys.argv[4])
    i = idx.get(a)
    while i is None: a -= 1; i = idx.get(a)
    for x in ins[i:i + n]: print(f"{x.address:08x}: {x.mnemonic} {x.op_str}")
elif mode == "abs":   # list absolute game addresses (0x4xxxxx-0xCxxxxx) referenced
    import collections, re
    c = collections.Counter()
    for x in ins:
        for m in re.findall(r"0x([4-9a-c][0-9a-f]{5})\b", x.op_str):
            c[int(m, 16)] += 1
    for k, v in sorted(c.items()): print(hex(k), v)
