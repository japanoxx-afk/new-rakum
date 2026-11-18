import sys,struct;sys.path.insert(0,'/home/claude/re')
import numpy as np
from flipmod import parse_brg, build_brg
A=np.array((59,155.)); B=np.array((169,95.)); C=np.array((251,240.)); d=B-A
C2=C-0.12*(C-A); ts=(0.10,0.42,0.74)
bases=[A+t*d+np.array([14,6]) for t in ts]+[C2+t*d for t in ts]
def cells_for(mirror):
    out=set()
    for bx,by in bases:
        if mirror: bx=509-bx
        for x in np.arange(bx-18,bx+19,4):
            for y in np.arange(by-14,by+1,4):
                out.add((int(y//32),int(x//32)))
    return out
for pre in 'EWSD':
    p='/home/claude/mod/Data/tile/%s_Bridge.brg'%pre
    base,Acnt,Bcnt,ents=parse_brg(open(p,'rb').read())
    for sid,mir in ((9,False),(8,True)):
        w,h,cells=ents[sid]; blk=cells_for(mir); n0=n1=0
        for r in range(h):
            for c in range(w):
                cl=cells[r][c]
                if cl==b'\0'*8: continue
                was=cl[3]; cl[3]=0 if (r,c) in blk else 1
                n0+=was==0; n1+=cl[3]==0
        print(pre,sid,'blocked before',n0,'after',n1,sorted(blk))
    open(p,'wb').write(build_brg(base,Acnt,Bcnt,ents))
