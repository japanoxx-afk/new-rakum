import sys,struct;sys.path.insert(0,'/home/claude/re');sys.path.insert(0,'/home/claude/re/ramp9')
import numpy as np
from flipmod import make, parse_brg, build_brg, diamond_to_img, img_to_diamond, rgb565_to_555
from s16 import S16; from edit6 import edit; from mrender import Tiles
from PIL import Image
POS={'bottom':(127,128),'left':(0,64),'right':(254,64),'top':(127,0)}
def to565(rgb):
    r=(rgb[...,0].astype(np.uint32)*31+127)//255; g=(rgb[...,1].astype(np.uint32)*63+127)//255; b=(rgb[...,2].astype(np.uint32)*31+127)//255
    return ((r<<11)|(g<<5)|b).astype(np.uint16)
def run(name='East',pre='E',jobs=((9,False),(8,True),(3,'under')),lip_tile=70,generic=False):
    global GEN; GEN=generic
    nj,nb,info=make('/home/claude/re/%s.JTL'%name.upper(),'/home/claude/re/%s_BRIDGE.BRG'%pre)
    for sid,mir in jobs:
        nj,nb=one(nj,nb,name,pre,sid,mir,lip_tile)
    open('/home/claude/mod/Data/tile/%s.jtl'%name,'wb').write(nj)
    open('/home/claude/mod/Data/tile/%s_Bridge.brg'%pre,'wb').write(nb)
MAPS={'East':'/tmp/flip2.rkm','West':'/tmp/flip_1.rkm','Savage':'/tmp/flip_2.rkm','Dungeon':'/tmp/flip_3.rkm'}
ANCH={9:(88,30),8:(28,32),3:(88,74),2:(24,74)}
def under(name,sid):
    from mrender import render
    ax,ay=ANCH[sid]; b=(ax*32,ay*32,ax*32+510,ay*32+256)
    im,o,t,T=render(MAPS[name],'/home/claude/re/%s.JTL'%name.upper(),box=b); return im
def one(nj,nb,name,pre,sid,mir,lip_tile):
    open('/tmp/_j','wb').write(nj); T=Tiles('/tmp/_j')
    import edit6; edit6.PRE=pre
    s=S16(open('/home/claude/re/%s_BRIDGE.S16'%pre,'rb').read())
    if mir=='under':
        from edit_o import edit_under, round_tip, cap
        f=s.decode(sid)[1].copy(); U=under(name,sid); e=cap(round_tip(edit_under(f,U),U),U)
    else:
     f=s.decode(sid-6)[1][::-1].copy()
     e=edit(f[:,::-1].copy(),T,lip_tile,GEN,(np.asarray(under(name,sid))[:,::-1] if GEN else None))[:,::-1].copy() if mir else edit(f,T,lip_tile,GEN,(under(name,sid) if GEN else None))
    delta=e[...,:3].astype(int)-f[...,:3].astype(int)
    Tt,T2=struct.unpack_from('<II',nj,4); cnt,=struct.unpack_from('<H',nj,16); rec=16+2*16384
    base,A,B,ents=parse_brg(nb); w,h,cells=ents[sid]
    pieces=sorted({struct.unpack_from('<H',cells[r][c],6)[0] for r in range(h) for c in range(w)}-{0})
    pieces=[p for p in pieces if p<300]
    # identify each piece's position by best match
    newd=[]; remap={}
    for p in pieces:
        tile=base+p; o=Tt+tile*rec; hdr=nj[o:o+16]
        img=diamond_to_img(np.frombuffer(nj[o+16:o+rec],dtype='<u2')).astype(np.uint32)
        rgb=np.stack([((img>>11)&31)*255//31,((img>>5)&63)*255//63,(img&31)*255//31],-1).astype(int)
        best=None
        for k,(x0,y0) in POS.items():
            sub=f[y0:y0+128,x0:x0+256,:3].astype(int); err=np.abs(sub-rgb).mean()
            if best is None or err<best[0]: best=(err,k)
        x0,y0=POS[best[1]]
        nrgb=e[y0:y0+128,x0:x0+256,:3].astype(int)
        changed=np.abs(delta[y0:y0+128,x0:x0+256]).sum()>0
        n565=to565(nrgb); n565=np.where(np.abs(delta[y0:y0+128,x0:x0+256]).sum(-1)>0,n565,img.astype(np.uint16))
        remap[p]=cnt+len(newd)-base; newd.append((hdr,img_to_diamond(n565)))
        print(name,'piece',p,best,'->',remap[p])
    for r in range(h):
        for c in range(w):
            p=struct.unpack_from('<H',cells[r][c],6)[0]
            if p in remap: struct.pack_into('<H',cells[r][c],6,remap[p])
    n2=cnt+len(newd)
    hdr=bytearray(nj[:Tt]); struct.pack_into('<H',hdr,16,n2); struct.pack_into('<I',hdr,8,Tt+n2*rec)
    b565=nj[Tt:Tt+cnt*rec]+b''.join(h_+p_.astype('<u2').tobytes() for h_,p_ in newd)
    b555=nj[T2:T2+cnt*rec]+b''.join(h_+rgb565_to_555(p_).astype('<u2').tobytes() for h_,p_ in newd)
    J=bytes(hdr)+b565+b555; Bb=build_brg(base,A,B,ents)
    Image.fromarray(e).save('/home/claude/re/ramp9/%s_sub%d.png'%(name,sid))
    return J,Bb
if __name__=='__main__':
    run(generic='savage')
    for n,p in [('West','W'),('Savage','S'),('Dungeon','D')]:
        import os
        jobs=((9,False),(8,True),(3,'under'))
        run(n,p,jobs,generic='savage')
