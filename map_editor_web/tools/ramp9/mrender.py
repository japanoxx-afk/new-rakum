import sys,struct,numpy as np
sys.path.insert(0,'/home/claude/re'); sys.path.insert(0,'/home/claude/re/ramp9')
from flipmod import diamond_to_img
from PIL import Image
TSN=['East','West','Savage','Dungeon']
class Tiles:
    def __init__(s,path):
        s.J=open(path,'rb').read(); s.T,=struct.unpack_from('<I',s.J,4); s.n,=struct.unpack_from('<H',s.J,16)
        s.rec=16+2*16384; s.c={}
    def get(s,i):
        if i not in s.c:
            o=s.T+i*s.rec; px=np.frombuffer(s.J[o+16:o+s.rec],dtype='<u2'); im=diamond_to_img(px).astype(np.uint32)
            rgba=np.zeros((128,256,4),np.uint8)
            rgba[...,0]=((im>>11)&31)*255//31; rgba[...,1]=((im>>5)&63)*255//63; rgba[...,2]=(im&31)*255//31
            from flipmod import ROWS
            for y,(x0,w) in enumerate(ROWS): rgba[y,x0:x0+w,3]=255
            # bleed 2px
            s.c[i]=Image.fromarray(rgba)
        return s.c[i]
def parse(path):
    d=open(path,'rb').read(); secs={}
    offs=[struct.unpack_from('<II',d,12+8*k) for k in range(8)]
    offs=sorted(offs,key=lambda x:x[1])
    for k,(i,o) in enumerate(offs):
        e=offs[k+1][1] if k+1<len(offs) else len(d); secs[i]=d[o:e]
    return secs
def render(path,tiles_path=None,box=None,subs_brg=None):
    s=parse(path); ts,=struct.unpack_from('<I',s[0],0); W,H=struct.unpack_from('<HH',s[0],8)
    T=Tiles(tiles_path or '/home/claude/mod/Data/tile/%s.jtl'%TSN[ts])
    cw=(W+7)//8; ch=H//2
    x0,y0,x1,y1=box or (0,0,W*32,H*32)
    img=Image.new('RGBA',(x1-x0,y1-y0),(0,0,0,255))
    for i in range(cw*ch):
        idx=struct.unpack_from('<H',s[2],i*5)[0]; x=i%cw; y=i//cw
        cx=x*256+(y&1)*128; cy=y*64
        if cx+128<x0 or cx-128>x1 or cy+64<y0 or cy-64>y1: continue
        t=T.get(idx); img.alpha_composite(t,(cx-128-x0,cy-64-y0)) if cx-128-x0>=0 and cy-64-y0>=0 else img.paste(t,(cx-128-x0,cy-64-y0),t)
    objs=[]
    n,=struct.unpack_from('<I',s[3],4)
    for k in range(n):
        r=s[3][8+20*k:28+20*k]; kind=r[2]; oid,=struct.unpack_from('<H',r,4); ox,oy=struct.unpack_from('<II',r,8); objs.append((kind,oid,ox,oy))
    return img,objs,ts,T
def brg_composite(brg_path,T,sid):
    from flipmod import parse_brg
    base,A,B,e=parse_brg(open(brg_path,'rb').read()); w,h,cells=e[sid]
    # find piece positions: group cells by piece, centroid in cell coords
    pos={}
    for r in range(h):
        for c in range(w):
            p=struct.unpack_from('<H',cells[r][c],6)[0]
            if p and p<300: pos.setdefault(p,[]).append((c,r))
    return base,pos
def place_subs(img,objs,T,brg_path,box,override=None):
    from flipmod import parse_brg
    base,A,B,e=parse_brg(open(brg_path,'rb').read())
    for kind,oid,ax,ay in objs:
        if kind!=3: continue
        w,h,cells=e[oid]; pos={}
        for r in range(h):
            for c in range(w):
                p=struct.unpack_from('<H',cells[r][c],6)[0]
                if p and p<300: pos.setdefault(p,[]).append((c,r))
        for p,lst in pos.items():
            cx=(min(c for c,r in lst)+max(c for c,r in lst)+1)/2*32; cy=(min(r for c,r in lst)+max(r for c,r in lst)+1)/2*32
            t=override(oid,p) if override else None
            if t is None: t=T.get(base+p)
            img.alpha_composite(t,(int(ax*32+cx-128-box[0]),int(ay*32+cy-64-box[1])))
