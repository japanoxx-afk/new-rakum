import sys,pefile
from capstone import *
pe=pefile.PE(sys.argv[1]); base=pe.OPTIONAL_HEADER.ImageBase
data=pe.__data__
md=Cs(CS_ARCH_X86,CS_MODE_32)
def d(va,n):
    off=pe.get_offset_from_rva(va-base)
    for i,ins in enumerate(md.disasm(bytes(data[off:off+n*8]),va)):
        if i>=n: break
        print(f"{ins.address:08x}: {ins.mnemonic} {ins.op_str}")
for a in sys.argv[2:]:
    va,n=a.split(':'); print('=====',va); d(int(va,16),int(n))
