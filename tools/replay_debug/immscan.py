import sys,pefile
from capstone import *
pe=pefile.PE(sys.argv[1]); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_32); md.skipdata=True
pats=sys.argv[2:]
for s in pe.sections:
    if not s.Characteristics & 0x20000000: continue
    d=s.get_data(); va0=base+s.VirtualAddress
    if va0>=0x1000000: continue
    for ins in md.disasm(d,va0):
        t=f"{ins.mnemonic} {ins.op_str}"
        if any(t.startswith(p) or t.endswith(p) for p in pats) and ins.mnemonic=='cmp': print(f"{ins.address:x}: {t}")
