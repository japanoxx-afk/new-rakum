import sys,pefile
from capstone import *
pe=pefile.PE(sys.argv[1]); base=pe.OPTIONAL_HEADER.ImageBase; data=pe.__data__
md=Cs(CS_ARCH_X86,CS_MODE_32)
lo,hi=int(sys.argv[2],16),int(sys.argv[3],16); pats=sys.argv[4:]
off=pe.get_offset_from_rva(lo-base)
for ins in md.disasm(bytes(data[off:off+(hi-lo)]),lo):
    s=f"{ins.mnemonic} {ins.op_str}"
    if any(p in s for p in pats): print(f"{ins.address:08x}: {s}")
