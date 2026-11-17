import struct,numpy as np
class S16:
    def __init__(s,data):
        s.d=d=data; s.a,s.b,s.c,s.e=struct.unpack_from('<4I',d,0); s.g=struct.unpack_from('<H',d,16)[0]
        s.groups=struct.unpack_from('<%dH'%s.g,d,18)
        # frame descriptors in region a
        s.frames=[]; p=s.a
        while p<s.b:
            desc=struct.unpack_from('<IHHHHHHH',d,p); s.frames.append((p-s.a,desc)); p+=18+desc[5]*4
    def decode(s,i,block='b',fmt=565):
        rel,desc=s.frames[i]; base={'b':s.b,'c':s.c,'e':s.e}[block]
        # frames are laid out sequentially in each block; find frame start by walking
        p=base
        for k in range(i):
            dk=struct.unpack_from('<IHHHHHHH',s.d,p); h=dk[5]
            offs=struct.unpack_from('<%dI'%h,s.d,p+18); p=p+18+4*h+offs[-1]
        dk=struct.unpack_from('<IHHHHHHH',s.d,p); w,h=dk[4],dk[5]
        offs=struct.unpack_from('<%dI'%h,s.d,p+18); data=p+18+4*h
        img=np.zeros((h,w,4),np.uint8)
        ends=list(offs[:-1])+[offs[-1]//2]; prev=0
        for y in range(h):
            n=ends[y]-prev; row=struct.unpack_from('<%dH'%n,s.d,data+2*prev); prev=ends[y]
            x=0;j=0
            while j+1<len(row):
                sk,cnt=row[j],row[j+1]; j+=2
                if sk==0 and cnt==0: break
                x+=sk
                for q in range(cnt):
                    c=row[j+q]
                    if 0<=x+q<w:
                        if fmt==565: img[y,x+q]=[((c>>11)&31)*255//31,((c>>5)&63)*255//63,(c&31)*255//31,255]
                        else: img[y,x+q]=[((c>>10)&31)*255//31,((c>>5)&31)*255//31,(c&31)*255//31,255]
                j+=cnt; x+=cnt
        return dk,img
