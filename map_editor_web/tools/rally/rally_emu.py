import struct
from unicorn import *
from unicorn.x86_const import *
from rally_asm import CODE, HOOK, CAVE, SITE, EXACT, GATHER, MOVE
GRID=0xb4198a
def run(cells, click):
    mu=Uc(UC_ARCH_X86,UC_MODE_32)
    mu.mem_map(0x400000,0x100000)          # code incl. 0x473000 and cave 0x4eb000
    mu.mem_map(0xb40000,0x100000)          # grid region
    mu.mem_map(0x100000,0x10000)           # stack
    for a in (EXACT,GATHER,MOVE): mu.mem_write(a,b'\xf4')   # hlt
    mu.mem_write(SITE,HOOK); mu.mem_write(CAVE,CODE)
    for (x,y),v in cells.items(): mu.mem_write(GRID+y*0x208+x,bytes([v]))
    ebp=0x108000; caller=0x109000
    mu.mem_write(ebp,struct.pack('<I',caller))
    x,y=click; mu.mem_write(ebp+0x14,struct.pack('<hh',x,y))
    mu.mem_write(caller+0x14,struct.pack('<hh',x,y))
    mu.reg_write(UC_X86_REG_EBP,ebp); mu.reg_write(UC_X86_REG_ESP,ebp-0x60)
    try: mu.emu_start(SITE,0,count=5000)
    except UcError: pass
    eip=mu.reg_read(UC_X86_REG_EIP)
    where={EXACT+1:'EXACT',GATHER+1:'GATHER',MOVE+1:'MOVE'}.get(eip,hex(eip))
    cx,cy=struct.unpack('<hh',mu.mem_read(caller+0x14,4))
    return where,(cx,cy)
gold={(x,y):0x53 for x in (50,51,52) for y in (40,)}
well={(x,y):0x63 for x in (70,71,72) for y in (60,61)}
tree={(30,30):0x41}
cells={**gold,**well,**tree}
px=lambda cx,cy:(cx*32+10,cy*32+5)
tests=[('click on gold cell',px(51,40),'EXACT'),
       ('1 cell above gold',px(51,39),'GATHER'),
       ('2 cells left of gold',px(48,40),'GATHER'),
       ('3 cells away',px(47,40),'MOVE'),
       ('near well',px(73,62),'GATHER'),
       ('near tree only',px(31,31),'MOVE'),
       ('open ground',px(10,10),'MOVE')]
ok=True
for name,c,exp in tests:
    w,newpos=run(cells,c)
    tgt=(newpos[0]//32,newpos[1]//32)
    print('%-22s -> %-6s new target cell %s attr=%s'%(name,w,tgt,hex(cells.get(tgt,0))))
    ok&= (w==exp) and (w!='GATHER' or cells.get(tgt) in (0x53,0x63))
print('ALL OK' if ok else 'FAIL')
