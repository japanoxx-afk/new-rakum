import sys,pefile
from capstone import *
pe=pefile.PE(sys.argv[1]); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_32)
pat=int(sys.argv[2],16).to_bytes(4,'little')
for s in pe.sections:
    if not s.Characteristics & 0x20000000: continue
    d=s.get_data(); va0=base+s.VirtualAddress; i=d.find(pat)
    while i>=0:
        for back in range(2,8):
            ins=list(md.disasm(d[i-back:i-back+16],va0+i-back,1))
            if ins and ins[0].size>=back+4 and pat in ins[0].bytes:
                nxt=list(md.disasm(d[i-back:i-back+40],va0+i-back,4))
                print(' | '.join(f"{x.address:x}: {x.mnemonic} {x.op_str}" for x in nxt)); break
        i=d.find(pat,i+1)
