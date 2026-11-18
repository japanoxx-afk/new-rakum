import struct, numpy as np, json, sys
sys.path.insert(0,'/home/claude/re')
ROWS=[]
for k in range(64): w=2+4*k; ROWS.append(((256-w)//2,w))
ROWS+=ROWS[::-1]
def diamond_to_img(px):
    img=np.zeros((128,256),np.uint16); p=0
    for y,(x0,w) in enumerate(ROWS): img[y,x0:x0+w]=px[p:p+w]; p+=w
    return img
def img_to_diamond(img):
    out=[]
    for y,(x0,w) in enumerate(ROWS): out.append(img[y,x0:x0+w])
    return np.concatenate(out)
def rgb565_to_555(a):
    a=a.astype(np.uint32); return (((a>>11)&31)<<10 | (((a>>5)&63)>>1)<<5 | (a&31)).astype(np.uint16)

def parse_brg(d):
    base,=struct.unpack_from('<H',d,0); A,B=struct.unpack_from('<II',d,2); p=10; ents=[]
    for i in range(A+B):
        w,h=struct.unpack_from('<II',d,p); p+=8
        cells=[[bytearray(d[p+(r*w+c)*8:p+(r*w+c)*8+8]) for c in range(w)] for r in range(h)]; p+=w*h*8
        ents.append([w,h,cells])
    assert p==len(d)
    return base,A,B,ents
def build_brg(base,A,B,ents):
    out=bytearray(struct.pack('<HII',base,A,B))
    for w,h,cells in ents:
        out+=struct.pack('<II',w,h)
        for r in range(h):
            for c in range(w): out+=cells[r][c]
    return bytes(out)
SWAPNS=lambda m: (m & ~0x6 & 0xff) | ((m&4)>>1) | ((m&2)<<1)

def make(jtl_path, brg_path, src_ids=(2,3,4,5)):
    J=open(jtl_path,'rb').read(); Bd=open(brg_path,'rb').read()
    T,T2=struct.unpack_from('<II',J,4); cnt,=struct.unpack_from('<H',J,16); npx,=struct.unpack_from('<I',J,18)
    rec=16+2*npx; assert T2==T+cnt*rec and len(J)==T2+cnt*rec
    base,A,B,ents=parse_brg(Bd); assert B==0
    newdiam=[]   # (hdr16, px565)
    piece_map={} # old piece -> new piece
    new_entries=[]
    for sid in src_ids:
        w,h,cells=ents[sid]
        used=[r for r in range(h) if any(cells[r][c]!=b'\0'*8 for c in range(w))]
        assert max(used)<=7, (sid,used)
        for r in range(8):
            for c in range(w):
                p=struct.unpack_from('<H',cells[r][c],6)[0]
                if p and p < 200 and p not in piece_map:
                    tile=base+p; o=T+tile*rec
                    hdr=bytearray(J[o:o+16]); px=np.frombuffer(J[o+16:o+rec],dtype='<u2')
                    img=diamond_to_img(px)[::-1].copy()
                    nh=bytearray(hdr); nh[0:4]=hdr[0:4][::-1]
                    piece_map[p]=cnt+len(newdiam)-base; newdiam.append((bytes(nh),img_to_diamond(img)))
        nc=[[bytearray(8) for _ in range(w)] for _ in range(h)]
        for r in range(8):
            for c in range(w):
                src=cells[7-r][c]
                if src==b'\0'*8: continue
                cell=bytearray(src); cell[1]=SWAPNS(cell[1])
                p=struct.unpack_from('<H',cell,6)[0]
                if p and p < 200: struct.pack_into('<H',cell,6,piece_map[p])
                nc[r][c]=cell
        for r in range(8,h):
            for c in range(w): nc[r][c]=bytearray(cells[r][c])
        new_entries.append([w,h,nc])
    n2=cnt+len(newdiam)
    hdr=bytearray(J[:T]); struct.pack_into('<H',hdr,16,n2); struct.pack_into('<I',hdr,8,T+n2*rec)
    b565=J[T:T+cnt*rec]+b''.join(h+p.astype('<u2').tobytes() for h,p in newdiam)
    b555=J[T2:T2+cnt*rec]+b''.join(h+rgb565_to_555(p).astype('<u2').tobytes() for h,p in newdiam)
    newJ=bytes(hdr)+b565+b555
    newB=build_brg(base,A+len(new_entries),0,ents+new_entries)
    return newJ,newB,{'pieces':{str(k):v for k,v in piece_map.items()},'newtiles':len(newdiam),'base':base,'cnt':cnt}
if __name__=='__main__':
    import os
    os.makedirs('/home/claude/mod/Data/tile',exist_ok=True)
    for name,pre in [('East','E'),('West','W'),('Savage','S'),('Dungeon','D')]:
        nj,nb,info=make(name.upper()+'.JTL',pre+'_BRIDGE.BRG')
        open('/home/claude/mod/Data/tile/%s.jtl'%name,'wb').write(nj)
        open('/home/claude/mod/Data/tile/%s_Bridge.brg'%pre,'wb').write(nb)
        print(name,info,len(nj),len(nb))
