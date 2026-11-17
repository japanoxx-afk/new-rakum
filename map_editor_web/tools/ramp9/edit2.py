import sys;sys.path.insert(0,'/home/claude/re');sys.path.insert(0,'/home/claude/re/ramp9')
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
def soft_poly(H,W,poly,f):
    from PIL import ImageDraw
    m=Image.new('L',(W,H),0); ImageDraw.Draw(m).polygon(poly,fill=255)
    return gaussian_filter(np.asarray(m,float)/255,f)
def edit(img, A=(150,2,262,82), Bpoly=None, src_off=(-215,20), dark=0.30, light=0.10):
    H,W=img.shape[:2]; out=img.astype(float).copy(); alpha=img[...,3]>0
    # 1) upper-left wall: re-flip locally so rock face hangs downward
    x0,y0,x1,y1=A; patch=img[y0:y1,x0:x1][::-1].astype(float)
    m=soft_poly(H,W,[(x0+8,y0+8),(x1-8,y0+8),(x1-8,y1-8),(x0+8,y1-8)],4)[y0:y1,x0:x1,None]
    m=m*(patch[...,3:4]>0)
    out[y0:y1,x0:x1,:3]=out[y0:y1,x0:x1,:3]*(1-m)+patch[...,:3]*m
    # 2) lower-right wall: replace rocks with grass sampled elsewhere
    if Bpoly is None: Bpoly=[(330,95),(420,80),(490,120),(470,150),(400,200),(320,230),(300,180)]
    mb=soft_poly(H,W,Bpoly,6)
    dx,dy=src_off; src=np.roll(np.roll(img.astype(float),dy,0),dx,1)
    ok=(np.roll(np.roll(alpha,dy,0),dx,1))[...,None]
    mbb=mb[...,None]*ok
    out[...,:3]=out[...,:3]*(1-mbb)+src[...,:3]*mbb
    # 3) slope shading along corridor lower-left(high)->upper-right(low)
    yy,xx=np.mgrid[0:H,0:W].astype(float)
    ax=np.array([382-128,64-192.]); L=np.hypot(*ax); u=ax/L
    t=((xx-128)*u[0]+(yy-192)*u[1])/L
    n=np.abs((xx-128)*(-u[1])+(yy-192)*u[0])   # distance from axis
    corridor=np.exp(-(n/70)**2)
    cx,cy=W/2,H/2; d=1-(np.abs(xx+0.5-cx)/cx+np.abs(yy+0.5-cy)/cy)
    fade=np.clip(d/0.12,0,1)
    g=1+(light*(1-t)-dark*np.clip(t,0,1)**1.5)*corridor*fade
    out[...,:3]*=g[...,None]
    out[...,3]=img[...,3]
    return np.clip(out,0,255).astype(np.uint8)
