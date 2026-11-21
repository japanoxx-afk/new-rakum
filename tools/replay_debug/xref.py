import sys,pefile,struct
pe=pefile.PE(sys.argv[1]); base=pe.OPTIONAL_HEADER.ImageBase
for tgt in [int(a,16) for a in sys.argv[2:]]:
  for s in pe.sections:
    if not s.Characteristics & 0x20000000: continue
    d=s.get_data(); va0=base+s.VirtualAddress
    for i in range(len(d)-5):
      if d[i] in (0xE8,0xE9) and (va0+i+5+struct.unpack_from('<i',d,i+1)[0])&0xffffffff==tgt:
        print(hex(tgt),'<-',hex(va0+i),'call' if d[i]==0xE8 else 'jmp')
